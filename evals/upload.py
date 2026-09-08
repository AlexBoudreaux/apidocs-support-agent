"""Push `evals/dataset.jsonl` into LangSmith. Build spec section 8.1.

One JSONL, two datasets.

* `apidocs-golden`, all 30, with `splits` and `metadata` so the experiment view
  filters by stratum in one click.
* `apidocs-retrieval`, the 27 non-escalate examples, inputs unchanged, outputs
  narrowed to `expected_doc_ids`. Derived rather than authored, so the two can
  never drift apart.

Both get the tag `v2`. v1 was tagged first and superseded the same day: three
L3 tickets carried `api_version: "unknown"`, which the frozen `Ticket` type
forbids, so they errored at `intake` and never reached retrieval. Nothing else
about the file changed. Every experiment runs against the tag, not against
"whatever is in the dataset today". That is the whole point of freezing: without
it, editing one reference answer silently invalidates every comparison already
made.

    uv run python evals/upload.py [--dry-run] [--tag v1]

Re-running is safe. Examples are keyed by a UUID derived from the example id.
Rows that already exist are updated in place, rows that do not are created, so a
second upload never appends a duplicate set and never destroys the history an
older tag points at.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from langsmith import Client

# Imported for the side effect: `app.settings` is what loads `.env`, and without
# it `Client()` falls back to whatever key happens to be in the ambient shell.
from app import settings  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = REPO_ROOT / "evals" / "dataset.jsonl"

GOLDEN = "apidocs-golden"
RETRIEVAL = "apidocs-retrieval"

# Stable example ids across re-uploads. A fixed namespace plus the example's own
# id, so `l1_001` is the same LangSmith row every time and the dataset version
# history reads as edits rather than as a pile of duplicates.
_NAMESPACE = uuid.UUID("6f1d5a3e-9c42-4b7a-8f10-2d5b7c1e4a90")


def example_uuid(dataset: str, example_id: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{dataset}:{example_id}")


def load_rows(path: Path = DATASET_PATH) -> list[dict]:
    """Read the frozen JSONL. One example per line."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate example ids in dataset.jsonl")
    return rows


def golden_examples(rows: list[dict]) -> list[dict]:
    """All 30, unchanged from the file."""
    return [
        {
            "id": example_uuid(GOLDEN, r["id"]),
            "inputs": r["inputs"],
            "outputs": r["outputs"],
            "metadata": {**r["metadata"], "example_id": r["id"]},
            # LangSmith's `ExampleCreate` field is `split`, singular, and it
            # takes the list. The build spec calls it `splits` after the JSONL
            # key; they are the same thing.
            "split": r["splits"],
        }
        for r in rows
    ]


def retrieval_examples(rows: list[dict]) -> list[dict]:
    """The 27 non-escalate examples, outputs narrowed to the doc ids.

    Escalate examples are dropped because retrieval never runs on them: triage
    routes straight to review, so there is nothing to score.
    """
    return [
        {
            "id": example_uuid(RETRIEVAL, r["id"]),
            "inputs": r["inputs"],
            "outputs": {"expected_doc_ids": r["outputs"]["expected_doc_ids"]},
            "metadata": {**r["metadata"], "example_id": r["id"]},
            "split": r["splits"],
        }
        for r in rows
        if r["outputs"]["disposition"] != "escalate"
    ]


def ensure_dataset(client: Client, name: str, description: str):
    if client.has_dataset(dataset_name=name):
        return client.read_dataset(dataset_name=name)
    return client.create_dataset(dataset_name=name, description=description)


def push(client: Client, name: str, description: str, examples: list[dict], tag: str) -> None:
    """Create or update the dataset, upsert every example, then tag the version.

    `create_examples` is not an upsert. Handing it an id that already exists
    returns 409 ("example already exists"), so existing rows go through
    `update_examples` instead. Deleting and recreating would be simpler and
    wrong: it would drop the rows an older version tag resolves to.
    """
    dataset = ensure_dataset(client, name, description)

    existing = {e.id for e in client.list_examples(dataset_id=dataset.id)}
    new = [e for e in examples if e["id"] not in existing]
    updates = [{**e, "dataset_id": dataset.id} for e in examples if e["id"] in existing]

    if new:
        client.create_examples(dataset_id=dataset.id, examples=new)
    if updates:
        client.update_examples(dataset_id=dataset.id, updates=updates)
    print(f"{name}: {len(new)} created, {len(updates)} updated")

    # `as_of` has to be after the write lands, or the tag points at the version
    # before it and every experiment reads an empty dataset.
    client.update_dataset_tag(
        dataset_name=name, as_of=datetime.now(timezone.utc), tag=tag
    )
    print(f"{name}: {len(examples)} example(s), tagged {tag}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="v2", help="dataset version tag, default v2")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the counts and exit, no writes"
    )
    args = parser.parse_args()

    rows = load_rows()
    golden = golden_examples(rows)
    retrieval = retrieval_examples(rows)

    splits: dict[str, int] = {}
    for r in rows:
        for s in r["splits"]:
            splits[s] = splits.get(s, 0) + 1

    print(f"{DATASET_PATH.relative_to(REPO_ROOT)}: {len(rows)} example(s)")
    for split, count in sorted(splits.items()):
        print(f"  {split:<10} {count}")
    print(f"{GOLDEN}: {len(golden)}   {RETRIEVAL}: {len(retrieval)}")

    if args.dry_run:
        print("dry run, nothing written")
        return 0

    client = Client()
    push(
        client,
        GOLDEN,
        "30 hand-verified API documentation support tickets. Reference answer, "
        "disposition, and expected doc ids per example. Splits L1, L2, L3, "
        "abstain, escalate, near_miss.",
        golden,
        args.tag,
    )
    push(
        client,
        RETRIEVAL,
        "Retrieval-only view of apidocs-golden. The 27 non-escalate examples, "
        "scored on recall and precision of expected_doc_ids.",
        retrieval,
        args.tag,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
