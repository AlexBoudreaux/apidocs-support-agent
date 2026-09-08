"""Deterministic guardrail checks. Owner is session 4d. Build spec section 9.

No LLM judge lives here by decision: the human and the offline eval are the
judges. Three call sites, one policy. Intake redacts with `redact`, the guardrail
flags the draft, and send flags whatever the human approved.

PII detection reuses LangChain's own detectors from
`langchain.agents.middleware.pii` rather than re-deriving the regexes, so the
node checks and the reviewer agent's `PIIMiddleware` agree on what an email is.
The one category deliberately dropped is `url`: every good draft carries deep
links, so scanning for urls would flag every draft the system writes.

`API_KEY_REGEX` is a string rather than a callable because 4d's reviewer agent
passes it straight to `PIIMiddleware(..., detector=API_KEY_REGEX)`.
"""

from __future__ import annotations

import re

from langchain.agents.middleware.pii import (
    PIIMatch,
    detect_credit_card,
    detect_email,
    detect_ip,
    detect_mac_address,
)

from app.state import Doc

REDACTED = "[REDACTED]"

# Provider-style secrets we never want in a draft, a trace, or a reply.
API_KEY_REGEX = (
    r"\b("
    r"sk_(?:live|test)_[A-Za-z0-9]{16,}"      # stripe-style secret key
    r"|sk-proj-[A-Za-z0-9_\-]{20,}"           # openai project key
    r"|whsec_[A-Za-z0-9]{16,}"                # webhook signing secret
    r"|Bearer\s+eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"  # bearer jwt
    r")\b"
)

_API_KEY = re.compile(API_KEY_REGEX)

# LangChain's detectors, minus `url`. Each returns a list of PIIMatch dicts with
# `type`, `value`, `start`, `end`.
_DETECTORS = (
    ("email", detect_email),
    ("credit_card", detect_credit_card),
    ("ip", detect_ip),
    ("mac_address", detect_mac_address),
)

# Route paths always carry their version prefix in this corpus.
_ROUTE = re.compile(r"/v[23](?:/[A-Za-z0-9_.{}\-]+)+")
_URL = re.compile(r"https?://[^\s)\]<>\"'`]+")
_ERROR_CODE = re.compile(r"\b(?:PAY_\d{4}|WHK_\d{4}|RATE_LIMITED)\b")


def _mask(value: str) -> str:
    """Show enough of a hit to be actionable without reprinting the secret."""
    head = value[:6]
    return f"{head}…" if len(value) > len(head) else value


def _find(text: str) -> list[PIIMatch]:
    """Every PII and secret match in `text`, sorted by position."""
    matches: list[PIIMatch] = []
    for _, detector in _DETECTORS:
        matches.extend(detector(text))
    for m in _API_KEY.finditer(text):
        matches.append(
            PIIMatch(type="api_key", value=m.group(0), start=m.start(), end=m.end())
        )
    matches.sort(key=lambda m: (m["start"], m["end"]))
    return matches


def pii_scan(text: str) -> list[str]:
    """Return one human readable flag per PII or secret hit in `text`.

    Flags land in `guardrail_flags`, which is graph state and therefore shows up
    in the trace and in the review UI, so the value is masked. The point of the
    flag is to tell the reviewer what tripped and roughly where, not to reprint
    the key.
    """
    if not text:
        return []
    seen: set[tuple[str, str]] = set()
    flags: list[str] = []
    for m in _find(text):
        key = (m["type"], m["value"])
        if key in seen:
            continue
        seen.add(key)
        flags.append(f"{m['type']} found in text: {_mask(m['value'])}")
    return flags


def redact(text: str) -> str:
    """Replace every PII and secret hit with `[REDACTED]`. Used at intake.

    Spans are replaced back to front so earlier offsets stay valid.
    """
    if not text:
        return text
    out = text
    for m in sorted(_find(text), key=lambda m: m["start"], reverse=True):
        out = out[: m["start"]] + REDACTED + out[m["end"] :]
    return out


# ---------- groundedness ----------


def _normalize_route(route: str) -> str:
    """Collapse a concrete path into its documented shape.

    `/v3/payments/pay_3Kd91xR2/refund` and `/v3/payments/{id}/refund` are the
    same route. Any segment that already looks like a placeholder, or that mixes
    letters and digits the way an object id does, becomes `{id}`.
    """
    parts = route.rstrip("/.,;:").split("/")
    out = []
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            out.append("{id}")
        elif part not in ("v2", "v3") and re.fullmatch(r"[A-Za-z0-9_\-]*\d[A-Za-z0-9_\-]*", part):
            out.append("{id}")
        else:
            out.append(part)
    return "/".join(out)


def _doc_corpus(docs: list[Doc]) -> str:
    """Everything the draft is allowed to have taken an identifier from."""
    return "\n".join(
        f"{d.get('route', '')}\n{d.get('url', '')}\n{d.get('error_code') or ''}\n{d.get('text', '')}"
        for d in docs
    )


def groundedness(draft: str, docs: list[Doc]) -> list[str]:
    """Flag every route, url, and error code in `draft` that is absent from `docs`.

    Deterministic, no model call. A doc "contains" an identifier if it appears
    anywhere in that doc's route, url, error code, or body text, because the
    refund doc legitimately names the reversal route and the error tables name
    the routes they apply to.

    Skipped on abstain by the guardrail node, because a gap report names routes
    that were searched, not routes that were retrieved.
    """
    if not draft:
        return []

    corpus = _doc_corpus(docs)
    allowed_routes = {_normalize_route(r) for r in _ROUTE.findall(corpus)}
    allowed_urls = {u.rstrip(".,;:") for u in _URL.findall(corpus)}
    allowed_codes = set(_ERROR_CODE.findall(corpus))

    flags: list[str] = []
    seen: set[str] = set()

    for raw in _ROUTE.findall(draft):
        route = _normalize_route(raw)
        if route not in allowed_routes and route not in seen:
            seen.add(route)
            flags.append(f"route {route} is not in the retrieved docs")

    for raw in _URL.findall(draft):
        url = raw.rstrip(".,;:")
        if url not in allowed_urls and url not in seen:
            seen.add(url)
            flags.append(f"url {url} is not in the retrieved docs")

    for code in _ERROR_CODE.findall(draft):
        if code not in allowed_codes and code not in seen:
            seen.add(code)
            flags.append(f"error code {code} is not in the retrieved docs")

    return flags
