#!/usr/bin/env python3
"""
Evaluate collected LLM responses against ground truth.

Reads response CSVs (from run_experiment.py), parses the final answer from
response_text, and computes accuracy overall and per distance bin.

Usage:
  python evaluate.py --input results/adj_responses_claude-sonnet-4-6.csv
  python evaluate.py                    # evaluate all *_responses_*.csv files
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"

BINS = ["near", "medium", "far"]


def extract_integer(text: str) -> int:
    """Extract the last integer from text. Returns -1 if none found."""
    numbers = re.findall(r'-?\b(\d+)\b', text)
    return int(numbers[-1]) if numbers else -1


def get_final_answer_text(response_text: str) -> str:
    """Extract the final answer text from response_text.

    For codegen agent responses (JSON array), returns the last assistant text.
    For raw/adj responses (plain text), returns as-is.
    """
    try:
        trace = json.loads(response_text)
        if isinstance(trace, list):
            for entry in reversed(trace):
                if entry.get("role") == "assistant":
                    return entry["text"]
            return ""
    except (json.JSONDecodeError, TypeError):
        pass
    return response_text


def evaluate_file(path: Path) -> list[dict]:
    """Read a responses CSV, parse answers, return evaluated rows."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    results = []
    for row in rows:
        answer_text = get_final_answer_text(row["response_text"])
        predicted = extract_integer(answer_text)
        gt = int(row["ground_truth_distance"])
        correct = predicted == gt
        results.append({
            **row,
            "predicted": predicted,
            "correct": correct,
        })
    return results


def compute_accuracy(rows: list) -> dict:
    """Returns nested dict: {bin: {n, correct, accuracy}}"""
    stats = defaultdict(lambda: {"n": 0, "correct": 0})
    for row in rows:
        b = row["bin"]
        stats[b]["n"] += 1
        if row["correct"]:
            stats[b]["correct"] += 1

    result = {}
    for b, s in stats.items():
        acc = s["correct"] / s["n"] if s["n"] > 0 else 0.0
        result[b] = {"n": s["n"], "correct": s["correct"], "accuracy": acc}

    total_n = sum(s["n"] for s in stats.values())
    total_c = sum(s["correct"] for s in stats.values())
    result["overall"] = {
        "n": total_n,
        "correct": total_c,
        "accuracy": total_c / total_n if total_n > 0 else 0.0,
    }
    return result


def print_single(label: str, stats: dict):
    """Print accuracy for a single file."""
    bin_cols = BINS + ["overall"]
    header = "".join(f"{b:>12}" for b in bin_cols)
    print(f"\n{label}")
    print(f"{'':>12}{header}")
    row_str = f"{'':>12}"
    for b in bin_cols:
        if b in stats:
            acc = stats[b]["accuracy"]
            n = stats[b]["n"]
            row_str += f"{acc*100:>8.1f}%({n})"
        else:
            row_str += f"{'N/A':>12}"
    print(row_str)


def print_table(all_stats: dict):
    """Print comparison table across multiple files."""
    bin_cols = BINS + ["overall"]
    conditions = list(all_stats.keys())

    print("\n" + "=" * 88)
    print("BASELINE RESULTS")
    print("=" * 88)

    header = f"{'Condition':<40}" + "".join(f"{b:>12}" for b in bin_cols)
    print(header)
    print("-" * len(header))
    for cond in conditions:
        stats = all_stats[cond]
        row_str = f"{cond:<40}"
        for b in bin_cols:
            if b in stats:
                acc = stats[b]["accuracy"]
                n = stats[b]["n"]
                row_str += f"{acc*100:>8.1f}%({n})"
            else:
                row_str += f"{'N/A':>12}"
        print(row_str)

    print("=" * 88)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=None, help="Path to a single responses CSV")
    args = parser.parse_args()

    if args.input:
        # Single file mode
        path = Path(args.input)
        if not path.exists():
            print(f"ERROR: {path} not found.", file=sys.stderr)
            sys.exit(1)

        results = evaluate_file(path)
        stats = compute_accuracy(results)
        print_single(path.name, stats)

        # Save evaluated CSV
        output_path = path.with_name(
            path.stem.replace("_responses_", "_evaluated_") + ".csv"
        )
        fieldnames = [
            "network", "source_edge", "target_edge",
            "ground_truth_distance", "bin",
            "predicted", "correct", "response_text",
        ]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"Evaluated results saved to {output_path}")

    else:
        # All files mode
        files = sorted(RESULTS_DIR.glob("*_responses_*.csv"))
        if not files:
            print("No response files found in results/.", file=sys.stderr)
            sys.exit(1)

        all_stats = {}
        for path in files:
            label = path.stem.replace("_responses_", " / ")
            results = evaluate_file(path)
            all_stats[label] = compute_accuracy(results)

        print_table(all_stats)


if __name__ == "__main__":
    main()
