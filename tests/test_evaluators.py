"""The two evaluator definitions Alex changed on 2026-09-07. Session 4g fix 3.

Hand-built inputs only, no LLM and no LangSmith. Both functions are pure code,
which is the point of scoring them where they are decided.

`escalate_correct` replaces `disposition`: pass when the pipeline escalated
exactly the tickets the reference escalates. `abstained` is new on the
retrieval-only experiment: pass when the subgraph's abstain flag matches
`expected_doc_ids == []`.
"""

from __future__ import annotations

import pytest

from evals.evaluators import (
    E2E_EVALUATORS,
    RETRIEVAL_EVALUATORS,
    abstained,
    escalate_correct,
)

# ---------- escalate_correct, the triage half ----------

# (reference disposition, pipeline disposition, expected score)
ESCALATE_CASES = [
    # Escalate examples pass only on escalate.
    ("escalate", "escalate", 1),
    ("escalate", "answer", 0),
    ("escalate", "abstain", 0),
    # An answer example passes as long as it was not escalated.
    ("answer", "answer", 1),
    ("answer", "abstain", 1),
    ("answer", "escalate", 0),
    # An abstain example passes as long as triage did not escalate it, whatever
    # retrieval then did. This is the case the rename exists for: under the old
    # `disposition` column, (abstain, answer) scored 0 and blamed triage for a
    # retrieval decision.
    ("abstain", "abstain", 1),
    ("abstain", "answer", 1),
    ("abstain", "escalate", 0),
]


@pytest.mark.parametrize("reference,actual,expected", ESCALATE_CASES)
def test_escalate_correct(reference, actual, expected):
    result = escalate_correct(
        inputs={"ticket": {"subject": "s", "body": "b"}},
        outputs={"disposition": actual},
        reference_outputs={"disposition": reference},
    )
    assert result["key"] == "escalate_correct"
    assert result["score"] == expected


def test_escalate_correct_is_not_the_old_disposition_column():
    """The one row where the new definition and the old one disagree."""
    old_score = int("answer" == "abstain")  # what `disposition` scored
    new = escalate_correct({}, {"disposition": "answer"}, {"disposition": "abstain"})
    assert old_score == 0
    assert new["score"] == 1


def test_escalate_correct_scores_a_missing_disposition_as_not_escalated():
    """A pipeline that fell over produced no disposition. That is not an escalate."""
    assert escalate_correct({}, {}, {"disposition": "answer"})["score"] == 1
    assert escalate_correct({}, {}, {"disposition": "escalate"})["score"] == 0


def test_disposition_key_is_gone_from_the_e2e_list():
    """Old and new experiments must not share a column name. Build spec 8.3."""
    keys = [f.__name__ for f in E2E_EVALUATORS]
    assert "escalate_correct" in keys
    assert "disposition" not in keys


# ---------- abstained, the retrieval half ----------

# (expected_doc_ids, subgraph abstained flag, expected score)
ABSTAIN_CASES = [
    # An abstain example expects no docs. It passes when the subgraph abstains.
    ([], True, 1),
    ([], False, 0),
    # An answer example expects docs. It passes when the subgraph does not abstain.
    (["payments-refund-v3"], False, 1),
    (["payments-refund-v3"], True, 0),
    (["a", "b", "c"], False, 1),
]


@pytest.mark.parametrize("expected_docs,flag,expected", ABSTAIN_CASES)
def test_abstained(expected_docs, flag, expected):
    result = abstained(
        inputs={"ticket": {"subject": "s", "body": "b"}},
        outputs={"relevant_doc_ids": [], "abstained": flag},
        reference_outputs={"expected_doc_ids": expected_docs},
    )
    assert result["key"] == "abstained"
    assert result["score"] == expected


def test_abstained_scores_every_example_and_never_skips():
    """Deterministic on all 27, not a subset. Blank rows would hide the column."""
    for expected_docs in ([], ["x"], None):
        result = abstained(
            {}, {"abstained": False}, {"expected_doc_ids": expected_docs}
        )
        assert result.get("results") != []
        assert result["score"] in (0, 1)


def test_abstained_treats_a_missing_flag_as_not_abstained():
    assert abstained({}, {}, {"expected_doc_ids": ["x"]})["score"] == 1
    assert abstained({}, {}, {"expected_doc_ids": []})["score"] == 0


def test_abstained_is_in_the_retrieval_list_and_recall_precision_survive():
    keys = [f.__name__ for f in RETRIEVAL_EVALUATORS]
    assert keys == ["retrieval_recall", "retrieval_precision", "abstained"]
