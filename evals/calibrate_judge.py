"""Run the correctness judge against Alex's hand labels. Build spec section 8.5.

    uv run python evals/calibrate_judge.py [--repeat N] [--quiet]

Ten pairs in `evals/calibration_pairs.jsonl`, five labelled pass and five
labelled fail. The script calls the exact function `evaluators.correctness`
calls, so a green number here is a statement about the judge the experiment will
actually use, not about a near-copy of it.

Target is 9 of 10. Below that, the judge prompt gets fixed and this reruns
before any experiment.

Raw agreement is reported alongside TPR and TNR, per Hamel Husain. Agreement
alone is misleading when one class is rare: a judge that says "pass" to
everything scores 50 percent here and would score 90 percent on a set with one
failure in ten, while catching nothing. This set is deliberately balanced so all
three numbers are readable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app import settings  # noqa: F401  loads .env before the model is built
from evals.evaluators import judge_correctness

REPO_ROOT = Path(__file__).resolve().parent.parent
PAIRS_PATH = REPO_ROOT / "evals" / "calibration_pairs.jsonl"

TARGET = 9


def load_pairs(path: Path = PAIRS_PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_once(pairs: list[dict], quiet: bool = False) -> list[dict]:
    """Judge every pair and return one result row each."""
    results = []
    for pair in pairs:
        verdict = judge_correctness(
            pair["ticket"], pair["reference_answer"], pair["draft"]
        )
        predicted = "pass" if verdict.passed else "fail"
        agreed = predicted == pair["label"]
        results.append(
            {
                "id": pair["id"],
                "label": pair["label"],
                "predicted": predicted,
                "agreed": agreed,
                "failure_mode": pair.get("failure_mode"),
                "reason": verdict.reason,
            }
        )
        if not quiet:
            mark = "ok  " if agreed else "MISS"
            print(f"  {mark} {pair['id']}  label={pair['label']:<4} judge={predicted:<4}")
    return results


def report(results: list[dict]) -> int:
    """Print agreement, TPR, TNR, and every disagreement. Returns the agreement count."""
    agreed = sum(r["agreed"] for r in results)
    total = len(results)

    # "Positive" is a real failure caught, because catching failures is the job.
    fails = [r for r in results if r["label"] == "fail"]
    passes = [r for r in results if r["label"] == "pass"]
    tpr = sum(r["predicted"] == "fail" for r in fails) / len(fails) if fails else float("nan")
    tnr = sum(r["predicted"] == "pass" for r in passes) / len(passes) if passes else float("nan")

    print()
    print(f"agreement : {agreed} of {total}")
    print(f"TPR       : {tpr:.2f}  ({len(fails)} labelled fail, caught as fail)")
    print(f"TNR       : {tnr:.2f}  ({len(passes)} labelled pass, kept as pass)")

    misses = [r for r in results if not r["agreed"]]
    if misses:
        print("\ndisagreements")
        for r in misses:
            mode = r["failure_mode"] or "-"
            print(f"  {r['id']}  label={r['label']} judge={r['predicted']} mode={mode}")
            print(f"      judge said: {r['reason']}")
    else:
        print("\nno disagreements")

    print()
    print("PASS" if agreed >= TARGET else f"BELOW TARGET, fix the judge prompt (need {TARGET})")
    return agreed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="judge each pair N times and report the worst run, for judge stability",
    )
    parser.add_argument("--quiet", action="store_true", help="only the summary")
    args = parser.parse_args()

    pairs = load_pairs()
    print(f"{len(pairs)} calibration pair(s), model {settings.MODEL_STRONG}\n")

    worst = None
    for i in range(args.repeat):
        if args.repeat > 1:
            print(f"run {i + 1} of {args.repeat}")
        results = run_once(pairs, quiet=args.quiet)
        agreed = sum(r["agreed"] for r in results)
        if worst is None or agreed < worst[0]:
            worst = (agreed, results)

    agreed = report(worst[1])
    return 0 if agreed >= TARGET else 1


if __name__ == "__main__":
    raise SystemExit(main())
