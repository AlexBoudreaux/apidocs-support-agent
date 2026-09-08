"""LangSmith feedback writes. Session 4g fix 1.

The bug this file exists to stop: `write_edit_feedback` passed both `run_id` and
`project_id` to `create_feedback`, langsmith 0.12.1 raised
`ValueError: project_id cannot be provided if run_id or trace_id is provided`,
the blanket `except` swallowed it, and the next log line said the write landed.
Three feedbacks that never existed read as a healthy flywheel for three days.

So `FakeClient.create_feedback` reproduces the SDK's own argument validation
rather than accepting anything. A test that only counts calls would have passed
on the broken code.
"""

from __future__ import annotations

import logging

import pytest

from app.integrations import langsmith_feedback as lf
from app.state import EditScore

SCORE: EditScore = {
    "tier": 1,
    "kind": "correctness",
    "added_identifiers": ["/v3/payments/{id}/refund"],
    "removed_identifiers": ["/v2/payments/{id}/refund"],
    "char_delta": 12,
}

RUN_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"


class FakeProject:
    id = SESSION_ID


class FakeClient:
    """Enough of `langsmith.Client` to exercise the argument shape.

    `create_feedback` mirrors langsmith 0.12.1's validation exactly: `run_id` or
    `trace_id` together with `project_id` is a `ValueError`, and `session_id` is
    the argument that names the owning project.
    """

    def __init__(self, fail_keys: set[str] | None = None):
        self.calls: list[dict] = []
        self.fail_keys = fail_keys or set()

    def read_project(self, project_name: str):
        return FakeProject()

    def create_feedback(self, **kwargs):
        run_id = kwargs.get("run_id") or kwargs.get("trace_id")
        if run_id is None and kwargs.get("project_id") is None:
            raise ValueError("One of run_id, trace_id, or project_id  must be provided")
        if run_id is not None and kwargs.get("project_id") is not None:
            raise ValueError(
                "project_id cannot be provided if run_id or trace_id is provided"
            )
        if kwargs["key"] in self.fail_keys:
            raise RuntimeError(f"boom on {kwargs['key']}")
        self.calls.append(kwargs)


@pytest.fixture
def client(monkeypatch):
    """A fresh fake client, with the per-process session id cache cleared."""
    fake = FakeClient()
    monkeypatch.setattr(lf, "_client", lambda: fake)
    lf._session_id.cache_clear()
    yield fake
    lf._session_id.cache_clear()


def test_writes_all_three_keys(client):
    lf.write_edit_feedback(RUN_ID, SCORE, "fixed_facts", disposition_miss=False)

    assert [c["key"] for c in client.calls] == [
        "edit_tier",
        "human_tag",
        "disposition_miss",
    ]


def test_carries_session_id_and_never_project_id(client):
    """The exact regression. `project_id` alongside `run_id` is what broke."""
    lf.write_edit_feedback(RUN_ID, SCORE, "good_as_is", disposition_miss=False)

    assert len(client.calls) == 3
    for call in client.calls:
        assert call["run_id"] == RUN_ID
        assert call["session_id"] == SESSION_ID
        assert "project_id" not in call


def test_scores_match_the_spec_table(client):
    lf.write_edit_feedback(RUN_ID, SCORE, "good_as_is", disposition_miss=True)

    by_key = {c["key"]: c for c in client.calls}
    assert by_key["edit_tier"]["score"] == 2      # correctness
    assert by_key["edit_tier"]["value"] == "correctness"
    assert by_key["human_tag"]["score"] == 1      # good_as_is
    assert by_key["disposition_miss"]["score"] == 1


def test_a_raising_create_feedback_is_not_reported_as_success(client, caplog):
    """The done-list item: this test must fail if `create_feedback` raises.

    It fails two ways. No successful write is recorded, and the success log line
    is absent while an error line names the key that failed.
    """
    client.fail_keys = {"human_tag"}

    with caplog.at_level(logging.INFO, logger=lf.log.name):
        lf.write_edit_feedback(RUN_ID, SCORE, "fixed_wording", disposition_miss=False)

    assert [c["key"] for c in client.calls] == ["edit_tier", "disposition_miss"]

    messages = [r.getMessage() for r in caplog.records]
    assert not any("wrote edit_tier" in m for m in messages)

    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("human_tag" in m for m in errors)


def test_every_write_failing_still_does_not_log_success(client, caplog):
    client.fail_keys = {"edit_tier", "human_tag", "disposition_miss"}

    with caplog.at_level(logging.INFO, logger=lf.log.name):
        lf.write_edit_feedback(RUN_ID, SCORE, "good_as_is", disposition_miss=False)

    assert client.calls == []
    assert not any("wrote edit_tier" in r.getMessage() for r in caplog.records)


def test_no_run_id_is_a_skip_not_a_failure(client, caplog):
    """Tracing off is not an error. It must not page anyone."""
    with caplog.at_level(logging.INFO, logger=lf.log.name):
        lf.write_edit_feedback("", SCORE, "good_as_is", disposition_miss=False)

    assert client.calls == []
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)
