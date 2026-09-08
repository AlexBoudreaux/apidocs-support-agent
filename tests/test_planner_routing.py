"""Routing from `SearchQuery` to index, with no LLM anywhere. 4c done-list.

This is the test the brief's fifth missing-thing exists for: "if plan_query
returns {mode, route, version, error_code, text} instead of a search string,
retrieval becomes unit-testable without an LLM in the loop, and exact-match
versus semantic becomes a real routing decision rather than vibes."

So nothing here calls a model or an embedding. The knowledge base is a recorder
that answers the three lookup methods and remembers how it was called, the
planner is exercised through its pure post-model normalization, and the loop cap
is exercised through the router function directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from langgraph.graph import END

from app.retrieval.planner import MAX_QUERIES, _fallback, _normalize
from app.retrieval.reflect import MAX_ITERATIONS, route_after_reflect
from app.retrieval.search import make_search
from app.retrieval.subgraph import fan_out
from app.state import Doc, SearchQuery, Ticket

TICKET = Ticket(
    id="t_001",
    tenant="bank-a",
    api_version="v3",
    product_area="payments",
    subject="Refund is rejected on a payment we never captured",
    body="We call the refund route and get PAY_4012.",
    created_at="2026-09-01T10:00:00Z",
)


def _doc(doc_id: str) -> Doc:
    return Doc(
        doc_id=doc_id,
        source="doc",
        route="/v3/payments/{id}/refund",
        version="v3",
        area="payments",
        status="current",
        replaced_by=None,
        error_code=None,
        description="Refund a settled payment.",
        url="https://docs.example.com/v3/payments/refund",
        text="POST /v3/payments/{id}/refund. Errors: PAY_4012.",
    )


@dataclass
class RecordingKB:
    """Answers the three `KnowledgeBase` lookups and records every call.

    Duck-typed on purpose: `make_search` only ever calls these three methods, so
    the search node's routing can be asserted without a corpus or a provider.
    """

    calls: list[tuple] = field(default_factory=list)

    def exact(self, route, version, use_cache=True):
        self.calls.append(("exact", route, version, use_cache))
        return [_doc("payments-refund-v3")]

    def by_error_code(self, code, use_cache=True):
        self.calls.append(("by_error_code", code, use_cache))
        return [_doc("payments-errors#PAY_4012")]

    def semantic(self, text, version=None, area=None, k=4, use_cache=True):
        self.calls.append(("semantic", text, version, area, k, use_cache))
        return [_doc("payments-reversal-v3")]


@pytest.fixture
def kb() -> RecordingKB:
    return RecordingKB()


def _config(mode: str = "hybrid", use_cache: bool = True) -> dict:
    return {"configurable": {"retrieval_mode": mode, "use_cache": use_cache}}


def _run(kb: RecordingKB, query: SearchQuery, config: dict | None = None) -> dict:
    return make_search(kb)({"query": query, "ticket": TICKET}, config or _config())


# ---------- SearchQuery -> index ----------


def test_route_query_hits_the_exact_index(kb):
    out = _run(kb, SearchQuery(mode="exact", route="/v3/payments/{id}/refund", version="v3"))

    assert kb.calls == [("exact", "/v3/payments/{id}/refund", "v3", True)]
    assert out["modes"] == ["exact"]
    assert [d["doc_id"] for d in out["results"]] == ["payments-refund-v3"]


def test_error_code_query_hits_the_code_index(kb):
    out = _run(kb, SearchQuery(mode="exact", error_code="PAY_4012", version="v3"))

    assert kb.calls == [("by_error_code", "PAY_4012", True)]
    assert out["modes"] == ["exact"]
    assert [d["doc_id"] for d in out["results"]] == ["payments-errors#PAY_4012"]


def test_route_wins_when_a_query_carries_both(kb):
    """One lookup per branch. The route is the more specific of the two."""
    _run(kb, SearchQuery(mode="exact", route="/v3/payments", error_code="PAY_4012", version="v3"))
    assert len(kb.calls) == 1
    assert kb.calls[0][0] == "exact"


def test_semantic_query_hits_the_vector_index_scoped_to_the_ticket(kb):
    _run(kb, SearchQuery(mode="semantic", text="reverse an uncaptured payment", version="v3"))

    assert kb.calls == [("semantic", "reverse an uncaptured payment", "v3", "payments", 4, True)]


def test_semantic_drops_the_area_filter_when_the_area_is_unknown(kb):
    ticket = dict(TICKET, product_area="unknown")
    make_search(kb)(
        {"query": SearchQuery(mode="semantic", text="429s in sandbox", version="v3"), "ticket": ticket},
        _config(),
    )
    assert kb.calls[0][3] is None, "an unknown area must not filter the corpus to nothing"


def test_exact_query_naming_nothing_returns_no_results(kb):
    out = _run(kb, SearchQuery(mode="exact", version="v3"))

    assert kb.calls == []
    assert out == {"results": [], "modes": ["exact"]}


def test_search_falls_back_to_the_ticket_version(kb):
    """The planner fills the version, but a `Send` payload is not trusted to have it."""
    _run(kb, SearchQuery(mode="exact", route="/v3/payments/{id}/refund"))
    assert kb.calls[0][2] == "v3"


# ---------- the use_cache flag ----------


@pytest.mark.parametrize("use_cache", [True, False])
def test_use_cache_reaches_every_index(kb, use_cache):
    config = _config(use_cache=use_cache)
    _run(kb, SearchQuery(mode="exact", route="/v3/payments", version="v3"), config)
    _run(kb, SearchQuery(mode="exact", error_code="PAY_4012", version="v3"), config)
    _run(kb, SearchQuery(mode="semantic", text="refund window", version="v3"), config)

    assert [call[-1] for call in kb.calls] == [use_cache] * 3


# ---------- the semantic_only ablation ----------


def test_semantic_only_rewrites_a_route_query(kb):
    out = _run(
        kb,
        SearchQuery(mode="exact", route="/v3/payments/{id}/refund", version="v3"),
        _config(mode="semantic_only"),
    )

    assert kb.calls[0][0] == "semantic", "the exact index must not be reachable in this mode"
    assert kb.calls[0][1] == "/v3/payments/{id}/refund", "the route becomes the query text"
    assert out["modes"] == ["semantic"], "stats must show the ablation actually ran"


def test_semantic_only_rewrites_an_error_code_query(kb):
    _run(
        kb,
        SearchQuery(mode="exact", error_code="PAY_4012", version="v3"),
        _config(mode="semantic_only"),
    )
    assert kb.calls[0][:2] == ("semantic", "PAY_4012")


def test_semantic_only_leaves_semantic_queries_alone(kb):
    _run(kb, SearchQuery(mode="semantic", text="429s in sandbox"), _config(mode="semantic_only"))
    assert kb.calls[0][:2] == ("semantic", "429s in sandbox")


def test_hybrid_is_the_default_when_config_says_nothing(kb):
    make_search(kb)(
        {"query": SearchQuery(mode="exact", error_code="PAY_4012", version="v3"), "ticket": TICKET},
        {},
    )
    assert kb.calls[0][0] == "by_error_code"


# ---------- one failing branch cannot fail the superstep ----------


def test_a_raising_index_returns_an_empty_branch():
    class Exploding(RecordingKB):
        def exact(self, route, version, use_cache=True):
            raise RuntimeError("index is on fire")

    out = _run(Exploding(), SearchQuery(mode="exact", route="/v3/payments", version="v3"))
    assert out == {"results": [], "modes": ["exact"]}


# ---------- planner normalization, the part with no model in it ----------


def test_normalize_truncates_to_three():
    plan = [SearchQuery(mode="semantic", text=str(i)) for i in range(7)]
    assert len(_normalize(plan, TICKET)) == MAX_QUERIES


def test_normalize_fills_the_missing_version_from_the_ticket():
    out = _normalize([SearchQuery(mode="exact", route="/v3/payments")], TICKET)
    assert out[0].version == "v3"


def test_normalize_keeps_an_explicit_version():
    out = _normalize([SearchQuery(mode="exact", route="/v2/payments", version="v2")], TICKET)
    assert out[0].version == "v2", "a version-difference ticket needs the other version"


def test_normalize_demotes_an_exact_query_that_names_nothing():
    out = _normalize([SearchQuery(mode="exact", text="refund window")], TICKET)
    assert out[0].mode == "semantic"
    assert out[0].text == "refund window"


def test_fallback_is_one_semantic_query():
    assert [q.mode for q in _fallback(TICKET, None, None)] == ["semantic"]
    assert _fallback(TICKET, None, None)[0].text == TICKET["subject"]
    assert _fallback(TICKET, "the v2 backoff parameter", None)[0].text == "the v2 backoff parameter"
    assert _fallback(TICKET, "missing note", "reviewer hint")[0].text == "reviewer hint"


# ---------- fan-out and the loop cap ----------


def test_fan_out_is_one_send_per_query():
    queries = [
        SearchQuery(mode="exact", route="/v3/payments", version="v3"),
        SearchQuery(mode="semantic", text="uncaptured", version="v3"),
    ]
    sends = fan_out({"ticket": TICKET, "queries": queries})

    assert [s.node for s in sends] == ["search", "search"]
    assert [s.arg["query"] for s in sends] == queries
    assert all(s.arg["ticket"] == TICKET for s in sends)


@pytest.mark.parametrize(
    "decision,iteration,expected",
    [
        ("again", 1, "plan_queries"),
        ("again", 2, "plan_queries"),
        ("again", MAX_ITERATIONS, END),
        ("again", MAX_ITERATIONS + 1, END),
        ("done", 1, END),
        ("abstain", 1, END),
    ],
)
def test_the_edge_enforces_the_cap_not_the_model(decision, iteration, expected):
    assert route_after_reflect({"decision": decision, "iteration": iteration}) == expected
