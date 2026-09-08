"""search. One `Send` branch per query. Owner is session 4c. Build spec section 4.2.

Reads the `Send` payload and `config`. Writes `results` (append) and `modes`
(append), both `operator.add` reducers because the branches run concurrently in
one superstep.

No model call, in any mode. Routing is a `match` on a structured `SearchQuery`,
which is what makes exact-versus-semantic testable with no LLM in the loop
(`tests/test_planner_routing.py`). Every branch catches everything: one failed
branch in a `Send` fan-out fails the whole superstep otherwise.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from app.kb.index import KnowledgeBase
from app.state import SearchQuery

log = logging.getLogger(__name__)


def make_search(kb: KnowledgeBase):
    """Close the search node over the process-wide `KnowledgeBase`."""

    def search(state: dict, config: RunnableConfig) -> dict:
        """Run one `SearchQuery` against the exact or the semantic index."""
        configurable = config.get("configurable", {})
        use_cache = configurable.get("use_cache", True)
        retrieval_mode = configurable.get("retrieval_mode", "hybrid")

        query: SearchQuery = state["query"]
        ticket = state["ticket"]

        # The ablation: exact queries get rewritten into semantic ones whose text
        # is the route or error code string. This is what the second experiment
        # measures, so it is a real branch, not a config no-op.
        if retrieval_mode == "semantic_only" and query.mode == "exact":
            query = SearchQuery(
                mode="semantic",
                text=query.route or query.error_code or ticket["subject"],
                version=query.version,
            )

        try:
            if query.mode == "exact" and query.route:
                docs = kb.exact(query.route, query.version or ticket["api_version"], use_cache)
            elif query.mode == "exact" and query.error_code:
                docs = kb.by_error_code(query.error_code, use_cache)
            elif query.mode == "semantic":
                area = ticket["product_area"]
                docs = kb.semantic(
                    query.text or ticket["subject"],
                    version=query.version,
                    area=None if area == "unknown" else area,
                    k=4,
                    use_cache=use_cache,
                )
            else:
                docs = []
        except Exception:
            log.exception("search branch failed for query %r", query)
            return {"results": [], "modes": [query.mode]}

        log.info("search %s -> %d docs", query.mode, len(docs))
        return {"results": docs, "modes": [query.mode]}

    return search
