"""`KnowledgeBase` and the loader, against the real corpus on disk. 4c done-list.

Two halves.

The loader half is pure file reading and runs anywhere. `test_loader_counts` is
the regression guard on the loader reading `kb/docs/`, `kb/errors/` and
`kb/approved/` and nothing else: `kb/CORPUS.md` and `kb/FACTSHEET.md` sit at the
`kb/` root, name every route in the corpus, and print the list of words the
corpus is deliberately silent on, so a `kb/**/*.md` glob would poison retrieval
and make all six abstain examples fail in a way that looks like a model problem.

The semantic half embeds 52 descriptions with the real provider, because "does
the vector store rank reversal above refund for an uncaptured payment" is only a
meaningful question about the real embedding model. Those tests skip without an
`OPENAI_API_KEY`. The KB is session-scoped so the corpus is embedded once.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

from app import settings
from app.kb.index import KnowledgeBase, _normalize_route
from app.kb.loader import CorpusError, load_kb

CORPUS = Path(__file__).resolve().parent.parent / "kb"

needs_provider = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="embeds the corpus with the real provider",
)


@pytest.fixture(scope="session")
def docs():
    return load_kb(CORPUS)


@pytest.fixture(scope="session")
def kb(docs) -> KnowledgeBase:
    return KnowledgeBase(docs)


# ---------- loader ----------


def test_loader_counts(docs):
    """52 Docs from the committed corpus, and nothing from the two files at the kb/ root.

    `kb/approved/` is also the answer cache's write path: post_send drops an
    `approved-<ticket_id>.md` in there on every approval with "save to KB"
    ticked, and `reset_demo.py` does not clean it. So the committed count is
    pinned exactly and runtime approvals are subtracted out, rather than
    hard-coding a total that a single demo run invalidates.
    """
    route_docs = [d for d in docs if d["source"] == "doc" and not d["error_code"]]
    error_rows = [d for d in docs if d["error_code"]]
    approved = [d for d in docs if d["source"] == "approved_answer"]
    runtime = [d for d in approved if d["doc_id"] != "approved-seed-001"]

    assert len(route_docs) == 35
    assert len(error_rows) == 16
    assert len(approved) - len(runtime) == 1, "the committed seed answer is missing"
    assert len(docs) - len(runtime) == 52

    for doc in docs:
        assert "CORPUS" not in doc["doc_id"], f"{doc['doc_id']} came from kb/CORPUS.md"
        assert "FACTSHEET" not in doc["doc_id"], f"{doc['doc_id']} came from kb/FACTSHEET.md"


def test_load_from_a_wrong_root_raises(tmp_path):
    """A wrong KB_ROOT must not present as a system that abstains on everything."""
    with pytest.raises(CorpusError, match="KB_ROOT"):
        load_kb(tmp_path)


def test_error_rows_carry_bare_codes(docs):
    """The tables render codes in backticks; the loader strips them."""
    codes = {d["error_code"] for d in docs if d["error_code"]}
    assert {"PAY_4012", "PAY_4013", "PAY_4090", "WHK_4220", "RATE_LIMITED"} <= codes


# ---------- exact index ----------


def test_exact_hit_on_route_and_version(kb):
    hits = kb.exact("/v3/payments/{id}/refund", "v3", use_cache=False)
    assert [d["doc_id"] for d in hits] == ["payments-refund-v3"]
    assert "90" in hits[0]["text"], "the v3 refund window is the fact this doc exists for"


def test_exact_is_version_scoped(kb):
    v2 = kb.exact("/v2/payments/{id}/refund", "v2", use_cache=False)
    assert [d["doc_id"] for d in v2] == ["payments-refund-v2"]
    assert kb.exact("/v2/payments/{id}/refund", "v3") == []


def test_route_collision(kb):
    """`(route, version)` is not unique, so `exact` returns a list. Build spec 5.1."""
    hits = {d["doc_id"] for d in kb.exact("/v3/payments", "v3", use_cache=False)}
    assert hits == {"payments-create-v3", "payments-list-v3"}

    webhooks = {d["doc_id"] for d in kb.exact("/v2/webhooks/endpoints", "v2")}
    assert webhooks == {"webhooks-endpoints-create-v2", "webhooks-endpoints-list-v2"}


def test_exact_tolerates_a_loosely_written_route(kb):
    """The planner writes routes by hand, so the fallback normalizes them."""
    for written in (
        "POST /v3/payments/{id}/refund",
        "/payments/{id}/refund",
        "/v3/payments/:id/refund",
        "/v3/payments/{payment_id}/refund/",
    ):
        hits = kb.exact(written, "v3", use_cache=False)
        assert [d["doc_id"] for d in hits] == ["payments-refund-v3"], written


def test_normalize_route_drops_verb_version_and_param_name():
    assert _normalize_route("POST /v3/payments/{payment_id}/refund?x=1") == "/payments/{id}/refund"
    assert _normalize_route("/v2/webhooks/deliveries/:id/retry") == "/webhooks/deliveries/{id}/retry"


def test_deprecated_route_returns_the_deprecation_doc(kb):
    hits = kb.exact("/v3/payments/{id}/void", "v3")
    assert [d["doc_id"] for d in hits] == ["payments-void-v3"]
    assert hits[0]["status"] == "deprecated"
    assert hits[0]["replaced_by"] == "/v3/payments/{id}/reversal"


def test_by_error_code(kb):
    """Near-miss on codes: 4012 is the amount, 4013 is the window."""
    amount = kb.by_error_code("PAY_4012")
    window = kb.by_error_code("PAY_4013")
    assert [d["doc_id"] for d in amount] == ["payments-errors#PAY_4012"]
    assert [d["doc_id"] for d in window] == ["payments-errors#PAY_4013"]
    assert "amount" in amount[0]["text"].lower()
    assert "window" in window[0]["text"].lower()


def test_by_error_code_is_forgiving_about_formatting(kb):
    assert kb.by_error_code(" `pay_4012` ") == kb.by_error_code("PAY_4012")


def test_shared_error_code_returns_both_areas(kb):
    hits = {d["doc_id"] for d in kb.by_error_code("RATE_LIMITED")}
    assert hits == {"payments-errors#RATE_LIMITED", "webhooks-errors#RATE_LIMITED"}


def test_unknown_lookups_return_empty(kb):
    assert kb.exact("/v3/payments/{id}/teleport", "v3") == []
    assert kb.by_error_code("PAY_9999") == []


# ---------- the answer cache flag ----------


def test_use_cache_flag_on_the_exact_index(kb):
    """The seed approved answer shares the v3 refund key. `use_cache` separates them."""
    with_cache = [d["doc_id"] for d in kb.exact("/v3/payments/{id}/refund", "v3")]
    without = [d["doc_id"] for d in kb.exact("/v3/payments/{id}/refund", "v3", use_cache=False)]

    assert "approved-seed-001" in with_cache
    assert "payments-refund-v3" in with_cache
    assert without == ["payments-refund-v3"]


def test_the_seed_answer_is_pinned_to_v3(kb, docs):
    seed = next(d for d in docs if d["doc_id"] == "approved-seed-001")
    assert seed["source"] == "approved_answer"
    assert (seed["route"], seed["version"]) == ("/v3/payments/{id}/refund", "v3")
    # Version pin: a v2 ticket must never see an answer written against v3.
    assert "approved-seed-001" not in {d["doc_id"] for d in kb.exact(seed["route"], "v2")}


# ---------- semantic index ----------


@needs_provider
def test_semantic_ranks_reversal_above_refund(kb):
    """Near-miss pair B. The whole reason the descriptions say what they are not for."""
    hits = kb.semantic(
        "reverse a payment we haven't captured",
        version="v3",
        area="payments",
        k=4,
        use_cache=False,
    )
    ids = [d["doc_id"] for d in hits]
    assert "payments-reversal-v3" in ids
    assert ids.index("payments-reversal-v3") < ids.index("payments-refund-v3")


@needs_provider
def test_semantic_respects_the_version_filter(kb):
    hits = kb.semantic("how do I page through a list of payments", version="v2", k=6)
    versions = {d["version"] for d in hits}
    assert versions <= {"v2", "all"}, "a v3 doc leaked into a v2 search"
    assert "payments-list-v2" in {d["doc_id"] for d in hits}


@needs_provider
def test_semantic_respects_the_area_filter(kb):
    hits = kb.semantic("retry a failed delivery", version="v3", area="webhooks", k=6)
    assert {d["area"] for d in hits} == {"webhooks"}


@needs_provider
def test_semantic_use_cache_false_hides_the_approved_answer(kb):
    query = "how long do I have to refund a payment"
    cached = {d["doc_id"] for d in kb.semantic(query, version="v3", k=8, use_cache=True)}
    clean = {d["doc_id"] for d in kb.semantic(query, version="v3", k=8, use_cache=False)}

    assert "approved-seed-001" in cached, "the cache demo needs this hit"
    assert "approved-seed-001" not in clean


@needs_provider
def test_semantic_returns_nothing_for_an_empty_query(kb):
    assert kb.semantic("   ", version="v3") == []


@needs_provider
def test_add_approved_answer_reaches_both_indexes(docs):
    """post_send's write path. New answer, exact hit and semantic hit, same call."""
    fresh = KnowledgeBase(docs)
    new = dict(docs[0])
    new.update(
        doc_id="approved-t_999",
        source="approved_answer",
        route="/v3/webhooks/deliveries/{id}/retry",
        version="v3",
        area="webhooks",
        error_code=None,
        description="Why did my webhook delivery stop retrying after five attempts",
        text="Deliveries stop after 5 attempts and are marked failed. Use the retry route.",
    )
    fresh.add_approved_answer(new)  # type: ignore[arg-type]

    assert "approved-t_999" in fresh.all_doc_ids()
    exact = {d["doc_id"] for d in fresh.exact("/v3/webhooks/deliveries/{id}/retry", "v3")}
    assert "approved-t_999" in exact

    semantic = {
        d["doc_id"]
        for d in fresh.semantic(
            "delivery stopped retrying after five attempts", version="v3", k=8
        )
    }
    assert "approved-t_999" in semantic


