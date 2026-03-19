#!/usr/bin/env python3
"""
Evaluate collected LLM responses across different NetTrafficQA tasks.

Usage:
  python evaluate.py --task QAdataset/feature_retrieval
  python evaluate.py --task QAdataset/pathfinding/shortest_path_distance --input QAdataset/pathfinding/shortest_path_distance/results/adj_responses_claude-sonnet-4-6.csv
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Common logic from existing evaluate.py
def extract_integer(text: str) -> int:
    """Extract the last integer from text. Returns -1 if none found."""
    numbers = re.findall(r'-?\b(\d+)\b', text)
    return int(numbers[-1]) if numbers else -1

def get_final_answer_text(response_text: str) -> str:
    """Extract the final answer text from response_text."""
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

def compare_answers(predicted: str, ground_truth: str, task_type: str = "") -> bool:
    """
    Compare predicted and ground truth answers.
    Support fuzzy matching for list of items or case-insensitive matching.
    """
    p = predicted.strip().lower()
    gt = ground_truth.strip().lower()
    
    # Extract all relevant entities (IDs or numbers) from both
    p_items = re.findall(r'[a-zA-Z0-9_\-:]+', p)
    gt_items = re.findall(r'[a-zA-Z0-9_\-:]+', gt)

    # Simple exact match
    if p == gt: return True
    
    # Simple single-item presence (if GT is just one ID)
    if len(gt_items) == 1 and len(p_items) >= 1:
        return gt_items[0] in p_items

    # If ground truth is a list (path tasks require order)
    if "path" in task_type and " -> " in ground_truth:
        # For paths, we look for the exact sequence anywhere in the response
        # or just extract the sequence of IDs and compare
        # Filter p_items to only include things that look like they could be IDs (alphanumeric)
        p_seq = [x for x in p_items if any(c.isalpha() for c in x) or any(c.isdigit() for c in x)]
        # This is a bit risky but standard for such benchmarks
        return gt_items == p_seq[:len(gt_items)] or gt_items == p_seq[-len(gt_items):]

    # For general list matching (unsorted set)
    if "," in ground_truth or " " in ground_truth:
        # If the ground truth has multiple items, we check if the sets match
        # To avoid extra noise, we filter response items to match the "shape" of GT items if possible
        # but here we'll just use a simple set comparison on extracted tokens
        p_set = set(p_items)
        gt_set = set(gt_items)
        return gt_set.issubset(p_set) and len(gt_set) > 0 # At least match all GT items
        
    # If it's an integer/number task
    if any(task in task_type for task in ["distance", "lanes", "length", "count"]):
        try:
            # Extract numbers
            p_nums = re.findall(r'\d+\.\d+|\d+', p)
            if not p_nums: return False
            p_val = float(p_nums[0])
            gt_val = float(gt)
            if "length" in task_type:
                return abs(p_val - gt_val) < 1.0
            return int(p_val) == int(gt_val)
        except: pass
        
    return False

def evaluate_file(path: Path) -> list[dict]:
    """Read a responses CSV, parse answers, return evaluated rows."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    results = []
    for row in rows:
        answer_text = get_final_answer_text(row["response_text"])
        gt = row["ground_truth"]
        task_type = row.get("type", "")
        
        correct = compare_answers(answer_text, gt, task_type)
        results.append({
            **row,
            "predicted": answer_text,
            "correct": correct,
        })
    return results

def compute_accuracy(rows: list, bin_field: str = None) -> dict:
    """Returns nested dict with statistics."""
    stats = defaultdict(lambda: {"n": 0, "correct": 0})
    for row in rows:
        b = row.get(bin_field, "overall") if bin_field else "overall"
        stats[b]["n"] += 1
        if row["correct"]:
            stats[b]["correct"] += 1

    result = {}
    for b, s in stats.items():
        acc = s["correct"] / s["n"] if s["n"] > 0 else 0.0
        result[b] = {"n": s["n"], "correct": s["correct"], "accuracy": acc}

    if "overall" not in result:
        total_n = sum(s["n"] for s in stats.values())
        total_c = sum(s["correct"] for s in stats.values())
        result["overall"] = {
            "n": total_n,
            "correct": total_c,
            "accuracy": total_c / total_n if total_n > 0 else 0.0,
        }
    return result

