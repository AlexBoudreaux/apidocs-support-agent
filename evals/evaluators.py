"""Evaluators. Build spec section 8.3.

Every function takes `(inputs, outputs, reference_outputs)` and returns a dict
LangSmith turns into one feedback column, or `SKIP` to leave the column blank
for that example. Blank matters: scoring correctness 0 on an abstain example
would drag the headline number down for behaviour that is exactly right.

Build spec 8.3 says an evaluator returns `None` to skip. langsmith 0.12.1 does
not accept that; `_format_evaluator_result` raises
`ValueError: Expected a non-empty dict, str, bool, int, float, list,
EvaluationResult, or EvaluationResults. Got None`. An empty `results` list is
the shape that actually means "no feedback for this example".

The judge is hand rolled rather than `openevals.create_llm_as_judge`, so
`calibrate_judge.py` and `run_experiment.py` call the identical function and a
package upgrade cannot silently change what the calibration number means.

Binary, never a 1 to 5 scale. Hamel Husain's point, and the reason is practical:
nobody knows what to do with a 3.

Changed 2026-09-07 (session 4g, build spec 8.3). `disposition` became
`escalate_correct` and the retrieval experiment gained `abstained`. Abstain is a
retrieval question and escalate is a triage question, so each is now scored
where it is decided instead of both being folded into one three-way column that
triage could pre-empt. The key was renamed, not redefined, so the comparison
view cannot silently line up two different definitions.
"""

from __future__ import annotations

import logging

from app import settings
from app.state import CorrectnessVerdict

log = logging.getLogger(__name__)

# "This evaluator has nothing to say about this example." See the module docstring.
SKIP: dict = {"results": []}


# ---------- the judge ----------

JUDGE_SYSTEM = """\
You grade one drafted reply from an API documentation support agent against a \
reference answer written by a human who read the source documentation.

Answer one question: does the draft give the developer the same answer as the \
reference, including the same route and the same API version?

Pass only if ALL of these hold.

1. Every route the draft tells the developer to call matches the route the \
reference tells them to call. A different route is a fail even when the \
surrounding explanation is correct.
2. Every API version the draft attaches to a fact matches the reference. \
Quoting a v2 fact at a v3 ticket, or the reverse, is a fail. This includes \
numbers that differ between versions, such as a time window, a rate limit, or a \
pagination scheme.
3. Every error code the draft names matches the reference's, where the \
reference names one.
4. The draft does not state anything that CONTRADICTS the reference. You are \
not shown the source documentation. You are shown the reference answer, which is \
a human's summary of the answer and not a copy of the doc page, so it is normal \
and correct for a good draft to carry accurate detail the reference leaves out. \
Fail added detail only when the reference says or implies something different: \
the reference says a field is not accepted in that version and the draft tells \
the developer to send it, the reference gives a number and the draft gives \
another, the reference names an event and the draft names a different one.
5. When the reference asks the developer which version they are on, or \
otherwise covers both versions because the ticket did not say, the draft does \
the same. Picking one version and answering it confidently is a fail.

Do NOT fail a draft for any of these.

- Different wording, structure, length, tone, or ordering.
- Extra request fields, response fields, event names, status values, worked \
examples, or procedural steps that the reference simply does not mention. The \
reference is a summary, not the whole doc page, and you cannot tell an accurate \
addition from an invented one without the source. Judge the answer, not the \
coverage.
- Omitting a secondary caveat, as long as the primary answer, route, and \
version are right.
- Markdown links, formatting, or a closing offer to help further.

Return `passed` and a one sentence `reason`. When you fail a draft, the reason \
names the specific route, version, code, or claim that is wrong."""

JUDGE_USER = """\
TICKET
{ticket}

REFERENCE ANSWER
{reference}

DRAFT TO GRADE
{draft}"""


def _judge_model():
    """`MODEL_STRONG` with structured output. Built per call, cheap to construct."""
    return settings.chat_model("strong").with_structured_output(CorrectnessVerdict)


