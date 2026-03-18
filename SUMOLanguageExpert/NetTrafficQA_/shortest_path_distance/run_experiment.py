#!/usr/bin/env python3
"""
Collect LLM responses for shortest_path QA pairs using a chosen baseline.

This script only collects responses — use evaluate.py to parse and score them.

Usage:
  python run_experiment.py --baseline raw
  python run_experiment.py --baseline adj --model claude-haiku-4-5-20251001 --n 5
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from utils import DEFAULT_MODEL
from methods import METHODS

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"

BASELINES = METHODS


def load_qa(n: int | None = None) -> list[dict]:
    qa_path = BASE_DIR / "qa_pairs.csv"
    if not qa_path.exists():
        print(f"ERROR: {qa_path} not found. Run generate_qa.py first.", file=sys.stderr)
        sys.exit(1)
    with open(qa_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[:n] if n else rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, choices=list(BASELINES.keys()))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--n", type=int, default=None, help="Limit to first N rows")
    args = parser.parse_args()

    ask_fn = BASELINES[args.baseline]
    rows = load_qa(args.n)

    output_path = RESULTS_DIR / f"{args.baseline}_responses_{args.model}.csv"
    fieldnames = [
        "network", "source_edge", "target_edge",
        "ground_truth_distance", "bin", "response_text",
    ]

    results = []
    for i, row in enumerate(rows, start=1):
        question = (
            f"What is the shortest path distance (in number of hops) "
            f"from edge {row['source_edge']} to edge {row['target_edge']}?"
        )
        print(f"[{i}/{len(rows)}] {row['network']} | {row['source_edge']} -> {row['target_edge']} "
              f"(gt={row['ground_truth_distance']}, bin={row['bin']})")

        resp_text = ask_fn(row["network"], question, args.model)
        print(f"  {resp_text[:80]}")

        results.append({
            **row,
            "response_text": resp_text,
        })

    RESULTS_DIR.mkdir(exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone. Collected {len(results)} responses.")
    print(f"Responses saved to {output_path}")


if __name__ == "__main__":
    main()
