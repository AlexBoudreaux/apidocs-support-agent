"""Run 15 tickets end to end with scripted approvals. Build spec section 11, 4d.

    uv run python scripts/seed_demo_traffic.py [--limit N] [--dry-run]

Demo steps 14 and 15 need history that already exists before Alex opens
LangSmith. The dashboard chart, the `edit_tier == 2` rule and the `heavy-edits`
annotation queue all read feedback written by post_send, and none of them have
anything to show until real runs have landed. This script is that history.

It is `app.demo run` and `app.demo resume` fused into one process, one ticket
after another, with the human decision read out of `DECISIONS` instead of a
terminal. The decisions are the whole point. `edit_score.kind` only comes out
`correctness` when the approved text changes a route, a version token, an error
code or a url, so the mutations below change those tokens on purpose rather
than reword sentences and hope.

Every seeded ticket id is prefixed `seed_` so this traffic never collides with
the thread ids the live demo uses on stage.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app import settings
from app.graph import build_graph
from app.integrations import servicenow
from app.kb.index import KnowledgeBase

log = logging.getLogger("seed_demo_traffic")


# ---------- the decision table ----------


@dataclass(frozen=True)
class Recipe:
    """One scripted human review. `mutation` names how `final_answer` is built."""

    source: str                       # fixture stem under fixtures/tickets/
    action: str = "approve"           # approve | escalate
    human_tag: str = "good_as_is"
    mutation: str = "none"            # none | wording | version | drop_url | add_route
    citation: str = ""                # the extra route sentence, for add_route
    save_to_kb: bool = False
    save_to_eval: bool = False
    escalation_note: str | None = None
    overrides: dict = field(default_factory=dict)   # set on the derived copies


# Sentences that cite a real corpus route and its real url. Appended text has to
# name something that exists, otherwise the groundedness check on a later run of
# the same corpus would disagree with traffic we seeded ourselves.
CITE_DELIVERIES = (
    "Every HTTP attempt behind one event is listed at "
    "[/v3/webhooks/deliveries](https://docs.example.com/v3/webhooks/deliveries)."
)
CITE_REVERSAL = (
    "If the payment has not been captured yet, use "
    "[/v3/payments/{id}/reversal](https://docs.example.com/v3/payments/reversal) instead."
)
CITE_EVENTS = (
    "The full event type list is at "
    "[/v3/webhooks/events](https://docs.example.com/v3/webhooks/events)."
)

# Plain English, no route, no url, no version, no error code. This is what keeps
# a `fixed_wording` run scoring `style` rather than `correctness`.
WORDING_SUFFIX = "Let us know if that clears it up and we will take another look."

ESC_NOTE_ANSWER = (
    "The pipeline answered this, but the customer is asking for account action "
    "we cannot take from the docs. Handing to the on-call engineer."
)
ESC_NOTE_ABSTAIN = (
    "Nothing in the reference docs covers this. Routing to the team that owns "
    "the written policy so the customer gets a real answer."
)
ESC_NOTE_TRIAGE = (
    "Triage was right. This needs a human on the account, not a documentation "
    "link. Escalated with the original ticket attached."
)

# Ticket id -> recipe. Run order is this order, so `--limit 3` is a useful smoke
# test (one identifier edit, one escalation, one clean approval) instead of three
# escalations in a row.
DECISIONS: dict[str, Recipe] = {
    "seed_l1_001": Recipe("l1_001", human_tag="fixed_facts", mutation="version",
                          save_to_eval=True),
    "seed_l2_002": Recipe("l2_002", action="escalate", human_tag="escalated",
                          escalation_note=ESC_NOTE_ANSWER),
    "seed_l1_003": Recipe("l1_003", human_tag="good_as_is"),
    "seed_l1_002": Recipe("l1_002", human_tag="fixed_facts", mutation="drop_url",
                          citation=CITE_REVERSAL),
    "seed_l1_004": Recipe("l1_004", human_tag="fixed_facts", mutation="drop_url",
                          citation=CITE_EVENTS),
    "seed_l2_001": Recipe("l2_001", human_tag="added_context", mutation="add_route",
                          citation=CITE_EVENTS, save_to_kb=True),
    "seed_l3_001": Recipe("l3_001", action="escalate", human_tag="escalated",
                          escalation_note=ESC_NOTE_ANSWER),
    "seed_l2_003": Recipe("l2_003", human_tag="fixed_facts", mutation="version"),
    "seed_l1_005": Recipe("l1_001", human_tag="fixed_wording", mutation="wording",
                          overrides={"tenant": "bank-c",
                                     "created_at": "2026-09-02T08:15:00Z"}),
    "seed_l1_006": Recipe("l1_003", human_tag="added_context", mutation="add_route",
                          citation=CITE_DELIVERIES, save_to_eval=True,
                          overrides={"tenant": "bank-a",
                                     "created_at": "2026-09-02T10:40:00Z"}),
    "seed_l2_004": Recipe("l2_001", human_tag="good_as_is",
                          overrides={"tenant": "bank-a",
                                     "created_at": "2026-09-02T13:20:00Z"}),
    "seed_abs_001": Recipe("abs_001", action="escalate", human_tag="escalated",
                           escalation_note=ESC_NOTE_ABSTAIN),
    "seed_abs_002": Recipe("abs_002", action="escalate", human_tag="escalated",
                           escalation_note=ESC_NOTE_ABSTAIN),
    "seed_esc_001": Recipe("esc_001", action="escalate", human_tag="escalated",
                           escalation_note=ESC_NOTE_TRIAGE),
    "seed_esc_002": Recipe("esc_002", action="escalate", human_tag="escalated",
                           escalation_note=ESC_NOTE_TRIAGE),
}


# ---------- mutations ----------

_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _mutate_version(draft: str, citation: str) -> str | None:
    """Repoint the first v3 route path at v2, which changes a route identifier.

    Swapping a bare `v3` token in prose is not enough. A draft that already names
    both versions still has the same identifier set afterwards, so tier 1 would
    score it `style` and the seeded traffic would carry the wrong label. Rewriting
    the version prefix of a route path changes a route token outright.
    """
    if "/v3/" in draft:
        return draft.replace("/v3/", "/v2/", 1)
    if "/v2/" in draft:
        return draft.replace("/v2/", "/v3/", 1)
    return None


def _mutate_drop_url(draft: str, citation: str) -> str | None:
    """Strip one deep link back to plain text, which removes a url identifier."""
    match = _LINK.search(draft)
    if not match:
        return None
    url = match.group(2)
    out = _LINK.sub(lambda m: m.group(1) if m.group(2) == url else m.group(0), draft)
    return out if out != draft else None


def _mutate_add_route(draft: str, citation: str) -> str | None:
    """Append a sentence citing one more real route, adding route and url tokens."""
    return f"{draft.rstrip()}\n\n{citation}" if citation else None


def _mutate_wording(draft: str, citation: str) -> str | None:
    """Change prose only. No route, url, version or error code goes in or out."""
    reworded = draft.replace("Please note that ", "Note that ")
    return f"{reworded.rstrip()}\n\n{WORDING_SUFFIX}"


MUTATIONS: dict[str, Callable[[str, str], str | None]] = {
    "version": _mutate_version,
    "drop_url": _mutate_drop_url,
    "add_route": _mutate_add_route,
    "wording": _mutate_wording,
}

# Mutations that must land an identifier change. If the primary edit no-ops
# (say the draft carries no deep link to strip) we fall back to citing an extra
# route, so the seeded `correctness` count does not depend on draft wording.
IDENTIFIER_MUTATIONS = {"version", "drop_url", "add_route"}

FALLBACK_CITATION = CITE_DELIVERIES


def apply_mutation(draft: str, recipe: Recipe) -> str:
    """Build the human's `final_answer` from the pipeline's draft."""
    if recipe.mutation == "none":
        return draft
    out = MUTATIONS[recipe.mutation](draft, recipe.citation)
    if out is None and recipe.mutation in IDENTIFIER_MUTATIONS:
        out = _mutate_add_route(draft, recipe.citation or FALLBACK_CITATION)
        log.info("mutation %s no-opped, cited an extra route instead", recipe.mutation)
    return out if out is not None else draft


# ---------- the plan ----------


@dataclass
class Seed:
    """One row of the plan. `level` is demo metadata, not part of `Ticket`."""

    ticket: dict
    level: str | None
    recipe: Recipe

    @property
    def id(self) -> str:
        return self.ticket["id"]


def build_plan() -> list[Seed]:
    """Load the 12 fixtures and derive 3 more, all with `seed_` ids."""
    tickets_dir = settings.FIXTURES_ROOT / "tickets"
    plan: list[Seed] = []
    for seed_id, recipe in DECISIONS.items():
        raw = json.loads((tickets_dir / f"{recipe.source}.json").read_text())
        level = raw.pop("level", None)
        raw.setdefault("product_area", "unknown")
        raw.update(recipe.overrides)
        raw["id"] = seed_id
        plan.append(Seed(ticket=raw, level=level, recipe=recipe))
    return plan


INSERT = """
insert into sn_tickets
  (id, tenant, api_version, product_area, subject, body, created_at, status, priority, level)
