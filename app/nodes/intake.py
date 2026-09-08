"""intake. Build spec section 4.1.

Reads nothing (its input is the graph's input). Writes `ticket`,
`first_trace_id`, `guardrail_flags=[]`, `guardrail_attempts=0`,
`priority="normal"`, `relevant_docs=[]`, `messages=[]`.

No model call. Redaction runs here so no model call and no trace ever sees a
raw secret.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from app.checks import pii_scan, redact
from app.state import Ticket, TicketState

log = logging.getLogger(__name__)

REQUIRED_FIELDS = ("id", "tenant", "api_version", "subject", "body", "created_at")


def _trace_id() -> str | None:
    """The trace this first invoke belongs to, recorded once for post_send.

    The approval resume is a second `invoke` and therefore a second LangSmith
    trace, measured 2026-09-04. Feedback written at post_send lands on that
    approval trace, which is correct but is not where the draft was generated.
    Pinning the first trace id in state at intake costs one field and lets
    post_send write the same feedback to both. Returns None when tracing is off.
    """
    try:
        from langsmith.run_helpers import get_current_run_tree

        tree = get_current_run_tree()
        return str(tree.trace_id) if tree is not None else None
    except Exception:
        log.warning("intake: could not read the current run tree")
        return None


def _redact(text: str) -> str:
    """Replace every PII and secret hit with `[REDACTED]`.

    The substitution lives in `checks.redact` so the span walk is written once.
    `pii_scan` is called here only to log how many hits there were, because the
    count is the thing worth seeing in the run log and the values are not.
    """
    flags = pii_scan(text)
    if not flags:
        return text
    log.info("intake: redacting %d hit(s)", len(flags))
    return redact(text)


def intake(state: TicketState, config: RunnableConfig) -> dict:
    """Validate the incoming ticket, redact it, and set the state defaults."""
    ticket = state.get("ticket")
    if not isinstance(ticket, dict):
        raise ValueError("intake expected {'ticket': Ticket} as graph input")

    missing = [f for f in REQUIRED_FIELDS if not ticket.get(f)]
    if missing:
        raise ValueError(f"malformed ticket {ticket.get('id')!r}: missing {missing}")
    if ticket["api_version"] not in ("v2", "v3"):
        raise ValueError(f"ticket {ticket['id']!r}: api_version must be v2 or v3")

    area = ticket.get("product_area")
    if area not in ("payments", "webhooks"):
        area = "unknown"

    clean = Ticket(
        id=ticket["id"],
        tenant=ticket["tenant"],
        api_version=ticket["api_version"],
        product_area=area,
        subject=_redact(ticket["subject"]),
        body=_redact(ticket["body"]),
        created_at=ticket["created_at"],
    )

    log.info("intake: ticket %s area=%s version=%s", clean["id"], area, clean["api_version"])
    return {
        "ticket": clean,
        "first_trace_id": _trace_id(),
        "guardrail_flags": [],
        "guardrail_attempts": 0,
        "priority": "normal",
        "relevant_docs": [],
        "messages": [],
    }
