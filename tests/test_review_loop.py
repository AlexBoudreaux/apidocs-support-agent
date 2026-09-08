"""The 4d edges, with no model in the loop. Build spec section 11, "4d review".

Three behaviours here are edges rather than functions, so they are tested through
the compiled graph on `InMemorySaver` with the drafter and the reviewer agent
swapped for scripted fakes.

1. The guardrail retry. A flagged first draft goes back to the drafter with the
   flags in hand, and a clean second draft reaches review. Two failures reach
   review at high priority instead of looping.
2. The two-node review loop. A chat turn runs `reviewer_agent` once and comes
   back to a fresh interrupt, and nothing from the earlier turn replays.
3. Send's PII re-check. An approved answer carrying an email routes back to
   review with the flag rather than posting.

The drafter is faked rather than called for real because the point of the retry
test is the edge and the flag hand-off. Asking a real model to write a bad draft
on purpose and a good one second makes the test a coin flip.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph import build_graph
from app.kb.index import KnowledgeBase
from app.state import Doc

TICKET = {
    "id": "loop_001",
    "tenant": "bank-a",
    "api_version": "v3",
    "product_area": "payments",
    "subject": "Refund rejected on an older payment",
    "body": "We get PAY_4013 back on payments from four months ago.",
    "created_at": "2026-09-01T10:00:00Z",
}

# `/v3/payments/{id}/annul` does not exist in the corpus, which is what makes it
# a groundedness failure. The clean draft cites only the doc below.
BAD_DRAFT = "Call POST /v3/payments/{id}/annul instead. See https://docs.example.com/v9/fake"
GOOD_DRAFT = (
    "The 90 day v3 refund window has passed, so PAY_4013 is expected.\n"
    "[POST /v3/payments/{id}/refund](https://docs.example.com/v3/payments/refund)"
)


def _doc() -> Doc:
    return Doc(
        doc_id="payments-refund-v3",
        source="doc",
        route="/v3/payments/{id}/refund",
        version="v3",
        area="payments",
        status="current",
        replaced_by=None,
        error_code=None,
        description="Refund a settled payment in full or in part.",
        url="https://docs.example.com/v3/payments/refund",
        text="POST /v3/payments/{id}/refund refunds within 90 days. Errors: PAY_4013.",
    )


def _config() -> dict:
    return {
        "configurable": {
            "thread_id": TICKET["id"],
            "use_cache": True,
            "retrieval_mode": "hybrid",
        },
        "tags": ["eval"],
    }


@pytest.fixture
def kb() -> KnowledgeBase:
    return KnowledgeBase([_doc()])


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch):
    """Keep the graph off Postgres, off LangSmith, and off the provider."""
    posted: list[tuple] = []
    monkeypatch.setattr(
        "app.nodes.send.servicenow.post_reply",
        lambda tid, kind, body: (posted.append((tid, kind, body)), True)[1],
    )
    monkeypatch.setattr("app.nodes.post_send.servicenow.mark_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.nodes.triage.triage",
        lambda state, config: {
            "disposition": "answer",
            "triage_reason": "scripted",
            "priority": "normal",
        },
    )
    # build_graph resolves `triage` through app.graph's globals at call time.
    monkeypatch.setattr(
        "app.graph.triage",
        lambda state, config: {
            "disposition": "answer",
            "triage_reason": "scripted",
            "priority": "normal",
        },
    )
    return posted


def _script_drafter(monkeypatch, drafts: list[str]) -> list[dict]:
    """Replace the drafter with a scripted sequence and record what it was told."""
    calls: list[dict] = []

    def fake(ticket, docs, disposition, flags=None, instruction=None, prior_draft=None):
        calls.append({"flags": flags, "instruction": instruction})
        return drafts[min(len(calls) - 1, len(drafts) - 1)]

    monkeypatch.setattr("app.nodes.draft.write_draft", fake)
    return calls


def test_guardrail_retry_passes_the_flags_and_the_second_draft_is_clean(kb, monkeypatch):
    """The retry is a correction, not a reroll, so the flags must reach the prompt."""
    calls = _script_drafter(monkeypatch, [BAD_DRAFT, GOOD_DRAFT])
    graph = build_graph(kb, InMemorySaver())
    config = _config()

    result = graph.invoke({"ticket": TICKET}, config)
    values = graph.get_state(config).values

    assert "__interrupt__" in result
    assert len(calls) == 2, "one flagged attempt, one retry"
    assert calls[0]["flags"] is None, "the first attempt has nothing to fix yet"
    assert calls[1]["flags"], "the retry is told why the first attempt was rejected"
    assert any("annul" in flag for flag in calls[1]["flags"])
    assert values["draft"] == GOOD_DRAFT
    assert values["guardrail_flags"] == [], "the second draft is clean"
    assert values["guardrail_attempts"] == 2
    assert values["priority"] == "normal"
    assert values["first_draft"] == BAD_DRAFT, "first_draft is pinned once and never moves"


def test_two_failures_reach_the_human_at_high_priority(kb, monkeypatch):
    """Two failures means something a third attempt will not fix."""
    calls = _script_drafter(monkeypatch, [BAD_DRAFT])
    graph = build_graph(kb, InMemorySaver())
    config = _config()

    graph.invoke({"ticket": TICKET}, config)
    values = graph.get_state(config).values

    assert len(calls) == 2, "exactly one retry, then the human"
    assert values["guardrail_flags"], "the flags are visible in the UI"
    assert values["guardrail_attempts"] == 2
    assert values["priority"] == "high"


def test_a_chat_turn_runs_one_agent_turn_and_replays_nothing(kb, monkeypatch):
    """`interrupt()` re-runs its node from the top, which is why the agent is its own node."""
    _script_drafter(monkeypatch, [GOOD_DRAFT])
    turns: list[int] = []

    class _Agent:
        def invoke(self, payload, config=None):
            turns.append(len(payload["messages"]))
            return {"messages": [*payload["messages"], AIMessage("v2 is 30 days.")]}

    monkeypatch.setattr("app.nodes.review.build_reviewer_agent", lambda ctx: _Agent())
    graph = build_graph(kb, InMemorySaver())
    config = _config()
    graph.invoke({"ticket": TICKET}, config)

    for text in ("what about v2?", "and the deprecated void route?"):
        result = graph.invoke(Command(resume={"type": "chat", "text": text}), config)
        assert "__interrupt__" in result, "back to the human after one agent turn"

    values = graph.get_state(config).values
    assert turns == [1, 3], "each turn sees the history once, and no turn is re-run"
    assert len(values["messages"]) == 4
    assert values["pending_human"] is None


def test_send_bounces_an_approved_answer_that_carries_an_email(kb, monkeypatch, no_side_effects):
    """The last PII check runs on whatever the human approved, not on what we drafted."""
    _script_drafter(monkeypatch, [GOOD_DRAFT])
    graph = build_graph(kb, InMemorySaver())
    config = _config()
    graph.invoke({"ticket": TICKET}, config)

    decision = {
        "action": "approve",
        "final_answer": "Mail ops-lead@bank-a.example.com about it.",
        "human_tag": "fixed_wording",
        "save_to_kb": False,
        "save_to_eval": False,
        "escalation_note": None,
    }
    result = graph.invoke(Command(resume={"type": "decision", "decision": decision}), config)

    values = graph.get_state(config).values
    assert "__interrupt__" in result, "back to review rather than out to the customer"
    assert no_side_effects == [], "nothing was posted"
    assert values.get("sent") is None
    assert any("email" in flag for flag in values["guardrail_flags"])
    assert "ops-lead@bank-a.example.com" not in str(values["guardrail_flags"]), (
        "the flag names the category and masks the value, because flags reach the trace"
    )