def print_table(all_stats: dict, bins=None):
    """Print comparison table across multiple files."""
    bin_cols = bins + ["overall"] if bins else ["overall"]
    conditions = list(all_stats.keys())

    print("\n" + "=" * 88)
    print("EVALUATION RESULTS")
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
    parser.add_argument("--task", required=True, help="Task directory e.g., QAdataset/feature_retrieval")
    parser.add_argument("--baseline", default=None, help="Baseline to filter (e.g., adj)")
    parser.add_argument("--model", default=None, help="Model to filter (e.g., claude-3-5-sonnet-20240620)")
    parser.add_argument("--network", default=None, help="Network to filter (e.g., grid_11x11)")
    parser.add_argument("--n", default=None, help="N to filter (e.g., n10)")
    parser.add_argument("--type", choices=["feature_retrieval", "network_comprehension", "pathfinding"], default=None, help="Force evaluation of a specific task category")
    parser.add_argument("--input", default=None, help="Path to a single responses CSV (ignores other filters)")
    args = parser.parse_args()

    task_base = Path(args.task)
    
    if args.input:
        files = [Path(args.input)]
    else:
        # Search for response files recursively if task_base is a root
        potential_files = sorted(task_base.glob("**/results/*_responses_*.csv"))
        files = []
        for p in potential_files:
            stem = p.name
            path_str = str(p)
            if args.baseline and not stem.startswith(f"{args.baseline}_responses_"): continue
            if args.network and f"_{args.network}_" not in stem: continue
            if args.model and not stem.endswith(f"_{args.model}.csv"): continue
            if args.n and f"_n{args.n}" not in stem: continue
            
            # Type filter strictly matches the task category in the folder path
            if args.type and args.type not in p.parts: continue
            files.append(p)

    if not files:
        print(f"No response files found under {task_base} matching filters.", file=sys.stderr)
        return

    # Check if task uses bins
    use_bins = None
    if "shortest_path_distance" in str(task_base) or (args.type == "shortest_path_distance"):
        use_bins = ["near", "medium", "far"]

    # Data collection for individual and aggregate (group by network/baseline/model)
    all_stats = {}
    grouped_rows = defaultdict(list)
    
    for path in files:
        # Define grouping key (e.g. "baseline | model | network")
        # Extract metadata from stem if possible
        # For simplicity, we can just group by the common part before 'responses' and after
        # Meta data from path
        # Extract category from path (folder name before 'results')
        # path format is: .../{category}/results/...
        cat_folder = "unknown"
        if "results" in path.parts:
            idx = list(path.parts).index("results")
            if idx > 0: cat_folder = path.parts[idx-1]
            
        parts = path.stem.split("_responses_")
        baseline = parts[0]
        rest = parts[1]
        
        # Heuristic: find network and type
        network = "unknown"
        for n in ["grid_11x11", "random"]:
            if n in rest: network = n; break
        
        # Model part at the end
        model_part = path.stem.split("_")[-1].replace(".csv", "")
        
        # Reordered Grouping based on baseline | network | type | model
        group_key = f"{baseline} | {network} | {cat_folder} | {model_part}"
        
        label = path.stem.replace("_responses_", " / ")
        results = evaluate_file(path)
        all_stats[label] = compute_accuracy(results, bin_field="bin" if use_bins else None)
        grouped_rows[group_key].extend(results)
        
        # Save evaluated results
        output_path = path.with_name(path.stem.replace("_responses_", "_evaluated_") + ".csv")
        fieldnames = list(results[0].keys())
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"  Processed {path.name} -> {output_path.name}")

    # Aggregated Stats by Group
    agg_stats = {}
    for group, rows in grouped_rows.items():
        agg_stats[f"[Group: {group}]"] = compute_accuracy(rows, bin_field="bin" if use_bins else None)
    
    # Merge for printing
    final_view = {**agg_stats, **all_stats}
    print_table(final_view, bins=use_bins)

if __name__ == "__main__":
    main()