values (%(id)s, %(tenant)s, %(api_version)s, %(product_area)s, %(subject)s, %(body)s,
        %(created_at)s, 'new', 'normal', %(level)s)
on conflict (id) do nothing
"""


def insert_tickets(plan: list[Seed]) -> None:
    """Rows must exist before send, because `sn_replies.ticket_id` references them."""
    servicenow.setup()
    with servicenow.connect() as conn:
        for seed in plan:
            conn.execute(INSERT, {**seed.ticket, "level": seed.level})
        conn.commit()
    log.info("ensured %d rows in sn_tickets", len(plan))


# ---------- running ----------


@contextmanager
def open_graph() -> Iterator[CompiledStateGraph]:
    """Compile once for the whole run. `KnowledgeBase.load()` embeds every doc."""
    kb = KnowledgeBase.load()
    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as checkpointer:
        # from_conn_string takes no serde argument, so set it after construction.
        checkpointer.serde = settings.checkpoint_serde()
        yield build_graph(kb, checkpointer)


def run_config(ticket: dict, level: str | None) -> dict:
    """Same config `app.demo` builds, tagged `seed` so the rule can filter it."""
    return {
        "configurable": {
            "thread_id": ticket["id"],
            "use_cache": True,
            "retrieval_mode": "hybrid",
        },
        "metadata": {
            "ticket_id": ticket["id"],
            "level": level,
            "api_version": ticket["api_version"],
            "area": ticket["product_area"],
            "retrieval_mode": "hybrid",
        },
        "tags": ["seed"],
        "run_name": f"ticket-{ticket['id']}",
    }


def build_decision(seed: Seed, values: dict) -> dict:
    """The scripted human decision, forced to escalate when there is no answer.

    An abstain or a triage escalate reaches review with a gap report or no draft
    at all, so approving one would seed a `disposition_miss` in the wrong
    direction and post a non-answer as an answer.
    """
    recipe = seed.recipe
    draft = values.get("draft") or ""
    disposition = values.get("disposition")
    forced = disposition in ("abstain", "escalate")

    if forced or recipe.action == "escalate":
        note = recipe.escalation_note or (
            ESC_NOTE_ABSTAIN if disposition == "abstain" else ESC_NOTE_TRIAGE
        )
        return {
            "action": "escalate",
            "final_answer": draft or note,
            "human_tag": "escalated",
            "save_to_kb": False,
            "save_to_eval": recipe.save_to_eval,
            "escalation_note": note,
        }

    return {
        "action": "approve",
        "final_answer": apply_mutation(draft, recipe),
        "human_tag": recipe.human_tag,
        "save_to_kb": recipe.save_to_kb,
        "save_to_eval": recipe.save_to_eval,
        "escalation_note": None,
    }


def run_one(graph: CompiledStateGraph, seed: Seed) -> dict:
    """Invoke to the review interrupt, then resume with the scripted decision."""
    config = run_config(seed.ticket, seed.level)

    snapshot = graph.get_state(config)
    if snapshot.values and not snapshot.next:
        print(f"{seed.id:<14} already done, skipping")
        return {"id": seed.id, "skipped": True}

    try:
        servicenow.mark_status(seed.id, "in_progress")
    except Exception:
        log.warning("ticket %s is not in sn_tickets, continuing anyway", seed.id)

    graph.invoke({"ticket": seed.ticket}, config)
    values = graph.get_state(config).values
    disposition = values.get("disposition")

    try:
        servicenow.mark_status(seed.id, "awaiting_review", values.get("priority"))
    except Exception:
        log.warning("could not mark %s awaiting_review", seed.id)

    decision = build_decision(seed, values)
    graph.invoke(Command(resume={"type": "decision", "decision": decision}), config)

    final = graph.get_state(config).values
    score = final.get("edit_score") or {}
    sent = bool(final.get("sent"))
    print(
        f"{seed.id:<14} disposition={str(disposition):<9} "
        f"tag={decision['human_tag']:<14} sent={sent} kind={score.get('kind')}"
    )
    return {
        "id": seed.id,
        "skipped": False,
        "tag": decision["human_tag"],
        "kind": score.get("kind"),
        "sent": sent,
    }


# ---------- reporting ----------


def print_plan(plan: list[Seed]) -> None:
    """The dry run. Prints what would happen and touches nothing."""
    print(f"{'ticket':<14} {'level':<8} {'action':<9} {'tag':<14} "
          f"{'mutation':<10} {'kb':<4} eval")
    print("-" * 72)
    for seed in plan:
        r = seed.recipe
        print(f"{seed.id:<14} {str(seed.level):<8} {r.action:<9} {r.human_tag:<14} "
              f"{r.mutation:<10} {str(r.save_to_kb):<4} {r.save_to_eval}")
    identifier = sum(1 for s in plan if s.recipe.mutation in IDENTIFIER_MUTATIONS)
    escalations = sum(1 for s in plan if s.recipe.action == "escalate")
    print("-" * 72)
    print(f"{len(plan)} tickets, {identifier} identifier edits, "
          f"{escalations} scripted escalations, "
          f"{sum(1 for s in plan if s.recipe.save_to_eval)} save_to_eval, "
          f"{sum(1 for s in plan if s.recipe.save_to_kb)} save_to_kb")


def print_summary(results: list[dict], failures: list[tuple[str, str]]) -> None:
    """Counts by tag and by edit kind, which is what the dashboard will chart."""
    by_tag: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for r in results:
        if r.get("skipped"):
            continue
        by_tag[r["tag"]] = by_tag.get(r["tag"], 0) + 1
        by_kind[str(r["kind"])] = by_kind.get(str(r["kind"]), 0) + 1

    skipped = sum(1 for r in results if r.get("skipped"))
    print("\n" + "=" * 72)
    print("SEED TRAFFIC SUMMARY")
    print("=" * 72)
    print(f"ran     : {len(results) - skipped}")
    print(f"skipped : {skipped} (already finished threads)")
    print(f"by tag  : {by_tag}")
    print(f"by kind : {by_kind}")
    print(f"failed  : {len(failures)}")
    for ticket_id, error in failures:
        print(f"  {ticket_id}: {error}")
    print("=" * 72 + "\n")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(prog="seed_demo_traffic")
    parser.add_argument("--limit", type=int, help="run only the first N tickets")
    parser.add_argument("--dry-run", action="store_true", help="print the plan only")
    args = parser.parse_args(argv)

    plan = build_plan()
    if args.limit:
        plan = plan[: args.limit]

    if args.dry_run:
        print_plan(plan)
        return 0

    insert_tickets(plan)

    results: list[dict] = []
    failures: list[tuple[str, str]] = []
    with open_graph() as graph:
        for seed in plan:
            # One bad ticket must not cost the other fourteen their traces.
            try:
                results.append(run_one(graph, seed))
            except Exception as exc:
                log.exception("ticket %s failed", seed.id)
                failures.append((seed.id, f"{type(exc).__name__}: {exc}"))

    print_summary(results, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
