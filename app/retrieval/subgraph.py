"""The retrieval subgraph and its wrapper. Build spec sections 4.2 and 9.

```
plan_queries --fan_out (Send)--> search (x N) -> reflect
reflect --route_after_reflect--> plan_queries | END
```

Composition is the "different state schemas" pattern: the parent never sees
`queries`, `results`, or the loop counter. A wrapper function invokes the
compiled subgraph and hands back only `relevant_docs`, `retrieval_stats`, and
(on abstain) `disposition`. That is what "pass only the documentation that's
relevant to the next step" means in code.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy, Send

from app.kb.index import KnowledgeBase
from app.retrieval.planner import plan_queries
from app.retrieval.reflect import reflect, route_after_reflect
from app.retrieval.search import make_search
from app.state import RetrievalState, Ticket

log = logging.getLogger(__name__)


def fan_out(state: RetrievalState) -> list[Send]:
    """One parallel `search` branch per planned query, all in one superstep."""
    return [
        Send("search", {"query": q, "ticket": state["ticket"]})
        for q in state["queries"]
    ]


def build_retrieval_subgraph(kb: KnowledgeBase) -> CompiledStateGraph:
    """Compile the subgraph. No checkpointer: the parent owns persistence."""
    builder = StateGraph(RetrievalState)

    builder.add_node("plan_queries", plan_queries, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("search", make_search(kb))
    builder.add_node("reflect", reflect, retry_policy=RetryPolicy(max_attempts=3))

    builder.set_entry_point("plan_queries")
    builder.add_conditional_edges("plan_queries", fan_out, ["search"])
    builder.add_edge("search", "reflect")
    builder.add_conditional_edges(
        "reflect", route_after_reflect, {"plan_queries": "plan_queries", END: END}
    )

    return builder.compile()


# One compiled subgraph per `KnowledgeBase`, so the reviewer's `rerun_retrieval`
# and a 90-run experiment do not recompile the graph on every call. Keyed by
# object identity and holding the `kb` itself, so the entry cannot outlive it in
# a way that hands back a graph closed over a different corpus.
_COMPILED: dict[int, tuple[KnowledgeBase, Runnable]] = {}


def _compiled_for(kb: KnowledgeBase) -> Runnable:
    """Compile once per KB. `run_name` is what the nested span is called in LangSmith."""
    cached = _COMPILED.get(id(kb))
    if cached is None or cached[0] is not kb:
        # Named so the nested span reads as "retrieval_subgraph" rather than the
        # default "LangGraph".
        compiled = build_retrieval_subgraph(kb).with_config(run_name="retrieval_subgraph")
        _COMPILED[id(kb)] = (kb, compiled)
        return compiled
    return cached[1]


def run_retrieval(
    ticket: Ticket,
    kb: KnowledgeBase,
    config: RunnableConfig,
    hint: str | None = None,
) -> dict:
    """Run the subgraph for one ticket and return only the parent's keys.

    The same `config` goes in, so `use_cache` and `retrieval_mode` flow through
    and the subgraph's trace nests under the parent's.

    Returns `relevant_docs`, `retrieval_stats`, and `disposition` only when the
    subgraph abstained. The caller drops the `None`.
    """
    result = _compiled_for(kb).invoke(
        RetrievalState(
            ticket=ticket,
            hint=hint,
            iteration=0,
            results=[],
            modes=[],
            keep=[],
            queries=[],
            missing=None,
            decision=None,
        ),
        config,
    )

    # Branches ran concurrently and the same doc can come back from more than
    # one index, so dedupe by doc_id while keeping first-seen order.
    deduped = list({d["doc_id"]: d for d in result.get("results", [])}.values())
    keep = set(result.get("keep", []))
    decision = result.get("decision")

    return {
        "relevant_docs": [d for d in deduped if d["doc_id"] in keep],
        "retrieval_stats": {
            "iterations": result.get("iteration", 0),
            "queries_run": len(result.get("modes", [])),
            "modes": result.get("modes", []),
            "abstained": decision == "abstain",
        },
        "disposition": "abstain" if decision == "abstain" else None,
    }
