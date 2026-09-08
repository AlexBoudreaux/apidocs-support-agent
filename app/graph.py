"""The parent graph. Build spec section 4.1.

```
intake -> triage
triage --route_after_triage--> retrieval | review
retrieval -> draft
draft -> guardrail
guardrail --route_after_guardrail--> review | draft
review --route_after_review--> reviewer_agent | send
reviewer_agent -> review
send --route_after_send--> post_send | review
post_send -> END
```

Node names, edges, and routers are frozen. Sessions 4c and 4d fill in node
bodies; nobody adds or renames a node without updating `app/state.py` and
the tests first.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from app.kb.index import KnowledgeBase
from app.nodes.draft import draft
from app.nodes.guardrail import guardrail, route_after_guardrail
from app.nodes.intake import intake
from app.nodes.post_send import make_post_send
from app.nodes.review import make_reviewer_agent_node, review, route_after_review
from app.nodes.send import route_after_send, send
from app.nodes.triage import route_after_triage, triage
from app.retrieval.subgraph import run_retrieval
from app.state import TicketState

log = logging.getLogger(__name__)


def make_retrieval_node(kb: KnowledgeBase):
    """Wrapper node around the retrieval subgraph.

    Reads `ticket`. Writes `relevant_docs`, `retrieval_stats`, and, when the
    subgraph abstained, `disposition="abstain"` plus `priority="high"`. No model
    call in the wrapper itself.
    """

    def retrieval(state: TicketState, config: RunnableConfig) -> dict:
        """Run the subgraph and keep only the keys the parent needs."""
        result = run_retrieval(state["ticket"], kb, config)

        update = {
            "relevant_docs": result["relevant_docs"],
            "retrieval_stats": result["retrieval_stats"],
        }
        if result.get("disposition") == "abstain":
            update["disposition"] = "abstain"
            update["priority"] = "high"

        log.info(
            "retrieval: %d doc(s) kept, %d queries, %d iteration(s), abstained=%s",
            len(update["relevant_docs"]),
            result["retrieval_stats"]["queries_run"],
            result["retrieval_stats"]["iterations"],
            result["retrieval_stats"]["abstained"],
        )
        return update

    return retrieval


def build_graph(kb: KnowledgeBase, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    """Compile the parent graph. `thread_id` on the config equals `ticket.id`."""
    builder = StateGraph(TicketState)

    builder.add_node("intake", intake)
    builder.add_node("triage", triage, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("retrieval", make_retrieval_node(kb))
    builder.add_node("draft", draft, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("guardrail", guardrail)
    builder.add_node("review", review)
    builder.add_node("reviewer_agent", make_reviewer_agent_node(kb))
    builder.add_node("send", send)
    builder.add_node("post_send", make_post_send(kb))

    builder.set_entry_point("intake")
    builder.add_edge("intake", "triage")
    builder.add_conditional_edges(
        "triage", route_after_triage, {"retrieval": "retrieval", "review": "review"}
    )
    builder.add_edge("retrieval", "draft")
    builder.add_edge("draft", "guardrail")
    builder.add_conditional_edges(
        "guardrail", route_after_guardrail, {"review": "review", "draft": "draft"}
    )
    builder.add_conditional_edges(
        "review", route_after_review, {"reviewer_agent": "reviewer_agent", "send": "send"}
    )
    builder.add_edge("reviewer_agent", "review")
    builder.add_conditional_edges(
        "send", route_after_send, {"post_send": "post_send", "review": "review"}
    )
    builder.add_edge("post_send", END)

    return builder.compile(checkpointer=checkpointer)
