"""LangSmith feedback writes. Build spec sections 8.6 and 9.

Three feedbacks go on the run at post_send:

| key | score | value | comment |
|---|---|---|---|
| `edit_tier` | 0, 1, 2 for none, style, correctness | the kind, as a string | added and removed identifiers |
| `human_tag` | 1 when `good_as_is`, else 0 | the tag | the tag again, so the run list is readable |
| `disposition_miss` | 1 when the reviewer contradicted the pipeline | bool | which contradiction |

`edit_tier` is numeric on purpose. The dashboard chart in build spec section 11
averages it over time grouped by `level`, and an average needs a number.

`save_to_eval` puts one example into `apidocs-from-traffic`, never the golden
set. A reviewed ticket is a label the pipeline produced and a human corrected,
which is exactly the thing that must not leak into the frozen set the pipeline
is graded against.

Every call here swallows its own failure and logs. A flywheel that can take the
ticket down is worse than no flywheel. It logs at error level and names the key
that failed, and the success line only prints when all three writes landed, so a
silently empty feedback table cannot look like a healthy one again.
"""

from __future__ import annotations

import functools
import logging

from app import settings
from app.state import EditScore, Ticket

log = logging.getLogger(__name__)

FROM_TRAFFIC_DATASET = "apidocs-from-traffic"

# kind -> the number the dashboard averages.
EDIT_TIER_SCORE = {"none": 0, "style": 1, "correctness": 2}


def _client():
    """One LangSmith client per call. Cheap, and keeps import side effects out."""
    from langsmith import Client

    return Client()


@functools.cache
def _session_id() -> str | None:
    """Tracing project id, resolved once per process, passed as `session_id`.

    langsmith 0.12.1 warns on every `create_feedback` that carries no
    `session_id` ("deprecated and will stop working in a future release"). The
    argument that sets it is `session_id`, not `project_id`. `project_id` is the
    *other* way to address a feedback, the one that means "attach this to a
    project rather than to a run", and the SDK rejects the combination outright:

        ValueError: project_id cannot be provided if run_id or trace_id is provided

    That is exactly what the migration page says to do
    (https://docs.langchain.com/langsmith/smithdb-sdk-migration-feedback#feedback-create):
    keep `run_id`, add `session_id`, resolve it with `read_project`. Resolving
    the name to an id costs one request per process; failing to resolve it costs
    a deprecation warning, not a write.
    """
    try:
        return str(_client().read_project(project_name=settings.LANGSMITH_PROJECT).id)
    except Exception:
        log.warning("langsmith_feedback: could not resolve project %s", settings.LANGSMITH_PROJECT)
        return None


def _identifier_comment(score: EditScore) -> str:
    """Human readable added/removed list for the `edit_tier` comment."""
    added = ", ".join(score["added_identifiers"]) or "none"
    removed = ", ".join(score["removed_identifiers"]) or "none"
    return (
        f"tier {score['tier']} {score['kind']}. "
        f"added: {added}. removed: {removed}. "
        f"char delta: {score['char_delta']:+d}."
    )


def write_edit_feedback(
    run_id: str, score: EditScore, human_tag: str, disposition_miss: bool
) -> None:
    """Write edit_tier, human_tag, and disposition_miss against `run_id`.

    `run_id` is a trace id. post_send writes to both the approval trace and the
    original draft trace, so this is called once per trace with the same values.
    """
    if not run_id:
        log.info("langsmith_feedback: no run id, tracing is probably off, skipping")
        return

    feedbacks = [
        dict(
            key="edit_tier",
            score=EDIT_TIER_SCORE[score["kind"]],
            value=score["kind"],
            comment=_identifier_comment(score),
        ),
        dict(
            key="human_tag",
            score=1 if human_tag == "good_as_is" else 0,
            value=human_tag,
            comment=f"reviewer tagged this {human_tag}",
        ),
        dict(
            key="disposition_miss",
            score=1 if disposition_miss else 0,
            value=disposition_miss,
            comment=(
                "the reviewer's action contradicted the pipeline's disposition"
                if disposition_miss
                else "the reviewer's action agreed with the pipeline's disposition"
            ),
        ),
    ]

    client = _client()
    session_id = _session_id()
    failed: list[str] = []
    for fb in feedbacks:
        try:
            client.create_feedback(
                run_id=run_id, trace_id=run_id, session_id=session_id, **fb
            )
        except Exception:
            # One bad key must not cost the other two.
            failed.append(fb["key"])
            log.exception("langsmith_feedback: %s write FAILED on %s", fb["key"], run_id)

    if failed:
        # The success line used to print regardless, which is how three writes
        # that never landed read as a working flywheel for three days.
        log.error(
            "langsmith_feedback: %d of %d write(s) failed on %s: %s",
            len(failed),
            len(feedbacks),
            run_id,
            ", ".join(failed),
        )
        return

    log.info(
        "langsmith_feedback: wrote edit_tier=%d human_tag=%s disposition_miss=%s on %s",
        EDIT_TIER_SCORE[score["kind"]],
        human_tag,
        disposition_miss,
        run_id,
    )


def save_to_eval(ticket: Ticket, final_answer: str, disposition: str) -> None:
    """Add one reviewed ticket to the from-traffic dataset.

    The dataset is created on first use so a fresh account does not need a
    manual setup step before the demo. `outputs` matches the golden set's shape
    minus `expected_doc_ids`, which nobody labelled here, so a from-traffic
    example can be promoted into the golden set later without a reshape.
    """
    client = _client()

    try:
        if not client.has_dataset(dataset_name=FROM_TRAFFIC_DATASET):
            client.create_dataset(
                dataset_name=FROM_TRAFFIC_DATASET,
                description=(
                    "Reviewed production tickets, saved from the reviewer UI. "
                    "Never merged into apidocs-golden without a human pass."
                ),
            )
    except Exception:
        log.exception("langsmith_feedback: could not ensure %s exists", FROM_TRAFFIC_DATASET)
        return

    try:
        client.create_examples(
            dataset_name=FROM_TRAFFIC_DATASET,
            examples=[
                {
                    "inputs": {"ticket": dict(ticket)},
                    "outputs": {
                        "disposition": disposition,
                        "reference_answer": final_answer,
                    },
                    "metadata": {
                        "source": "from_traffic",
                        "ticket_id": ticket["id"],
                        "tenant": ticket["tenant"],
                        "api_version": ticket["api_version"],
                        "area": ticket["product_area"],
                    },
                }
            ],
        )
    except Exception:
        log.exception("langsmith_feedback: save_to_eval failed for %s", ticket["id"])
        return

    log.info(
        "langsmith_feedback: saved ticket %s to %s as %s",
        ticket["id"],
        FROM_TRAFFIC_DATASET,
        disposition,
    )
