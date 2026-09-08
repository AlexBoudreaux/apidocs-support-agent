"""guardrail and its router. Build spec section 4.1, RFC 3.5, decision 7.

Reads `draft`, `relevant_docs`, `disposition`, `guardrail_attempts`. Writes
`guardrail_flags`, `guardrail_attempts` (incremented), and `priority` (high on
the second failure).

No model call by decision. The human reviewer is the judge of whether the answer
makes sense and the offline eval is the judge of whether it is correct, so a
third judge in the middle would add latency and change nothing. What is left is
two deterministic checks, PII and secrets on the draft, and groundedness of every
route, url, and error code against the retrieved docs.

Groundedness is skipped on abstain because a gap report names routes that were
searched, not routes that were retrieved.

The retry is real rather than a reroll because `guardrail_flags` goes into the
second draft prompt as the list of things to fix. Two failures means something a
third attempt will not fix, and the human is next in line anyway.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from app.checks import groundedness, pii_scan
from app.state import TicketState

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2


def guardrail(state: TicketState, config: RunnableConfig) -> dict:
    """Flag the draft, count the attempt, raise priority on a second failure."""
    draft = state.get("draft") or ""
    flags = list(pii_scan(draft))
    if state.get("disposition") != "abstain":
        flags += groundedness(draft, state.get("relevant_docs", []))

    attempts = state.get("guardrail_attempts", 0) + 1
    update: dict = {"guardrail_flags": flags, "guardrail_attempts": attempts}
    if flags and attempts >= MAX_ATTEMPTS:
        update["priority"] = "high"

    log.info(
        "guardrail: attempt %d, %d flag(s)%s",
        attempts,
        len(flags),
        f" -> {'; '.join(flags)}" if flags else "",
    )
    return update


def route_after_guardrail(state: TicketState) -> str:
    """Clean draft goes to the human. A flagged one gets exactly one retry."""
    if not state.get("guardrail_flags"):
        return "review"
    if state.get("guardrail_attempts", 0) < MAX_ATTEMPTS:
        return "draft"
    return "review"