def judge_correctness(ticket_text: str, reference: str, draft: str) -> CorrectnessVerdict:
    """One judge call. Shared by the experiment and the calibration script.

    A draft that does not exist cannot match the reference, and that is a real
    failure rather than a missing datapoint, so it short circuits to a fail
    without spending a model call.
    """
    if not (draft or "").strip():
        return CorrectnessVerdict(passed=False, reason="the pipeline produced no draft")

    return _judge_model().invoke(
        [
            {"role": "system", "content": JUDGE_SYSTEM},
            {
                "role": "user",
                "content": JUDGE_USER.format(
                    ticket=ticket_text, reference=reference, draft=draft
                ),
            },
        ]
    )


def _ticket_text(inputs: dict) -> str:
    """The judge sees the ticket the way the pipeline saw it."""
    ticket = inputs.get("ticket") or {}
    if isinstance(ticket, str):
        return ticket
    return f"subject: {ticket.get('subject', '')}\n\n{ticket.get('body', '')}".strip()


# ---------- end to end evaluators ----------


def correctness(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """LLM judge, scored only where the reference disposition is `answer`.

    Returns `SKIP` on abstain and escalate examples so the column is blank there
    rather than zero. Those examples are graded by `escalate_correct` and, for
    the abstain half, by `abstained` on the retrieval-only experiment.
    """
    if reference_outputs.get("disposition") != "answer":
        return SKIP

    verdict = judge_correctness(
        _ticket_text(inputs),
        reference_outputs.get("reference_answer") or "",
        outputs.get("draft") or "",
    )
    return {
        "key": "correctness",
        "score": 1 if verdict.passed else 0,
        "comment": verdict.reason,
    }


def escalate_correct(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Did triage escalate exactly the tickets that should be escalated?

    Was `disposition`, three-way equality on answer/abstain/escalate. Alex
    narrowed it on 2026-09-07: abstain is a retrieval question and escalate is a
    triage question, so each is scored where it is decided. This column is the
    triage half. The retrieval half is the `abstained` column on the
    retrieval-only experiment, and `traj_abstain_exit` below is its end-to-end
    shadow.

    So an abstain example passes as long as triage did not escalate it, whatever
    retrieval then did with it, and an answer example passes as long as it was
    not escalated. Escalate examples pass only on escalate.

    The key is renamed rather than redefined in place. An experiment run before
    2026-09-07 carries a `disposition` column that means something else, and two
    different definitions under one name in the comparison view is a number
    nobody can read.
    """
    actual = outputs.get("disposition")
    expected = reference_outputs.get("disposition")
    actual_esc = actual == "escalate"
    expected_esc = expected == "escalate"
    return {
        "key": "escalate_correct",
        "score": int(actual_esc == expected_esc),
        "comment": (
            f"expected escalate={expected_esc} (reference {expected}), "
            f"got escalate={actual_esc} (pipeline {actual})"
        ),
    }


# ---------- trajectory evaluators ----------
# Deterministic reads of the target's output dict. No run-tree parsing: the
# same signal, and it survives a LangSmith schema change.


def traj_searched(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Retrieval ran at least one search on every example that should be answered."""
    if reference_outputs.get("disposition") != "answer":
        return SKIP
    stats = outputs.get("retrieval_stats") or {}
    queries = stats.get("queries_run", 0)
    return {
        "key": "traj_searched",
        "score": int(queries >= 1),
        "comment": f"{queries} search branch(es) ran",
    }


def traj_iterations_ok(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """The reflect loop stopped at or under three passes.

    Skipped when retrieval never ran at all, which is the escalate path. There is
    no iteration count to judge and a 1 there would be a free pass.
    """
    stats = outputs.get("retrieval_stats")
    if not stats:
        return SKIP
    iterations = stats.get("iterations", 0)
    return {
        "key": "traj_iterations_ok",
        "score": int(iterations <= 3),
        "comment": f"{iterations} retrieval iteration(s)",
    }


def traj_abstain_exit(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Examples the corpus cannot answer took the subgraph's abstain exit.

    Stricter than `disposition` on purpose. `disposition` would also pass if
    triage happened to escalate the ticket for an unrelated reason; this asserts
    the third retrieval exit is the mechanism that fired.
    """
    if reference_outputs.get("disposition") != "abstain":
        return SKIP
    stats = outputs.get("retrieval_stats") or {}
    abstained = bool(stats.get("abstained"))
    return {
        "key": "traj_abstain_exit",
        "score": int(abstained),
        "comment": "abstain exit taken" if abstained else "retrieval did not abstain",
    }


def traj_no_send_before_review(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Nothing was sent, and the graph did pause for a human.

    The one check that must pass on all 30. A send without a review decision is
    an answer that reached a bank developer with no human in the loop.
    """
    sent = outputs.get("sent")
    reached = bool(outputs.get("reached_review"))
    ok = sent is None and reached
    return {
        "key": "traj_no_send_before_review",
        "score": int(ok),
        "comment": (
            "paused at review, nothing sent"
            if ok
            else f"sent={sent!r} reached_review={reached}"
        ),
    }


E2E_EVALUATORS = [
    correctness,
    escalate_correct,
    traj_searched,
    traj_iterations_ok,
    traj_abstain_exit,
    traj_no_send_before_review,
]


# ---------- retrieval evaluators ----------


def _doc_sets(outputs: dict, reference_outputs: dict) -> tuple[set[str], set[str]]:
    return (
        set(outputs.get("relevant_doc_ids") or []),
        set(reference_outputs.get("expected_doc_ids") or []),
    )


def retrieval_recall(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Fraction of the expected docs that came back.

    An abstain example expects nothing, so an empty result is a perfect recall
    of 1.0 and anything returned is 0.0. That is the correct reading: the
    retriever was asked for documents that do not exist and found none.
    """
    actual, expected = _doc_sets(outputs, reference_outputs)
    if not expected:
        score = 1.0 if not actual else 0.0
        comment = "nothing expected, nothing returned" if not actual else (
            f"nothing expected, returned {sorted(actual)}"
        )
    else:
        hit = actual & expected
        score = len(hit) / len(expected)
        comment = f"found {sorted(hit)}, missed {sorted(expected - actual)}"
    return {"key": "retrieval_recall", "score": score, "comment": comment}


def retrieval_precision(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Fraction of what came back that was actually wanted.

    Empty and empty is 1.0. Returning docs when none were expected is 0.0, which
    the `len(actual & expected) / len(actual)` formula gives for free.
    """
    actual, expected = _doc_sets(outputs, reference_outputs)
    if not actual:
        score = 1.0 if not expected else 0.0
        comment = "nothing returned, nothing expected" if not expected else (
            f"nothing returned, expected {sorted(expected)}"
        )
    else:
        hit = actual & expected
        score = len(hit) / len(actual)
        comment = f"kept {sorted(hit)}, noise {sorted(actual - expected)}"
    return {"key": "retrieval_precision", "score": score, "comment": comment}


def abstained(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Did the subgraph take the abstain exit exactly on the examples with no docs?

    Added 2026-09-07. Alex's call: abstain is a retrieval decision, so it is
    measured on the retrieval subgraph alone rather than inferred from an
    end-to-end disposition that triage can pre-empt before retrieval ever runs.

    The reference is `expected_doc_ids == []`, which is what an abstain example
    looks like in the retrieval dataset. So it scores on all 27 examples, not a
    subset: an abstain example passes when the subgraph abstains, and an answer
    example passes when it does not. Recall and precision are unchanged and
    still say whether the right documents came back; this says whether the
    subgraph knew it had nothing.
    """
    expected_none = not (reference_outputs.get("expected_doc_ids") or [])
    actual = bool(outputs.get("abstained"))
    return {
        "key": "abstained",
        "score": int(actual == expected_none),
        "comment": (
            f"expected abstain={expected_none} "
            f"({'no docs expected' if expected_none else 'docs expected'}), "
            f"got abstain={actual}"
        ),
    }


RETRIEVAL_EVALUATORS = [retrieval_recall, retrieval_precision, abstained]
