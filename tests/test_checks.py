"""Deterministic guardrail checks. Build spec section 11, the 4d review done-list.

Covers the five cases the done-list names (fake route flagged, real route not
flagged, `sk_live_...` flagged, `Bearer eyJ...` flagged, email flagged, and a gap
report on abstain skipping groundedness) plus the non-obvious properties that
keep the guardrail from flagging every honest draft.

No filesystem and no network. Docs are built inline with `_doc`, the same way
`tests/test_smoke_graph.py` does it, using real corpus routes, urls and error
codes so the tests double as documentation of the domain.
"""

from __future__ import annotations

from app.checks import groundedness, pii_scan, redact
from app.nodes.guardrail import guardrail, route_after_guardrail
from app.state import Doc

# Obviously synthetic. Never a real credential.
FAKE_API_KEY = "sk_live_0000000000000000abcd"
FAKE_JWT = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIwMDAwMDAwMCJ9.c2lnbmF0dXJlZmFrZQ"

REFUND_URL = "https://docs.example.com/v3/payments/refund"


def _doc(doc_id: str, route: str, **over) -> Doc:
    """One corpus-shaped `Doc`, overridable field by field."""
    slug = doc_id.rsplit("-", 1)[0].split("-", 1)[-1]
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
        url=f"https://docs.example.com/v3/payments/{slug}",
        text=f"{route} refunds a captured payment. The 90 day window expires with PAY_4013.",
    )
    base.update(over)  # type: ignore[typeddict-item]
    return base


def _refund_docs() -> list[Doc]:
    """The refund doc, whose body text also names the reversal route."""
    return [
        _doc(
            "payments-refund-v3",
            "/v3/payments/{id}/refund",
            text=(
                "Refund a captured payment within 90 days, otherwise PAY_4013. "
                "To release an authorization that was never captured use "
                "/v3/payments/{id}/reversal instead."
            ),
        )
    ]


# ---------- groundedness ----------


def test_fake_route_is_flagged():
    """A route the docs never mention is flagged, which is the whole point of the check."""
    flags = groundedness("Call /v3/payments/{id}/unrefund to undo it.", _refund_docs())
    assert flags == ["route /v3/payments/{id}/unrefund is not in the retrieved docs"]


def test_real_route_in_the_retrieved_docs_is_not_flagged():
    """A route that is a retrieved doc's own route must pass, or no draft ever ships."""
    assert groundedness("Call /v3/payments/{id}/refund.", _refund_docs()) == []


def test_concrete_path_normalizes_to_the_documented_route():
    """A draft writing a real object id must not be flagged.

    Drafts substitute ids into paths all the time, so without normalization every
    real answer would trip the guardrail.
    """
    draft = "POST /v3/payments/pay_3Kd91xR2/refund"
    assert groundedness(draft, _refund_docs()) == []


def test_route_mentioned_only_in_a_doc_body_is_not_flagged():
    """Groundedness reads the whole doc, not just its `route` field.

    The refund doc legitimately names the reversal route in its text, and a draft
    that follows that pointer is grounded.
    """
    draft = "Use /v3/payments/{id}/reversal because the payment was never captured."
    assert groundedness(draft, _refund_docs()) == []


def test_unknown_url_is_flagged_and_a_retrieved_url_is_not():
    """Deep links are the product, so a link the docs never carried has to be caught."""
    bad = "See https://docs.example.com/v9/made-up-page for details."
    assert groundedness(bad, _refund_docs()) == [
        "url https://docs.example.com/v9/made-up-page is not in the retrieved docs"
    ]

    good = f"See [refund]({REFUND_URL}) for details."
    assert groundedness(good, _refund_docs()) == []


def test_invented_error_code_is_flagged_and_a_real_one_is_not():
    """Made-up error codes are the most convincing hallucination a support draft can carry."""
    docs = _refund_docs()
    assert groundedness("You will get PAY_9999 back.", docs) == [
        "error code PAY_9999 is not in the retrieved docs"
    ]
    assert groundedness("You will get PAY_4013 back.", docs) == []


def test_error_code_from_an_error_table_row_is_not_flagged():
    """Error table rows carry no route, so the code has to be matched from the row itself."""
    docs = [
        _doc(
            "webhooks-errors#WHK_4220",
            "",
            area="webhooks",
            version="all",
            error_code="WHK_4220",
            description="Signature mismatch.",
            url="https://docs.example.com/v3/webhooks/errors",
            text="Signature mismatch. v3 signs with the per endpoint secret.",
        )
    ]
    assert groundedness("A signature mismatch returns WHK_4220.", docs) == []


