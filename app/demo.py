"""The demo CLI. Build spec section 9.

    uv run python -m app.demo run --ticket fixtures/tickets/l1_001.json [--no-cache] [--mode semantic_only]
    uv run python -m app.demo resume --thread l1_001 --approve [--tag fixed_wording] [--final-file path]
    uv run python -m app.demo resume --thread l1_001 --chat "reword the second paragraph"
    uv run python -m app.demo status --thread l1_001
    uv run python -m app.demo list

`run` and `resume` are separate processes on purpose. The graph pauses at the
review interrupt, this process exits, and a later process picks the thread back
up out of Postgres with nothing but the `thread_id`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app import settings
from app.graph import build_graph
from app.integrations import servicenow
from app.kb.index import KnowledgeBase

log = logging.getLogger("demo")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


@contextmanager
def open_graph() -> Iterator[CompiledStateGraph]:
    """Compile the graph against Postgres for the life of one CLI command."""
    kb = KnowledgeBase.load()
    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as checkpointer:
        # from_conn_string takes no serde argument, so set it after construction.
        checkpointer.serde = settings.checkpoint_serde()
        yield build_graph(kb, checkpointer)


def run_config(ticket: dict, level: str | None, use_cache: bool, mode: str) -> dict:
    """The config every invoke uses. Metadata and tags per build spec section 6."""
    return {
        "configurable": {
            "thread_id": ticket["id"],
            "use_cache": use_cache,
            "retrieval_mode": mode,
        },
        "metadata": {
            "ticket_id": ticket["id"],
            "level": level,
            "api_version": ticket["api_version"],
            "area": ticket["product_area"],
            "retrieval_mode": mode,
        },
        "tags": ["demo"],
        "run_name": f"ticket-{ticket['id']}",
    }


def _load_fixture(path: Path) -> tuple[dict, str | None]:
    """Read a ticket fixture. `level` is demo metadata and is not part of `Ticket`."""
    raw = json.loads(path.read_text())
    level = raw.pop("level", None)
    return raw, level


def _level_for(ticket_id: str) -> str | None:
    """Recover the fixture's `level` on resume so both traces group the same way.

    `level` is demo metadata that would not exist in production. It lives on the
    `sn_tickets` row, which is the only place a second process can find it.
    """
    try:
        with servicenow.connect() as conn:
            row = conn.execute(
                "select level from sn_tickets where id = %s", (ticket_id,)
            ).fetchone()
        return row["level"] if row else None
    except Exception:
        log.warning("could not read level for %s", ticket_id)
        return None


def _print_pause(graph: CompiledStateGraph, config: dict, thread_id: str) -> None:
    """Print the draft and the thread id, the two things the next process needs."""
    values = graph.get_state(config).values
    print("\n" + "=" * 72)
    print(f"PAUSED AT REVIEW    thread_id = {thread_id}")
    print("=" * 72)
    print(f"disposition : {values.get('disposition')}")
    print(f"priority    : {values.get('priority')}")
    print(f"flags       : {values.get('guardrail_flags')}")
    stats = values.get("retrieval_stats") or {}
    print(
        f"retrieval   : {stats.get('queries_run', 0)} queries, "
        f"{stats.get('iterations', 0)} iteration(s), modes={stats.get('modes', [])}, "
        f"abstained={stats.get('abstained')}"
    )
    print(f"docs        : {[d['doc_id'] for d in values.get('relevant_docs', [])]}")
    print("-" * 72)
    print(values.get("draft") or "(no draft)")
    print("=" * 72)
    print(f"Resume with: uv run python -m app.demo resume --thread {thread_id} --approve\n")


# ---------- commands ----------


def cmd_run(args: argparse.Namespace) -> int:
    ticket, level = _load_fixture(Path(args.ticket))
    mode = args.mode
    config = run_config(ticket, level, use_cache=not args.no_cache, mode=mode)

    try:
        servicenow.mark_status(ticket["id"], "in_progress")
    except Exception:
        log.warning("ticket %s is not in sn_tickets, continuing anyway", ticket["id"])

    with open_graph() as graph:
        result = graph.invoke({"ticket": ticket}, config)
        if "__interrupt__" in result:
            try:
                servicenow.mark_status(
                    ticket["id"],
                    "awaiting_review",
                    graph.get_state(config).values.get("priority"),
                )
            except Exception:
                log.warning("could not mark %s awaiting_review", ticket["id"])
            _print_pause(graph, config, ticket["id"])
        else:
            print(json.dumps({k: str(v) for k, v in result.items()}, indent=2))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    config = {"configurable": {"thread_id": args.thread}}

    with open_graph() as graph:
        snapshot = graph.get_state(config)
        if not snapshot.values:
            print(f"no thread {args.thread!r} in the checkpointer", file=sys.stderr)
            return 1

        if not snapshot.next:
            print(f"thread {args.thread} is already finished. Nothing to resume.")
            _print_final(snapshot.values)
            return 0

        ticket = snapshot.values["ticket"]
        config = run_config(
            ticket,
            _level_for(ticket["id"]),
            use_cache=True,
            mode=snapshot.config.get("configurable", {}).get("retrieval_mode", "hybrid"),
        )

        if args.chat:
            command = Command(resume={"type": "chat", "text": args.chat})
        else:
            final_answer = (
                Path(args.final_file).read_text()
                if args.final_file
                else snapshot.values.get("draft")
                or ""
            )
            decision = {
                "action": "escalate" if args.escalate else "approve",
                "final_answer": final_answer,
                "human_tag": args.tag,
                "save_to_kb": args.save_to_kb,
                "save_to_eval": args.save_to_eval,
                "escalation_note": args.note,
            }
            command = Command(resume={"type": "decision", "decision": decision})

        result = graph.invoke(command, config)

        if "__interrupt__" in result:
            _print_pause(graph, config, args.thread)
        else:
            _print_final(graph.get_state(config).values)
    return 0


def _print_final(values: dict) -> None:
    sent = values.get("sent")
    score = values.get("edit_score")
    print("\n" + "=" * 72)
    print("DONE")
    print("=" * 72)
    print(f"sent       : {sent}")
    print(f"edit score : {score}")
    print("=" * 72 + "\n")


def cmd_status(args: argparse.Namespace) -> int:
    config = {"configurable": {"thread_id": args.thread}}
    with open_graph() as graph:
        snapshot = graph.get_state(config)
    if not snapshot.values:
        print(f"no thread {args.thread!r} in the checkpointer", file=sys.stderr)
        return 1

    values = snapshot.values
    print(f"thread      : {args.thread}")
    print(f"next        : {snapshot.next or '(finished)'}")
    print(f"disposition : {values.get('disposition')}")
    print(f"priority    : {values.get('priority')}")
    print(f"docs        : {[d['doc_id'] for d in values.get('relevant_docs', [])]}")
    print(f"messages    : {len(values.get('messages', []))}")
    print(f"sent        : {values.get('sent')}")
    print(f"edit score  : {values.get('edit_score')}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = servicenow.list_queue(args.status) if args.status else []
    if not args.status:
        rows = []
        for status in ("new", "in_progress", "awaiting_review", "closed"):
            rows.extend(servicenow.list_queue(status))
    if not rows:
        print("no tickets. Run scripts/seed_servicenow.py first.")
        return 0
    print(f"{'id':<12} {'status':<16} {'pri':<7} {'ver':<4} {'area':<9} subject")
    print("-" * 90)
    for r in rows:
        print(
            f"{r['id']:<12} {r['status']:<16} {r['priority']:<7} "
            f"{r['api_version']:<4} {r['product_area']:<9} {r['subject'][:44]}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="app.demo")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run one ticket to the review interrupt")
    p_run.add_argument("--ticket", required=True, help="path to a ticket fixture JSON")
    p_run.add_argument("--no-cache", action="store_true", help="hide approved answers")
    p_run.add_argument("--mode", default="hybrid", choices=["hybrid", "semantic_only"])
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="resume a paused thread from Postgres")
    p_resume.add_argument("--thread", required=True)
    p_resume.add_argument("--approve", action="store_true")
    p_resume.add_argument("--escalate", action="store_true")
    p_resume.add_argument("--chat", help="send one human chat turn to the reviewer agent")
    p_resume.add_argument("--tag", default="good_as_is")
    p_resume.add_argument("--final-file", help="file holding the final answer text")
    p_resume.add_argument("--note", help="escalation note")
    p_resume.add_argument("--save-to-kb", action="store_true")
    p_resume.add_argument("--save-to-eval", action="store_true")
    p_resume.set_defaults(func=cmd_resume)

    p_status = sub.add_parser("status", help="print the checkpointed state of a thread")
    p_status.add_argument("--thread", required=True)
    p_status.set_defaults(func=cmd_status)

    p_list = sub.add_parser("list", help="print the ServiceNow queue")
    p_list.add_argument("--status", help="filter by status")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
