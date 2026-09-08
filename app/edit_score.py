"""Draft-to-approved edit distance, tier 1. Build spec section 8.6.

Tier 1 is an identifier diff, not a text diff. The question it answers is "did
the human change what this answer *says*, or only how it reads," and the only
tokens that can change what an API answer says are the route, the version, the
error code, and the deep link. Wording is free to move.

`kind` is:

- `none`      the two texts are identical after whitespace normalization
- `style`     the identifier sets match, so only prose changed
- `correctness` the identifier sets differ

Tiers 2 (embedding distance) and 3 (LLM judge) are on the slide, not built.
Tier 4 is the human tag, which the reviewer supplies directly.
"""

from __future__ import annotations

import logging
import re

from app.state import EditScore

log = logging.getLogger(__name__)

# A route path as this corpus writes them: /v3/payments/{id}/refund. Leading
# version segment is required, so a bare "/refund" or a markdown link target is
# not mistaken for one. Trailing punctuation is trimmed by the caller because a
# route is very often the last thing in a sentence.
ROUTE_RE = re.compile(r"/v[23](?:/[A-Za-z0-9_{}.-]+)+", re.IGNORECASE)

# Bare version tokens, "v2" and "v3", when they stand as words. Occurrences
# inside a route are already covered by ROUTE_RE and are stripped before this
# runs, so "v3" here means the prose said "on v3".
VERSION_RE = re.compile(r"\bv[23]\b", re.IGNORECASE)

# SCREAMING_SNAKE error codes: PAY_4013, WHK_4100, RATE_LIMITED. Two or more
# segments, so a lone acronym like "API" or "POST" does not qualify.
ERROR_CODE_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")

URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")

# Punctuation a route or url picks up from the sentence around it, or from
# markdown emphasis and link syntax.
_TRAILING = ".,;:!?`*_)]}>\"'"


def _clean(token: str) -> str:
    """Strip markdown and sentence punctuation off the end of a matched token."""
    return token.rstrip(_TRAILING)


def extract_identifiers(text: str) -> set[str]:
    """Route paths, version tokens, error codes, and urls found in `text`.

    Case is preserved for error codes and urls because both are case bearing.
    Routes are lowercased: `/V3/Payments` and `/v3/payments` are the same route
    and a reviewer fixing capitalization is a style edit, not a correctness one.
    """
    if not text:
        return set()

    found: set[str] = set()

    urls = [_clean(m) for m in URL_RE.findall(text)]
    found.update(urls)

    # Strip the urls before route matching. A deep link ends in a path that
    # looks exactly like a route ("/v3/payments/refund") and would otherwise be
    # counted twice, once as the url and once as a route that the prose never
    # actually named.
    without_urls = URL_RE.sub(" ", text)

    routes = [_clean(m).lower() for m in ROUTE_RE.findall(without_urls)]
    found.update(routes)

    # And strip the routes before the bare-version pass, for the same reason.
    without_routes = ROUTE_RE.sub(" ", without_urls)
    found.update(m.lower() for m in VERSION_RE.findall(without_routes))

    found.update(ERROR_CODE_RE.findall(text))

    return {t for t in found if t}


def _normalized(text: str) -> str:
    """Collapse every run of whitespace so reflowing a paragraph is not an edit."""
    return " ".join((text or "").split())


def tier1(first_draft: str, final_answer: str) -> EditScore:
    """Compare the pipeline's first draft with what the human actually sent."""
    before = extract_identifiers(first_draft)
    after = extract_identifiers(final_answer)

    added = sorted(after - before)
    removed = sorted(before - after)

    if _normalized(first_draft) == _normalized(final_answer):
        kind = "none"
    elif not added and not removed:
        kind = "style"
    else:
        kind = "correctness"

    score = EditScore(
        tier=1,
        kind=kind,
        added_identifiers=added,
        removed_identifiers=removed,
        char_delta=len(final_answer or "") - len(first_draft or ""),
    )
    log.info(
        "edit_score.tier1: kind=%s added=%s removed=%s char_delta=%d",
        kind,
        added,
        removed,
        score["char_delta"],
    )
    return score
