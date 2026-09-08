"""Spoof ServiceNow. Two Postgres tables and this module. Build spec section 6.

No HTTP stub on purpose: a FastAPI fake would be a second process to babysit on
stage and buys nothing the tables do not. The primary key on `sn_replies
.ticket_id` is the whole idempotency story, so a resumed graph that reaches send
twice hits the conflict and treats it as already sent.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from app import settings
from app.state import Ticket

log = logging.getLogger(__name__)

SCHEMA = """
create table if not exists sn_tickets (
  id text primary key, tenant text, api_version text, product_area text,
  subject text, body text, created_at timestamptz,
  status text not null default 'new',
  priority text not null default 'normal',
  level text
);
create table if not exists sn_replies (
  ticket_id text primary key references sn_tickets(id),
  kind text not null,
  body text not null,
  posted_at timestamptz not null default now()
);
"""


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """One short-lived connection per call. The demo is not throughput bound."""
    with psycopg.connect(settings.DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def setup() -> None:
    """Create `sn_tickets` and `sn_replies`. Called by scripts/reset_demo.py."""
    with connect() as conn:
        conn.execute(SCHEMA)
        conn.commit()


def fetch_ticket(ticket_id: str) -> Ticket:
    """Read one row out of `sn_tickets` and shape it as a `Ticket`."""
    with connect() as conn:
        row = conn.execute(
            "select id, tenant, api_version, product_area, subject, body, created_at"
            " from sn_tickets where id = %s",
            (ticket_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"no ticket {ticket_id!r} in sn_tickets")
    return Ticket(
        id=row["id"],
        tenant=row["tenant"],
        api_version=row["api_version"],
        product_area=row["product_area"],
        subject=row["subject"],
        body=row["body"],
        created_at=row["created_at"].isoformat() if row["created_at"] else "",
    )


def list_queue(status: str = "awaiting_review") -> list[dict]:
    """The review queue. Sorted priority desc then created_at asc, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "select id, tenant, api_version, product_area, subject, status, priority,"
            " level, created_at from sn_tickets where status = %s"
            " order by (priority = 'high') desc, created_at asc",
            (status,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_status(ticket_id: str, status: str, priority: str | None = None) -> None:
    """Move a ticket through new -> in_progress -> awaiting_review -> closed."""
    with connect() as conn:
        if priority is None:
            conn.execute(
                "update sn_tickets set status = %s where id = %s", (status, ticket_id)
            )
        else:
            conn.execute(
                "update sn_tickets set status = %s, priority = %s where id = %s",
                (status, priority, ticket_id),
            )
        conn.commit()
    log.info("servicenow: ticket %s -> status=%s priority=%s", ticket_id, status, priority)


def post_reply(ticket_id: str, kind: str, body: str) -> bool:
    """Insert into `sn_replies`. False on primary key conflict, meaning already sent."""
    with connect() as conn:
        cur = conn.execute(
            "insert into sn_replies (ticket_id, kind, body) values (%s, %s, %s)"
            " on conflict (ticket_id) do nothing returning ticket_id",
            (ticket_id, kind, body),
        )
        posted = cur.fetchone() is not None
        conn.commit()
    log.info("servicenow: post_reply %s kind=%s posted=%s", ticket_id, kind, posted)
    return posted


def reply_exists(ticket_id: str) -> bool:
    """Check before send, so a resume that replays send does not double-post."""
    with connect() as conn:
        row = conn.execute(
            "select 1 from sn_replies where ticket_id = %s", (ticket_id,)
        ).fetchone()
    return row is not None
