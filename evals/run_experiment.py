"""Run one LangSmith experiment. Build spec section 8.4.

    uv run python evals/run_experiment.py --mode hybrid
    uv run python evals/run_experiment.py --mode hybrid --retrieval
    uv run python evals/run_experiment.py --mode semantic_only
    uv run python evals/run_experiment.py --mode semantic_only --retrieval

End to end runs the parent graph against `apidocs-golden` at tag `v1`, three
repetitions, six evaluators. Retrieval runs the subgraph alone against
`apidocs-retrieval`, one repetition, three evaluators.

Column names changed on 2026-09-07 (session 4g, build spec 8.3). End to end
prints `escalate_correct` where it used to print `disposition`, and the
retrieval table gained `abstained`. Experiments run before that date carry the
old `disposition` column; the rename is what keeps the comparison view from
lining the two definitions up as if they were the same measurement.

Run order matters. `e2e-hybrid` first, `retrieval-hybrid` second, and the
semantic-only pair last and only if the first two are green. Semantic-only is
the ablation: it rewrites every exact lookup to a semantic one, which is exactly
the change the near-miss split is built to detect.

After the run the script prints per-split pass rate and pass^3 for `correctness`
and `escalate_correct`. pass^3 is the fraction of examples that passed on all
three repetitions, not the fraction of runs that passed. It is the honest number for
a system that will run unattended many times a day: at a 70 percent single trial
rate, pass@3 reads 97 percent and pass^3 reads 34 percent, and only one of those
describes what a bank gets.
"""

from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict
from pathlib import Path

from langsmith import Client

from app import settings
from evals.evaluators import E2E_EVALUATORS, RETRIEVAL_EVALUATORS
from evals.target import run_full_graph, run_retrieval_only

REPO_ROOT = Path(__file__).resolve().parent.parent

GOLDEN = "apidocs-golden"
RETRIEVAL = "apidocs-retrieval"
# v2, not v1. Three L3 tickets shipped with `api_version: "unknown"`, which
# `Ticket.api_version` (frozen, `Literal["v2","v3"]`) forbids and `intake`
# rejects, so they errored at the first node. Alex chose to set a concrete
# version on those three rather than widen the schema. See evals/DATASET.md.
DATASET_VERSION = "v2"

REPETITIONS = 3
MAX_CONCURRENCY = 8

# Reported in this order so the results table always reads the same way.
SPLIT_ORDER = ["L1", "L2", "L3", "abstain", "escalate", "near_miss"]


