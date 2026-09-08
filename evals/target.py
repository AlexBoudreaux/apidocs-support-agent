"""Eval targets. Build spec section 8.2.

Two callables that `client.evaluate` can point at.

* `run_full_graph` drives the whole parent graph to the review interrupt and
  hands back a flat dict of the things the evaluators grade.
* `run_retrieval_only` calls `run_retrieval` directly, skipping draft, guardrail
  and review, so a low end-to-end score can be split into "retrieval found the
  wrong docs" and "retrieval was fine and drafting failed on top of it".

Both run with `use_cache=False`. The seed approved answer in `kb/approved/` is a
memorized answer to a golden-set ticket, and grading the system on it would be
grading it on the answer key.

Neither imports a node. The parent graph is the only entry point, per the
section 9 contract.
"""

from __future__ import annotations

import logging
import threading
import uuid

from langgraph.checkpoint.memory import InMemorySaver

from app import settings
from app.graph import build_graph
from app.kb.index import KnowledgeBase
from app.retrieval.subgraph import run_retrieval
from app.state import Ticket

log = logging.getLogger(__name__)

# One KB and one compiled graph per process. `evaluate` runs examples on a
# thread pool, so a per-call `KnowledgeBase.load()` would re-read the corpus and
# re-embed 52 descriptions on every one of the 90 runs.
# Reentrant: `get_graph` holds the lock and calls `get_kb`, which takes it
# again. A plain Lock deadlocks the first call and every eval thread behind it.
_lock = threading.RLock()
_kb: KnowledgeBase | None = None
_graph = None


def get_kb() -> KnowledgeBase:
    """The process-wide corpus. Loaded once, embedded lazily on first search."""
    global _kb
    with _lock:
        if _kb is None:
            _kb = KnowledgeBase.load()
            log.info("target: loaded %d docs", len(_kb.all_doc_ids()))
        return _kb


def get_graph():
    """The parent graph, compiled once against an `InMemorySaver`.

    `interrupt()` requires a checkpointer, so the eval needs one even though it
    never resumes a thread. In-memory rather than Postgres: an experiment run is
    not a demo run and has no business leaving 90 threads in the demo database.
    """
    global _graph
    with _lock:
        if _graph is None:
            saver = InMemorySaver(serde=settings.checkpoint_serde())
            _graph = build_graph(get_kb(), saver)
        return _graph


def _ticket_of(inputs: dict) -> Ticket:
    """Dataset examples carry the ticket under `inputs.ticket`."""
    return inputs["ticket"]


def _config(ticket: Ticket, retrieval_mode: str) -> dict:
    """A fresh thread per call, plus the metadata the trace is filtered by.

    Tag is `eval`, not `demo`. The online evaluator Alex configures in the UI
    filters on `demo` or `seed`, and an experiment run must not be graded twice
    or charged against that spend cap.
    """
    return {
        "configurable": {
            "thread_id": f"eval-{ticket['id']}-{uuid.uuid4().hex[:8]}",
            "use_cache": False,
            "retrieval_mode": retrieval_mode,
        },
        "metadata": {
            "ticket_id": ticket["id"],
            "api_version": ticket["api_version"],
            "area": ticket["product_area"],
            "retrieval_mode": retrieval_mode,
        },
        "tags": ["eval"],
        "run_name": f"eval-{ticket['id']}",
        # Two retrieval passes fan out three searches each, then draft, then a
        # guardrail retry. The default of 25 is enough today and the ceiling is
        # here so a planner that loops forever fails the example rather than the
        # experiment.
        "recursion_limit": 50,
    }


def run_full_graph(inputs: dict, retrieval_mode: str = "hybrid") -> dict:
    """Invoke the parent graph to the review interrupt and read final state.

    `invoke` returns the interrupt payload, not the state, so the state comes
    from `get_state(config).values` afterwards.
    """
    ticket = _ticket_of(inputs)
    graph = get_graph()
    config = _config(ticket, retrieval_mode)

    result = graph.invoke({"ticket": ticket}, config)
    reached_review = "__interrupt__" in result

    values = graph.get_state(config).values
    stats = values.get("retrieval_stats")

    return {
        "disposition": values.get("disposition"),
        "draft": values.get("draft"),
        "relevant_doc_ids": [d["doc_id"] for d in values.get("relevant_docs") or []],
        "retrieval_stats": stats,
        "guardrail_flags": values.get("guardrail_flags") or [],
        # The eval never resumes past the interrupt, so a non-None `sent` would
        # mean the graph sent an answer with no human in the loop.
        "sent": values.get("sent"),
        "reached_review": reached_review,
    }


def run_retrieval_only(inputs: dict, retrieval_mode: str = "hybrid") -> dict:
    """Run the retrieval subgraph alone against one ticket.

    No checkpointer and no parent state. `run_retrieval` takes the config
    directly, which is where `use_cache=False` and the retrieval mode live.

    Build spec 8.2 writes the signature with no mode argument, but 8.4 asks for
    a `retrieval-semantic-only` experiment, which cannot exist without one. The
    default keeps the documented call shape working unchanged.
    """
    ticket = _ticket_of(inputs)
    config = _config(ticket, retrieval_mode)
    config["run_name"] = f"retrieval-{ticket['id']}"

    result = run_retrieval(ticket, get_kb(), config)
    stats = result["retrieval_stats"]

    return {
        "relevant_doc_ids": [d["doc_id"] for d in result["relevant_docs"]],
        "abstained": stats["abstained"],
        "retrieval_stats": stats,
    }
