"""Create the tables and clear the demo state. Build spec section 6.

    uv run python scripts/reset_demo.py

Calls `PostgresSaver.setup()` once (the checkpoint tables), creates `sn_tickets`
and `sn_replies`, then truncates all three so a rehearsal starts clean.

Also clears the answer cache back to its committed seed. `kb/approved/` is a
write path, not just a fixture directory: post_send drops one markdown file in
there on every approval with "save to KB" ticked. Left alone, a rehearsal
searches a slightly larger knowledge base than the one before it, retrieval
returns different documents, and the draft on stage does not match the draft you
practised. See build spec section 4.1 (post_send) and 5.4.
"""

from __future__ import annotations

import logging

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from app import settings
from app.integrations import servicenow

log = logging.getLogger("reset_demo")

CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")

# The one approved answer that ships with the repo. Everything else under
# kb/approved/ was written by a demo run and goes.
SEED_APPROVED = "seed-refund-window.md"


def reset_answer_cache() -> int:
    """Delete runtime-approved answers, keep the committed seed. Returns the count."""
    approved = settings.APPROVED_DIR
    if not approved.is_dir():
        return 0

    removed = 0
    for path in sorted(approved.glob("*.md")):
        if path.name == SEED_APPROVED:
            continue
        path.unlink()
        removed += 1

    if not (approved / SEED_APPROVED).exists():
        log.warning(
            "%s is missing. The answer cache demo has nothing to hit until a "
            "ticket is approved with save-to-KB ticked.",
            approved / SEED_APPROVED,
        )
    return removed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(message)s")

    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as checkpointer:
        checkpointer.setup()
    log.info("checkpoint tables ready")

    servicenow.setup()
    log.info("sn_tickets and sn_replies ready")

    with psycopg.connect(settings.DATABASE_URL) as conn:
        conn.execute("truncate sn_replies, sn_tickets cascade")
        for table in CHECKPOINT_TABLES:
            if table == "checkpoint_migrations":
                continue  # dropping migrations would re-run setup on every start
            conn.execute(f"truncate {table}")
        conn.commit()
    log.info("truncated sn_* and checkpoint tables")

    removed = reset_answer_cache()
    log.info("answer cache reset, %d runtime answer(s) removed, seed kept", removed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
