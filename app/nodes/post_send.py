"""post_send. Build spec section 4.1.

Reads `first_draft`, `review`, `ticket`, `relevant_docs`, `disposition`,
`first_trace_id`. Writes `edit_score`.

This is the flywheel: every reviewed ticket produces a label for free. Three
feedbacks go on the run, optionally one example goes to the from-traffic
dataset, and optionally one approved answer goes into `kb/approved/` and the
live index. LangSmith failures log and continue.

Settled 2026-09-04, the question build spec 4.1 left for 4d. The approval resume
is a second `invoke` and is always a second LangSmith trace, in a second process
or the same one. Measured with two invokes on one thread: the node's
`get_current_run_tree().trace_id` differs between the first invoke and the
resume. So feedback written here lands on the approval trace by default.

That is the right place for the human tag, since the human acted on that trace,
but it is the wrong place to go looking for the draft that was scored. Intake
now pins the first invoke's trace id into `first_trace_id`, and post_send writes
the same three feedbacks to both traces when they differ. Two extra
`create_feedback` calls, no extra model call, and the draft trace carries its own
score.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from app import settings
from app.edit_score import tier1
from app.integrations import servicenow
from app.integrations.langsmith_feedback import save_to_eval, write_edit_feedback
from app.state import Doc, TicketState

log = logging.getLogger(__name__)


def _current_run_id() -> str:
    """Root run id of the trace this node is executing inside, the approval trace."""
    try:
        from langsmith.run_helpers import get_current_run_tree

        tree = get_current_run_tree()
        return str(tree.trace_id) if tree is not None else ""
    except Exception:
        log.exception("post_send: could not read the current run tree")
        return ""


def _feedback_targets(state: TicketState) -> list[str]:
    """Every trace that should carry this ticket's labels, approval trace first.

    Two entries in the normal case. The approval trace, where the human acted,
    and the original run trace, where the draft being scored was written.
    """
    targets = [t for t in (_current_run_id(), state.get("first_trace_id")) if t]
    return list(dict.fromkeys(targets))


def _save_approved_answer(state: TicketState) -> None:
    """Write one markdown file to `kb/approved/` and add it to the live index."""
    docs = [d for d in state.get("relevant_docs", []) if d["source"] == "doc"]
    if not docs:
        log.info("post_send: save_to_kb requested but no doc-source entries, skipping")
        return

    ticket = state["ticket"]
    # Build spec says "the first doc-source entry", but an error-table row is a
    # doc-source entry with route "" and version "all", and pinning a cached
    # answer to that makes it unreachable through the exact index. Prefer the
    # first entry that actually carries a route.
    first = next((d for d in docs if d["route"]), docs[0])
    doc = Doc(
        doc_id=f"approved-{ticket['id']}",
        source="approved_answer",
        route=first["route"],
        version=first["version"],
        area=first["area"],
        status="current",
        replaced_by=None,
        error_code=None,
        description=ticket["subject"],
        url=first["url"],
        text=state["review"].final_answer,
    )

    settings.APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.APPROVED_DIR / f"{ticket['id']}.md"
    path.write_text(
        "---\n"
        f"doc_id: {doc['doc_id']}\n"
        "source: approved_answer\n"
        f"route: {doc['route']}\n"
        f"version: {doc['version']}\n"
        f"area: {doc['area']}\n"
        "status: current\n"
        "replaced_by: null\n"
        f"description: {doc['description']}\n"
        f"url: {doc['url']}\n"
        "---\n\n"
        f"{doc['text']}\n"
    )
    log.info("post_send: wrote approved answer %s", path)

    kb = state.get("_kb")  # set by the node closure below
    if kb is not None:
        kb.add_approved_answer(doc)


def make_post_send(kb):
    """Close post_send over the process-wide `KnowledgeBase`."""

    def post_send(state: TicketState, config: RunnableConfig) -> dict:
        """Score the edit, write the feedback, close the ticket."""
        decision = state["review"]
        score = tier1(state.get("first_draft") or "", decision.final_answer)

        disposition = state.get("disposition")
        disposition_miss = (disposition == "answer" and decision.action == "escalate") or (
            disposition == "abstain" and decision.action == "approve"
        )

        for run_id in _feedback_targets(state):
            try:
                write_edit_feedback(run_id, score, decision.human_tag, disposition_miss)
            except Exception:
                log.exception("post_send: edit feedback write failed on %s, continuing", run_id)

        if decision.save_to_eval:
            try:
                save_to_eval(state["ticket"], decision.final_answer, disposition or "answer")
            except Exception:
                log.exception("post_send: save_to_eval failed, continuing")

        if decision.save_to_kb and decision.action == "approve":
            try:
                _save_approved_answer({**state, "_kb": kb})
            except Exception:
                log.exception("post_send: save_to_kb failed, continuing")

        try:
            servicenow.mark_status(state["ticket"]["id"], "closed")
        except Exception:
            log.exception("post_send: mark_status failed, continuing")

        log.info(
            "post_send: ticket %s edit_kind=%s disposition_miss=%s traces=%s",
            state["ticket"]["id"],
            score["kind"],
            disposition_miss,
            _feedback_targets(state) or "(tracing off)",
        )
        return {"edit_score": score}

    return post_send
