"""send and its router. Build spec section 4.1.

Reads `ticket`, `review`, `sent`. Writes `sent`, or `guardrail_flags` if the PII
re-check trips.

Idempotency is the primary key on `sn_replies.ticket_id`: a resumed graph that
reaches send twice hits the conflict and treats it as already sent. Durable
execution gives crash recovery, not idempotency, so the check is in the code.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig

from app.checks import pii_scan
from app.integrations import servicenow
from app.state import SentRecord, TicketState

log = logging.getLogger(__name__)


def send(state: TicketState, config: RunnableConfig) -> dict:
    """Post the approved answer or the escalation back to ServiceNow, once."""
    if state.get("sent") is not None:
        log.info("send: already sent, no-op")
        return {}

    decision = state["review"]
    flags = pii_scan(decision.final_answer)
    if flags:
        # Routes back to review with the flags visible rather than redacting
        # silently. Costs one edge, keeps the human in the loop.
        log.info("send: PII re-check tripped with %d flag(s), back to review", len(flags))
        return {"guardrail_flags": flags, "review": None}

    ticket_id = state["ticket"]["id"]
    kind = "escalation" if decision.action == "escalate" else "answer"
    body = decision.escalation_note if kind == "escalation" else decision.final_answer

    posted = servicenow.post_reply(ticket_id, kind, body or "")
    if not posted:
        log.info("send: primary key conflict on %s, treating as already sent", ticket_id)

    return {
        "sent": SentRecord(
            ticket_id=ticket_id,
            kind=kind,
            posted_at=datetime.now(timezone.utc).isoformat(),
        )
    }


def route_after_send(state: TicketState) -> str:
    """Sent goes on to the feedback write. A tripped re-check goes back to the human."""
    return "post_send" if state.get("sent") is not None else "review"
