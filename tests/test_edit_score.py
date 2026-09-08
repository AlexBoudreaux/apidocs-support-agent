"""Tier 1 edit scorer. Build spec section 11, "4b and 4e evals".

The four cases the done list names are `test_identical`, `test_reworded`,
`test_route_changed`, and `test_url_added`. The rest guard the two places this
scorer can lie: punctuation stuck to a route, and a deep link whose path looks
like a route the prose never said.
"""

from __future__ import annotations

from app.edit_score import extract_identifiers, tier1

DRAFT = (
    "In v3 a payment can be refunded up to 90 days after capture on "
    "`POST /v3/payments/{id}/refund`. Past that window the call returns "
    "`PAY_4013`. See [refund](https://docs.example.com/v3/payments/refund)."
)


# ---------- the four named cases ----------


def test_identical():
    score = tier1(DRAFT, DRAFT)
    assert score["kind"] == "none"
    assert score["added_identifiers"] == []
    assert score["removed_identifiers"] == []
    assert score["char_delta"] == 0


def test_whitespace_only_is_still_none():
    """A reviewer reflowing a paragraph did not edit the answer."""
    reflowed = DRAFT.replace(". ", ".\n\n")
    assert tier1(DRAFT, reflowed)["kind"] == "none"


def test_reworded():
    final = (
        "You can refund a v3 payment for 90 days after capture, using "
        "`POST /v3/payments/{id}/refund`. After 90 days you get `PAY_4013` back. "
        "The doc is here: [refund](https://docs.example.com/v3/payments/refund)."
    )
    score = tier1(DRAFT, final)
    assert score["kind"] == "style"
    assert score["added_identifiers"] == []
    assert score["removed_identifiers"] == []


def test_route_changed():
    final = DRAFT.replace("/v3/payments/{id}/refund", "/v3/payments/{id}/reversal")
    score = tier1(DRAFT, final)
    assert score["kind"] == "correctness"
    assert score["added_identifiers"] == ["/v3/payments/{id}/reversal"]
    assert score["removed_identifiers"] == ["/v3/payments/{id}/refund"]


def test_url_added():
    final = DRAFT + " Error table: https://docs.example.com/errors/payments"
    score = tier1(DRAFT, final)
    assert score["kind"] == "correctness"
    assert score["added_identifiers"] == ["https://docs.example.com/errors/payments"]
    assert score["removed_identifiers"] == []


# ---------- the ways it could lie ----------


def test_version_swap_is_correctness():
    """Right route, wrong version. The single most expensive miss this system makes."""
    before = "On v2 the refund window is 30 days."
    after = "On v3 the refund window is 30 days."
    score = tier1(before, after)
    assert score["kind"] == "correctness"
    assert score["added_identifiers"] == ["v3"]
    assert score["removed_identifiers"] == ["v2"]


def test_error_code_swap_is_correctness():
    score = tier1("You will see `PAY_4013`.", "You will see `PAY_4012`.")
    assert score["kind"] == "correctness"
    assert score["added_identifiers"] == ["PAY_4012"]
    assert score["removed_identifiers"] == ["PAY_4013"]


def test_trailing_punctuation_does_not_split_a_route():
    """`/v3/payments/{id}/refund.` and `/v3/payments/{id}/refund` are one route."""
    ids = extract_identifiers("Call POST /v3/payments/{id}/refund.")
    assert "/v3/payments/{id}/refund" in ids


def test_url_path_is_not_counted_as_a_route():
    """A deep link ends in something route shaped. Counting it twice makes a
    reviewer who only swapped the link look like they changed the route."""
    ids = extract_identifiers("[refund](https://docs.example.com/v3/payments/refund)")
    assert ids == {"https://docs.example.com/v3/payments/refund"}


def test_version_inside_a_route_is_not_a_bare_version_token():
    ids = extract_identifiers("POST /v3/payments/{id}/refund")
    assert ids == {"/v3/payments/{id}/refund"}


def test_route_case_is_not_a_correctness_edit():
    score = tier1("POST /V3/Payments/{id}/Refund", "POST /v3/payments/{id}/refund")
    assert score["kind"] == "style"


def test_single_word_acronyms_are_not_error_codes():
    ids = extract_identifiers("Send a POST to the API and read the JSON body.")
    assert ids == set()


def test_empty_draft_against_a_written_answer():
    """Escalate tickets pause with `draft=None`, so post_send passes "" in."""
    score = tier1("", "We escalated this to the payments on-call.")
    assert score["kind"] == "style"
    assert score["char_delta"] == len("We escalated this to the payments on-call.")
