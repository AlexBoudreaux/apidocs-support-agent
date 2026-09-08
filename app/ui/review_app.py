"""The reviewer page. Build spec section 7.

    uv run streamlit run app/ui/review_app.py

One ticket per thread, one interrupt per human turn. The page holds no state of
its own beyond which ticket is selected, because Postgres already holds it. Every
rerun reopens the checkpointer, rereads `graph.get_state(config).values`, and
draws from that, so a refresh, a second tab, or the CLI resuming the same thread
all see the same truth.

The one place that was not true was the draft box. See `render_editor` for why
its key carries the checkpoint id.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import streamlit as st
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app import settings
from app.graph import build_graph
from app.integrations import servicenow
from app.kb.index import KnowledgeBase

TAGS = ["good_as_is", "fixed_wording", "fixed_facts", "added_context", "escalated"]


@st.cache_resource
def load_kb() -> KnowledgeBase:
    """Loading embeds 37 descriptions, so it must survive reruns, not repeat them."""
    return KnowledgeBase.load()


@contextmanager
def open_graph() -> Iterator[CompiledStateGraph]:
    """Compile per read and per invoke, because a connection parked in
    `session_state` would outlive the script run that made it and go stale."""
    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as checkpointer:
        # from_conn_string takes no serde argument, so set it after construction.
        checkpointer.serde = settings.checkpoint_serde()
        yield build_graph(load_kb(), checkpointer)


def query_one(sql: str, ticket_id: str) -> dict | None:
    """Both things the page needs out of ServiceNow are one row by ticket id."""
    with servicenow.connect() as conn:
        row = conn.execute(sql, (ticket_id,)).fetchone()
    return dict(row) if row else None


def run_config(ticket: dict) -> dict:
    """The config every invoke uses. Metadata and tags per build spec section 6."""
    row = query_one("select level from sn_tickets where id = %s", ticket["id"]) or {}
    level = row.get("level")
    return {
        "configurable": {
            "thread_id": ticket["id"],
            "use_cache": True,
            "retrieval_mode": "hybrid",
        },
        "metadata": {
            "ticket_id": ticket["id"],
            "level": level,
            "api_version": ticket["api_version"],
            "area": ticket["product_area"],
            "retrieval_mode": "hybrid",
        },
        "tags": ["demo"],
        "run_name": f"ticket-{ticket['id']}",
    }


def resume(ticket: dict, payload: dict) -> None:
    """Resume, then rerun so the page rereads Postgres instead of guessing. A
    decision that comes back with no `sent` means send's PII re-check bounced it."""
    config = run_config(ticket)
    with open_graph() as graph:
        graph.invoke(Command(resume=payload), config)
        values = graph.get_state(config).values
    st.session_state.bounced = payload["type"] == "decision" and not values.get("sent")
    st.rerun()


def render_sidebar() -> None:
    """The queue. Clicking a row is the only way a ticket gets selected."""
    st.sidebar.header("Review queue")
    if st.sidebar.button("Refresh queue"):
        st.rerun()
    rows = servicenow.list_queue()
    if not rows:
        st.sidebar.info("Queue is empty. Run a ticket through the CLI first.")
    for row in rows:
        badge = "HIGH" if row["priority"] == "high" else "normal"
        label = f"{row['id']} [{badge}] {row['subject'][:34]}"
        if st.sidebar.button(label, key=f"pick_{row['id']}", width="stretch"):
            st.session_state.ticket_id = row["id"]
        st.sidebar.caption(f"{row['product_area']} / {row['api_version']} / {row['status']}")


def render_ticket(values: dict) -> None:
    """Top of the main area. Collapsed the header still says which ticket this is,
    so it only opens itself when triage did not answer and the ticket is the story."""
    ticket = values["ticket"]
    disposition = values.get("disposition") or ""
    priority = values.get("priority") or "normal"
    header = f"{ticket['id']}  [{priority}]  {ticket['subject']}"
    with st.expander(header, expanded=disposition in ("escalate", "abstain")):
        st.caption(f"{ticket['tenant']} / {ticket['api_version']} / {ticket['product_area']}"
                   f" / {ticket['created_at']} / disposition: {disposition or '-'}")
        st.text(ticket["body"])
        if disposition == "escalate":
            st.warning(f"Triage escalated: {values.get('triage_reason')}")


