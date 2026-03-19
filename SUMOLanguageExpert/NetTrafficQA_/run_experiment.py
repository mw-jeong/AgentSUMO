#!/usr/bin/env python3
"""
Collect LLM responses for a specific QA task using a chosen baseline.

Usage:
  python run_experiment.py --task QAdataset/feature_retrieval --baseline adj
  python run_experiment.py --task QAdataset/pathfinding/shortest_path_distance --baseline raw
"""

import argparse
import csv
import sys
from pathlib import Path

# Add scripts to path
SCRIPTS_DIR = Path(__file__).parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from utils import DEFAULT_MODEL
from methods import METHODS

def get_qa_files(task_dir: Path, network: str = "all") -> list[Path]:
    """Retrieve list of CSV files to process."""
    questions_dir = task_dir / "questions"
    search_dir = questions_dir if questions_dir.exists() else task_dir
    
    if network == "all":
        paths = sorted([p for p in search_dir.glob("*.csv") if p.is_file()])
    else:
        paths = sorted([p for p in search_dir.glob(f"{network}_*.csv") if p.is_file()])
        if not paths:
            # Fallback for old structure or specific names
            for name in [f"{network}_qa_pairs.csv", "qa_pairs.csv"]:
                p = search_dir / name
                if p.exists(): paths.append(p)
    return paths

def load_qa_rows(path: Path, n: int | None = None) -> list[dict]:
    """Load rows from a single CSV file."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[:n] if n else rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="Path to task directory (e.g., QAdataset/feature_retrieval)")
    parser.add_argument("--baseline", required=True, choices=list(METHODS.keys()))
    parser.add_argument("--network", default="all", help="Network name (e.g., grid_11x11, random, all)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--n", type=int, default=None, help="Limit to first N rows")
    args = parser.parse_args()

    task_dir = Path(args.task)
    if not task_dir.is_dir():
        # Try relative to current script
        task_dir = Path(__file__).parent / args.task
        
    ask_fn = METHODS[args.baseline]
    qa_files = get_qa_files(task_dir, args.network)
    
    if not qa_files:
        print(f"ERROR: No QA files found in {task_dir}")
        sys.exit(1)

    results_dir = task_dir / "results"
    results_dir.mkdir(exist_ok=True)
    
    print(f"Starting experiment: task={args.task}, baseline={args.baseline}, network={args.network}, model={args.model}")
    
    for qa_path in qa_files:
        rows = load_qa_rows(qa_path, args.n)
        if not rows: continue
        
        print(f"\nProcessing {qa_path.name} ({len(rows)} questions)")
        n_str = f"_n{args.n}" if args.n else ""
        output_path = results_dir / f"{args.baseline}_responses_{qa_path.stem}{n_str}_{args.model}.csv"
        
        fieldnames = list(rows[0].keys())
        if "response_text" not in fieldnames:
            fieldnames.append("response_text")

        results = []
        for i, row in enumerate(rows, start=1):
            network = row["network"]
            question = row["question"]
            
            print(f"  [{i}/{len(rows)}] {question[:60]}...")
            
            try:
                resp_text = ask_fn(network, question, args.model)
                print(f"    Response: {resp_text[:80]}...")
            except Exception as e:
                print(f"    ERROR: {e}")
                resp_text = f"ERROR: {e}"

            results.append({
                **row,
                "response_text": resp_text,
            })

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"  Results saved to {output_path.name}")

    print(f"\nAll experiments done.")

if __name__ == "__main__":
    main()
