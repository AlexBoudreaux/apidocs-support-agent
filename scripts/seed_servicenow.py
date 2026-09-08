"""Load ticket fixtures into `sn_tickets`. Build spec section 6.

    uv run python scripts/seed_servicenow.py [--dir fixtures/tickets]

Every `*.json` under the fixtures directory becomes one row with status `new`.
`level` is demo metadata carried from the fixture so the LangSmith dashboard can
group by it; it would not exist in production.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from app import settings
from app.integrations import servicenow

log = logging.getLogger("seed_servicenow")

INSERT = """
insert into sn_tickets
  (id, tenant, api_version, product_area, subject, body, created_at, status, priority, level)
values (%(id)s, %(tenant)s, %(api_version)s, %(product_area)s, %(subject)s, %(body)s,
        %(created_at)s, 'new', 'normal', %(level)s)
on conflict (id) do update set
  tenant = excluded.tenant, api_version = excluded.api_version,
  product_area = excluded.product_area, subject = excluded.subject,
  body = excluded.body, created_at = excluded.created_at,
  status = 'new', priority = 'normal', level = excluded.level
"""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(settings.FIXTURES_ROOT / "tickets"))
    args = parser.parse_args()

    paths = sorted(Path(args.dir).glob("*.json"))
    if not paths:
        log.warning("no ticket fixtures under %s", args.dir)
        return 0

    servicenow.setup()
    with servicenow.connect() as conn:
        for path in paths:
            raw = json.loads(path.read_text())
            raw.setdefault("level", None)
            raw.setdefault("product_area", "unknown")
            conn.execute(INSERT, raw)
            log.info("seeded %s", raw["id"])
        conn.commit()

    log.info("seeded %d ticket(s) from %s", len(paths), args.dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