def render_editor(ticket: dict, values: dict, checkpoint_id: str) -> None:
    """Full width, and the tallest thing on the page, because the draft is what the
    room is meant to read. The decision row sits directly under it."""
    flags = values.get("guardrail_flags") or []
    if flags:
        st.warning("Guardrail flags: " + ", ".join(flags))

    # The key carries the checkpoint id, not just the ticket id. Streamlit keeps a
    # keyed widget's value across reruns and prefers it over `value=`, so when the
    # reviewer agent called `rewrite_draft` the new draft landed in Postgres and
    # the pane went on showing the old text until the browser was reloaded.
    # Deleting the key in `resume()` did not help: `render_editor` runs before
    # `render_chat` in `main`, so the old text is written back into widget state on
    # the same script run that then pops it.
    #
    # A new checkpoint id means the graph advanced, which is the only thing that
    # can change the draft under the reviewer. Typing in the box writes no
    # checkpoint, so unsent edits survive a plain rerun, and switching tickets
    # still drops the old text because the ticket id is in there too.
    key = f"draft_{ticket['id']}_{checkpoint_id}"
    text = st.text_area("Draft", value=values.get("draft") or "", height=420, key=key)

    with st.expander("Retrieved docs"):
        for doc in values.get("relevant_docs") or []:
            st.markdown(
                f"**{doc['doc_id']}** `{doc.get('route') or '-'}` "
                f"{doc.get('version')} / {doc.get('status')} / {doc.get('source')}  \n"
                f"{doc.get('url')}"
            )
        st.caption(str(values.get("retrieval_stats") or ""))

    # One row, left to right. Widget keys and the decision payload are unchanged.
    tags, checks, note_col, buttons = st.columns([2, 1.2, 2, 1.2], vertical_alignment="bottom")
    with tags:
        tag = st.radio("Tag", TAGS, key=f"tag_{ticket['id']}", horizontal=True)
    with checks:
        save_kb = st.checkbox("Save to KB", key=f"kb_{ticket['id']}")
        save_eval = st.checkbox("Save to eval set", key=f"eval_{ticket['id']}")
    with note_col:
        note = st.text_input("Escalation note", key=f"note_{ticket['id']}")
    with buttons:
        approve = st.button("Approve", type="primary", key=f"approve_{ticket['id']}",
                            width="stretch")
        escalate = st.button("Escalate", key=f"escalate_{ticket['id']}", width="stretch")

    if approve or escalate:
        decision = {
            "action": "escalate" if escalate else "approve",
            "final_answer": text,
            "human_tag": "escalated" if escalate else tag,
            "save_to_kb": save_kb,
            "save_to_eval": save_eval,
            "escalation_note": note if escalate else None,
        }
        resume(ticket, {"type": "decision", "decision": decision})


def render_chat(ticket: dict, values: dict) -> None:
    """Bottom of the page. Tool calls get a caption so the audience sees the agent work."""
    for message in values.get("messages") or []:
        kind = getattr(message, "type", "")
        role = "user" if kind == "human" else "assistant"
        calls = getattr(message, "tool_calls", None) or []
        # `.text` drops the reasoning blocks the Responses API returns alongside
        # the answer. Rendering `content` raw would print their encrypted payload
        # into the chat pane.
        content = str(message.text).strip()
        if not content and not calls:
            continue  # tool-call-only AI messages still get a caption, empty ones do not
        with st.chat_message(role):
            if kind == "tool":
                st.caption(f"{getattr(message, 'name', 'tool')} returned")
                st.code(content[:1500], language="markdown")
            elif content:
                st.write(content)
            if calls:
                st.caption("called " + ", ".join(c["name"] for c in calls))

    prompt = st.chat_input("Ask the reviewer agent")
    if prompt:
        resume(ticket, {"type": "chat", "text": prompt})


def render_done(ticket_id: str, values: dict) -> None:
    """The finished screen. The reply row and the edit score, nothing else."""
    st.success("Sent. Thread finished.")
    st.write(values.get("sent"))
    row = query_one("select ticket_id, kind, body, posted_at from sn_replies"
                    " where ticket_id = %s", ticket_id)
    if row:
        st.write(f"**sn_replies** {row['kind']} at {row['posted_at']}")
        st.text(row["body"])
    st.write("Edit score", values.get("edit_score"))


def main() -> None:
    st.set_page_config(page_title="Reviewer", layout="wide")
    st.title("Support reply review")
    st.caption("uv run streamlit run app/ui/review_app.py")
    render_sidebar()
    ticket_id = st.session_state.get("ticket_id")
    if not ticket_id:
        st.info("Pick a ticket from the queue.")
        return

    with open_graph() as graph:
        snapshot = graph.get_state({"configurable": {"thread_id": ticket_id}})
    values, nxt = snapshot.values, snapshot.next
    checkpoint_id = (snapshot.config.get("configurable") or {}).get("checkpoint_id", "")
    if not values:
        st.warning(f"No checkpoint for thread {ticket_id!r}. Run it through the CLI first.")
        return

    if not nxt and values.get("sent"):
        render_done(ticket_id, values)
        return

    if st.session_state.pop("bounced", False):
        st.warning("Send bounced this back to review. The flags are on the draft.")

    # Top to bottom: ticket header, draft plus decision row, chat. The queue is in
    # the sidebar, so the draft owns the full width instead of a quarter of it.
    render_ticket(values)
    render_editor(values["ticket"], values, checkpoint_id)
    st.divider()
    st.subheader("Reviewer chat")
    render_chat(values["ticket"], values)


# Streamlit runs this file as __main__, so the guard keeps a plain import side effect free.
if __name__ == "__main__":
    main()
