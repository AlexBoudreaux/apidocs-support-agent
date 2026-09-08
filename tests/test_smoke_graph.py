"""End-to-end smoke test on `InMemorySaver`. Build spec 4a done-list.

Runs a ticket from intake to the review interrupt, resumes with a decision, and
checks that send and post_send ran and that a second resume is a no-op. No
Postgres, no provider, no network: the KB is built inline and the ServiceNow
calls are monkeypatched.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph import build_graph
from app.kb.index import KnowledgeBase
from app.state import Doc

TICKET = {
    "id": "smoke_001",
    "tenant": "bank-a",
    "api_version": "v3",
    "product_area": "payments",
    "subject": "Refund fails on a payment we authorized but never captured",
    "body": "We call the refund endpoint and get PAY_4012 back every time.",
    "created_at": "2026-09-01T10:00:00Z",
}


def _doc(doc_id: str, route: str, **over) -> Doc:
    base = Doc(
        doc_id=doc_id,
        source="doc",
        route=route,
        version="v3",
        area="payments",
        status="current",
        replaced_by=None,
        error_code=None,
        description="Refund a settled payment. Not for reversing an uncaptured authorization.",
        url=f"https://docs.example.com/v3/payments/{doc_id}",
        text=f"{route} does a thing. Errors: PAY_4012.",
    )
    base.update(over)  # type: ignore[typeddict-item]
    return base


@pytest.fixture
def kb() -> KnowledgeBase:
    return KnowledgeBase(
        [
            _doc("payments-refund-v3", "/v3/payments/{id}/refund"),
            _doc("payments-reversal-v3", "/v3/payments/{id}/reversal"),
            _doc(
                "payments-errors#PAY_4012",
                "",
                version="all",
                error_code="PAY_4012",
                description="Refund exceeds captured amount.",
            ),
        ]
    )


@pytest.fixture(autouse=True)
def no_servicenow(monkeypatch):
    """Keep the smoke test off Postgres."""
    posted: list[tuple] = []
    monkeypatch.setattr(
        "app.nodes.send.servicenow.post_reply",
        lambda tid, kind, body: (posted.append((tid, kind, body)), True)[1],
    )
    monkeypatch.setattr("app.nodes.post_send.servicenow.mark_status", lambda *a, **k: None)
    return posted


@pytest.fixture
def graph(kb):
    return build_graph(kb, InMemorySaver())


def _config(mode: str = "hybrid") -> dict:
    return {
        "configurable": {
            "thread_id": TICKET["id"],
            "use_cache": True,
            "retrieval_mode": mode,
        },
        "metadata": {
            "ticket_id": TICKET["id"],
            "level": "L1",
            "api_version": TICKET["api_version"],
            "area": TICKET["product_area"],
            "retrieval_mode": mode,
        },
        "tags": ["eval"],
    }


def test_runs_to_the_review_interrupt(graph):
    config = _config()
    result = graph.invoke({"ticket": TICKET}, config)

    assert "__interrupt__" in result, "graph should pause at review"
    payload = result["__interrupt__"][0].value
    assert set(payload) == {
        "ticket",
        "draft",
        "disposition",
        "triage_reason",
        "guardrail_flags",
        "relevant_docs",
        "priority",
        "messages_len",
    }

    values = graph.get_state(config).values
    assert values["disposition"] == "answer"
    assert values["draft"], "the stub drafter should have written something"
    assert values["first_draft"] == values["draft"]
    # Unwritten TypedDict keys are simply absent from state, not None.
    assert values.get("sent") is None


def test_send_fan_out_and_counter_are_real(graph):
    config = _config()
    graph.invoke({"ticket": TICKET}, config)
    stats = graph.get_state(config).values["retrieval_stats"]

    # The planner found an error code and a symptom, so two Send branches ran.
    assert stats["queries_run"] >= 2
    assert set(stats["modes"]) <= {"exact", "semantic"}
    assert 1 <= stats["iterations"] <= 3
    assert stats["abstained"] is False


def test_semantic_only_mode_rewrites_exact_queries(graph):
    config = _config(mode="semantic_only")
    graph.invoke({"ticket": TICKET}, config)
    stats = graph.get_state(config).values["retrieval_stats"]
    assert stats["modes"] and set(stats["modes"]) == {"semantic"}


def test_abstain_when_nothing_is_retrievable():
    graph = build_graph(KnowledgeBase([]), InMemorySaver())
    config = _config()
    graph.invoke({"ticket": TICKET}, config)

    values = graph.get_state(config).values
    assert values["disposition"] == "abstain"
    assert values["priority"] == "high"
    assert values["retrieval_stats"]["abstained"] is True
    assert values["relevant_docs"] == []


def test_chat_turn_routes_through_the_reviewer_agent(graph):
    config = _config()
    graph.invoke({"ticket": TICKET}, config)

    result = graph.invoke(
        Command(resume={"type": "chat", "text": "is backoff available in v2?"}), config
    )
    assert "__interrupt__" in result, "one agent turn, then back to the human"

    values = graph.get_state(config).values
    # Written against the 4a stub agent, which replied without calling a tool, so
    # the turn was exactly two messages. The real agent from 4d looks things up,
    # so a turn is the human message plus a tool call, a tool result, and a reply.
    # What the edge guarantees is one human turn in and an assistant turn out.
    messages = values["messages"]
    assert len(messages) >= 2
    assert messages[0].type == "human"
    assert messages[-1].type == "ai", "the turn ends with the agent talking to the human"
    assert values["pending_human"] is None


def test_approve_runs_send_and_post_send_and_is_idempotent(graph, no_servicenow):
    config = _config()
    graph.invoke({"ticket": TICKET}, config)

    decision = {
        "action": "approve",
        "final_answer": "Use the reversal endpoint, not refund.",
        "human_tag": "fixed_facts",
        "save_to_kb": False,
        "save_to_eval": False,
        "escalation_note": None,
    }
    graph.invoke(Command(resume={"type": "decision", "decision": decision}), config)

    values = graph.get_state(config).values
    assert values["sent"]["kind"] == "answer"
    assert values["edit_score"]["tier"] == 1
    assert len(no_servicenow) == 1

    snapshot = graph.get_state(config)
    assert not snapshot.next, "the graph reached END"

    # A second resume has nothing left to run and must not post again.
    graph.invoke(None, config)
    assert len(no_servicenow) == 1


def test_escalate_at_triage_skips_retrieval_and_drafting(kb, monkeypatch):
    """The one parent edge the stub triage never takes on its own."""
    # build_graph resolves `triage` through app.graph's globals at call time,
    # so patching the name there is enough. No module reload.
    monkeypatch.setattr(
        "app.graph.triage",
        lambda state, config: {
            "disposition": "escalate",
            "triage_reason": "billing dispute with a legal threat",
            "priority": "high",
        },
    )
    graph = build_graph(kb, InMemorySaver())

    config = _config()
    result = graph.invoke({"ticket": TICKET}, config)

    assert "__interrupt__" in result
    values = graph.get_state(config).values
    assert values["disposition"] == "escalate"
    assert values["priority"] == "high"
    assert values.get("draft") is None, "escalate never drafts"
    assert values.get("retrieval_stats") is None, "escalate never retrieves"