def test_empty_draft_is_not_flagged():
    """An empty draft has nothing to be ungrounded about, so it short circuits."""
    assert groundedness("", _refund_docs()) == []


# ---------- pii and secrets ----------


def test_stripe_style_secret_key_is_flagged():
    """A provider secret in a draft must never reach a reply."""
    flags = pii_scan(f"Your key {FAKE_API_KEY} is wrong.")
    assert len(flags) == 1
    assert flags[0].startswith("api_key found in text:")


def test_bearer_jwt_is_flagged():
    """A pasted bearer token is the most common credential leak in a support thread."""
    flags = pii_scan(f"Send header Authorization: {FAKE_JWT} and retry.")
    assert len(flags) == 1
    assert flags[0].startswith("api_key found in text:")


def test_email_address_is_flagged():
    """Customer contact details are PII and must not be echoed back through the pipeline."""
    flags = pii_scan("Reply to alice@example.com when the refund clears.")
    assert len(flags) == 1
    assert flags[0].startswith("email found in text:")


def test_flags_mask_the_value_they_report():
    """Flags land in graph state and therefore in the LangSmith trace.

    Reprinting the secret in the flag would leak it into exactly the place the
    check exists to protect.
    """
    for secret in (FAKE_API_KEY, FAKE_JWT, "alice@example.com"):
        flags = pii_scan(f"here it is {secret} ok")
        assert flags, f"expected a flag for {secret[:6]}"
        for flag in flags:
            assert secret not in flag


def test_documentation_url_is_not_flagged_as_pii():
    """`url` detection is deliberately excluded because deep links are the product.

    A regression here would flag every draft the system writes.
    """
    assert pii_scan("See https://docs.example.com/v3/payments/refund") == []


def test_empty_text_scans_clean():
    """The empty draft path is hit on every escalate ticket."""
    assert pii_scan("") == []


# ---------- redact ----------


def test_redact_replaces_the_hit_and_keeps_the_surrounding_text():
    """Intake redacts before anything is stored, and the ticket must stay readable."""
    out = redact(f"Our key {FAKE_API_KEY} stopped working.")
    assert out == "Our key [REDACTED] stopped working."


def test_redact_handles_two_hits_in_one_string():
    """Spans are replaced back to front, so both offsets have to survive the first edit."""
    out = redact("Contact alice@example.com or bob@example.com today.")
    assert out == "Contact [REDACTED] or [REDACTED] today."


def test_redact_leaves_a_clean_string_untouched():
    """Redaction is applied to every ticket body, so it must be a no-op on clean text."""
    clean = "Refunds fail with PAY_4013 on /v3/payments/{id}/refund."
    assert redact(clean) == clean


# ---------- the guardrail node ----------


def test_abstain_skips_the_groundedness_check():
    """A gap report names routes that were searched, not routes that were retrieved.

    Checking it against `relevant_docs` would flag every abstain the system makes.
    """
    draft = "We found nothing about /v3/payments/{id}/refund or PAY_4013."
    state = {"draft": draft, "relevant_docs": [], "guardrail_attempts": 0}

    abstained = guardrail({**state, "disposition": "abstain"}, config={})
    assert abstained["guardrail_flags"] == []

    answered = guardrail({**state, "disposition": "answer"}, config={})
    assert answered["guardrail_flags"], "the same draft is checked when we are answering"


def test_guardrail_counts_attempts_and_raises_priority_on_the_second_failure():
    """One retry, then the flagged draft goes to a human at the top of the queue."""
    state = {
        "draft": "Call /v3/payments/{id}/unrefund.",
        "relevant_docs": _refund_docs(),
        "disposition": "answer",
        "guardrail_attempts": 0,
    }

    first = guardrail(state, config={})
    assert first["guardrail_attempts"] == 1
    assert first["guardrail_flags"]
    assert "priority" not in first, "one bad draft is not an escalation"

    second = guardrail({**state, "guardrail_attempts": 1}, config={})
    assert second["guardrail_attempts"] == 2
    assert second["priority"] == "high"


def test_route_after_guardrail_retries_once_then_hands_over():
    """The retry edge is the only loop in the parent graph, so it must terminate."""
    assert route_after_guardrail({"guardrail_flags": ["bad route"], "guardrail_attempts": 1}) == "draft"
    assert route_after_guardrail({"guardrail_flags": ["bad route"], "guardrail_attempts": 2}) == "review"
    assert route_after_guardrail({"guardrail_flags": [], "guardrail_attempts": 1}) == "review"