def test_all_doc_ids_matches_the_corpus(kb, docs):
    assert kb.all_doc_ids() == {d["doc_id"] for d in docs}
    assert len(kb.all_doc_ids()) >= 52


def test_settings_kb_root_points_at_the_corpus():
    assert settings.KB_ROOT.resolve() == CORPUS.resolve()


# ---------- the lazy vector store under the Send fan-out ----------


class _CountingEmbeddings(Embeddings):
    """Deterministic, offline, and counts how many times it was asked to embed."""

    def __init__(self) -> None:
        self.batches = 0

    def _vector(self, text: str) -> list[float]:
        seed = sum(ord(c) for c in text.lower())
        return [((seed >> i) & 0xFF) / 255.0 for i in range(8)]

    def embed_documents(self, texts):
        self.batches += 1
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


def test_the_corpus_is_embedded_once_in_one_batch(docs):
    fake = _CountingEmbeddings()
    kb = KnowledgeBase(docs, embeddings=fake)

    assert fake.batches == 0, "constructing a KnowledgeBase must not call the provider"
    kb.semantic("anything", version="v3")
    kb.semantic("anything else", version="v3")
    assert fake.batches == 1, "one batched call for the whole corpus, then never again"


def test_concurrent_first_searches_all_see_a_filled_index(docs):
    """The `Send` fan-out reaches the lazy build from several threads at once.

    Without the lock one branch saw a store that existed but had not been filled
    and silently returned nothing, which reads downstream as "the docs do not
    cover this" rather than as a bug.
    """
    fake = _CountingEmbeddings()
    kb = KnowledgeBase(docs, embeddings=fake)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda i: kb.semantic(f"refund window {i}", version="v3", k=4), range(8))
        )

    assert all(len(r) == 4 for r in results), "a branch searched an empty index"
    assert fake.batches == 1