def git_sha() -> str:
    """Best effort. This repo is not a git repo yet, and that is not a failure."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or "not-a-git-repo"
    except Exception:
        return "unknown"


def run_metadata(mode: str, label: str | None = None) -> dict:
    """The convention, set deliberately. LangSmith does not prescribe one."""
    return {
        "retrieval_mode": mode,
        "prompt_version": label or "unlabelled",
        "git_sha": git_sha(),
        "dataset_version": DATASET_VERSION,
        "model_fast": settings.MODEL_FAST,
        "model_strong": settings.MODEL_STRONG,
        "judge_model": settings.MODEL_STRONG,
        "use_cache": False,
    }


# ---------- scoring the returned results ----------


def _rows(results) -> list[dict]:
    """Flatten `ExperimentResults` into one row per run.

    Each row carries the example's splits, which is what the per-split table is
    grouped by, and the score of every evaluator that returned something.
    """
    rows = []
    for r in results:
        example = r["example"]
        metadata = example.metadata or {}
        splits = metadata.get("dataset_split") or []
        scores = {}
        for feedback in r["evaluation_results"]["results"]:
            if feedback.score is not None:
                scores[feedback.key] = feedback.score
        rows.append(
            {
                "example_id": metadata.get("example_id", str(example.id)),
                "splits": list(splits),
                "scores": scores,
            }
        )
    return rows


def per_split(rows: list[dict], key: str) -> dict[str, dict]:
    """Mean single-trial pass rate and pass^3 for one evaluator key, per split.

    Only examples the evaluator actually scored are counted. `correctness` is
    blank on abstain and escalate by design, so those splits are absent from its
    table rather than showing a misleading zero.
    """
    by_split: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if key not in row["scores"]:
            continue
        for split in row["splits"]:
            by_split[split][row["example_id"]].append(row["scores"][key])

    out = {}
    for split, examples in by_split.items():
        trials = [s for scores in examples.values() for s in scores]
        # pass^k, not pass@k: every trial of the example has to have passed.
        all_passed = [all(s >= 1 for s in scores) for scores in examples.values()]
        out[split] = {
            "examples": len(examples),
            "trials": len(trials),
            "mean": sum(trials) / len(trials) if trials else 0.0,
            "pass_pow_k": sum(all_passed) / len(all_passed) if all_passed else 0.0,
        }
    return out


def print_split_table(rows: list[dict], keys: list[str]) -> None:
    print()
    print(f"{'split':<10} {'key':<26} {'n':>3} {'trials':>7} {'mean':>7} {'pass^k':>8}")
    print("-" * 66)
    for key in keys:
        table = per_split(rows, key)
        for split in SPLIT_ORDER + sorted(set(table) - set(SPLIT_ORDER)):
            if split not in table:
                continue
            s = table[split]
            print(
                f"{split:<10} {key:<26} {s['examples']:>3} {s['trials']:>7} "
                f"{s['mean']:>7.2f} {s['pass_pow_k']:>8.2f}"
            )
        print("-" * 66)


def print_mean_table(rows: list[dict], keys: list[str]) -> None:
    """Retrieval runs are one repetition, so pass^k is not a number worth printing."""
    print()
    print(f"{'split':<10} {'key':<22} {'n':>3} {'mean':>7}")
    print("-" * 46)
    for key in keys:
        table = per_split(rows, key)
        overall = [r["scores"][key] for r in rows if key in r["scores"]]
        for split in SPLIT_ORDER + sorted(set(table) - set(SPLIT_ORDER)):
            if split not in table:
                continue
            s = table[split]
            print(f"{split:<10} {key:<22} {s['examples']:>3} {s['mean']:>7.2f}")
        if overall:
            print(f"{'ALL':<10} {key:<22} {len(overall):>3} {sum(overall) / len(overall):>7.2f}")
        print("-" * 46)


def print_failures(rows: list[dict], keys: list[str]) -> None:
    """Every example that failed at least one trial, so the write-up can diagnose it."""
    seen: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        for key in keys:
            if key in row["scores"]:
                seen[(row["example_id"], key)].append(row["scores"][key])

    bad = {k: v for k, v in seen.items() if not all(s >= 1 for s in v)}
    if not bad:
        print("\nno failing examples")
        return

    print("\nfailing examples (example, key, trial scores)")
    for (example_id, key), scores in sorted(bad.items()):
        print(f"  {example_id:<10} {key:<26} {scores}")


# ---------- the two experiments ----------


def run_e2e(mode: str, dry_run: bool, label: str | None = None) -> None:
    client = Client()
    prefix = f"e2e-{mode.replace('_', '-')}" + (f"-{label}" if label else "")
    print(f"{prefix}: {GOLDEN}@{DATASET_VERSION}, {REPETITIONS} repetition(s)")
    if dry_run:
        print("dry run, nothing sent")
        return

    results = client.evaluate(
        lambda inputs: run_full_graph(inputs, retrieval_mode=mode),
        data=client.list_examples(dataset_name=GOLDEN, as_of=DATASET_VERSION),
        evaluators=E2E_EVALUATORS,
        experiment_prefix=prefix,
        num_repetitions=REPETITIONS,
        max_concurrency=MAX_CONCURRENCY,
        metadata=run_metadata(mode, label),
    )

    rows = _rows(results)
    print_split_table(rows, ["correctness", "escalate_correct"])
    print_split_table(
        rows,
        [
            "traj_searched",
            "traj_iterations_ok",
            "traj_abstain_exit",
            "traj_no_send_before_review",
        ],
    )
    print_failures(rows, ["correctness", "escalate_correct"])
    print(f"\nexperiment: {results.experiment_name}")


def run_retrieval(mode: str, dry_run: bool, label: str | None = None) -> None:
    client = Client()
    prefix = f"retrieval-{mode.replace('_', '-')}" + (f"-{label}" if label else "")
    print(f"{prefix}: {RETRIEVAL}@{DATASET_VERSION}, 1 repetition")
    if dry_run:
        print("dry run, nothing sent")
        return

    results = client.evaluate(
        lambda inputs: run_retrieval_only(inputs, retrieval_mode=mode),
        data=client.list_examples(dataset_name=RETRIEVAL, as_of=DATASET_VERSION),
        evaluators=RETRIEVAL_EVALUATORS,
        experiment_prefix=prefix,
        num_repetitions=1,
        max_concurrency=MAX_CONCURRENCY,
        metadata=run_metadata(mode, label),
    )

    rows = _rows(results)
    print_mean_table(rows, ["retrieval_recall", "retrieval_precision", "abstained"])
    print_failures(rows, ["retrieval_recall", "abstained"])
    print(f"\nexperiment: {results.experiment_name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["hybrid", "semantic_only"], default="hybrid")
    parser.add_argument(
        "--retrieval",
        action="store_true",
        help="run the retrieval-only experiment instead of the end to end one",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    parser.add_argument(
        "--label",
        default=None,
        help="name this run. Appends to the experiment prefix and is stored as `prompt_version`",
    )
    args = parser.parse_args()

    if args.retrieval:
        run_retrieval(args.mode, args.dry_run, args.label)
    else:
        run_e2e(args.mode, args.dry_run, args.label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
