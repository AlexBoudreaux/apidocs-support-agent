"""review, reviewer_agent, and the router between them. Build spec section 4.1.

**review** reads everything. Writes either `review` (on a decision) or
`pending_human` plus `messages` (on a chat turn). Exactly one `interrupt()` call
and nothing with side effects before it.

**reviewer_agent** reads `ticket`, `draft`, `relevant_docs`, `messages`,
`pending_human`. Writes `messages`, `draft` and `relevant_docs` if a tool changed
them, and `pending_human=None`.

Two nodes and not one loop, because `interrupt()` re-runs the node from the top
on resume. A single node holding the whole conversation would re-execute every
earlier agent turn, and every `rewrite_draft` side effect, on each resume.
Splitting the human turn from the agent turn gives one interrupt per node run,
so nothing replays.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.kb.index import KnowledgeBase
from app.reviewer.agent import RECURSION_LIMIT, ReviewContext, build_reviewer_agent
from app.state import ReviewDecision, TicketState

log = logging.getLogger(__name__)


def review(state: TicketState, config: RunnableConfig) -> dict:
    """Pause for the human. One interrupt per human turn, on the ticket's thread."""
    payload = {
        "ticket": state["ticket"],
        "draft": state.get("draft"),
        "disposition": state.get("disposition"),
        "triage_reason": state.get("triage_reason"),
        "guardrail_flags": state.get("guardrail_flags", []),
        "relevant_docs": state.get("relevant_docs", []),
        "priority": state.get("priority", "normal"),
        "messages_len": len(state.get("messages", [])),
    }

    resumed = interrupt(payload)

    kind = (resumed or {}).get("type")
    if kind == "chat":
        text = resumed["text"]
        log.info("review: human chat turn, %d chars", len(text))
        return {"pending_human": text, "messages": [HumanMessage(text)]}

    if kind == "decision":
        decision = ReviewDecision.model_validate(resumed["decision"])
        log.info("review: human decision action=%s tag=%s", decision.action, decision.human_tag)
        return {"review": decision, "pending_human": None}

    raise ValueError(f"unknown resume payload type: {kind!r}")


def make_reviewer_agent_node(kb: KnowledgeBase):
    """Close the reviewer_agent node over the process-wide `KnowledgeBase`."""

    def reviewer_agent(state: TicketState, config: RunnableConfig) -> dict:
        """Run exactly one agent turn and fold its tool effects back into state."""
        ctx = ReviewContext(
            ticket=state["ticket"],
            draft=state.get("draft"),
            relevant_docs=list(state.get("relevant_docs", [])),
            kb=kb,
            config=config,
        )

        try:
            agent = build_reviewer_agent(ctx)
            result = agent.invoke(
                {"messages": state.get("messages", [])},
                {**config, "recursion_limit": RECURSION_LIMIT},
            )
            new_messages = result["messages"][len(state.get("messages", [])):]
        except Exception as exc:
            log.exception("reviewer agent failed")
            new_messages = [
                AIMessage(
                    f"The reviewer agent hit an error: {exc}. You can still edit "
                    "the draft by hand and approve."
                )
            ]

        return {
            "messages": new_messages,
            "draft": ctx.draft,
            "relevant_docs": ctx.relevant_docs,
            "pending_human": None,
        }

    return reviewer_agent


def route_after_review(state: TicketState) -> str:
    """A chat message goes to the agent. A decision goes to send."""
    if state.get("pending_human"):
        return "reviewer_agent"
    if state.get("review") is not None:
        return "send"
    raise ValueError("review node produced neither pending_human nor review")
