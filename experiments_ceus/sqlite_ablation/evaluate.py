#!/usr/bin/env python3
"""
SQLite Ablation - Evaluation Script

Compares experiment results against ground truth.
All questions are evaluated as exact_match (numeric included).

Levels:
  L1: Single-simulation retrieval (5 questions)
  L2: Single-simulation aggregation (5 questions)
  L3+L4: Multi-simulation reasoning (10 questions)

Usage:
    python -m experiments_ceus.sqlite_ablation.evaluate
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
GT_DIR = BASE_DIR / "ground_truth"

CITIES = ["gangnam_small", "timessquare_small"]
CONDITIONS = ["full", "xml_only", "no_data"]

# Level grouping: L3+L4 merged into "L3L4"
LEVEL_GROUPS = {
    "L1": ["L1"],
    "L2": ["L2"],
    "L3L4": ["L3", "L4"],
}


def extract_number(text: str) -> float | None:
    """Extract the final answer number from LLM response."""
    # Pattern 1: **Answer: 123.45**
    m = re.search(r'\*\*(?:Answer|답)[:\s]*([+-]?[\d,]+\.?\d*)', text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(',', ''))

    # Pattern 2: any bold containing a number (with optional sign, unit, etc.)
    # Matches: **18.0 seconds**, **+1.45%**, **Reduction: 22.22%**, **662.68 mg**
    bolds = re.findall(r'\*\*[^*]*?([+-]?[\d,]+\.?\d*)\s*(?:초|seconds|mg|%|veh/km|m/s|ml|g|kg|대/km)?\s*(?:\([^)]*\))?\s*\*\*', text)
    if bolds:
        # Filter out zeros and very small noise, take last meaningful number
        nums = [float(b.replace(',', '')) for b in bolds if b.strip() and re.match(r'^[+-]?[\d,]+\.?\d*$', b.strip())]
        if nums:
            return nums[-1]

    # Pattern 3: "= **123.45" or "is **123.45"
    m = re.search(r'(?:=|is)\s*\*\*\s*([+-]?[\d,]+\.?\d*)', text)
    if m:
        return float(m.group(1).replace(',', ''))

    # Pattern 4: last number in text as fallback
    nums = re.findall(r'([+-]?\d[\d,]*\.?\d*)', text)
    if nums:
        return float(nums[-1].replace(',', ''))

    return None


def extract_choice(text: str) -> str | None:
    """Extract Webster or Green Wave choice from LLM response."""
    # Check bold patterns first
    bolds = re.findall(r'\*\*(\w[\w\s]*?)\*\*', text)
    for b in bolds:
        bl = b.lower().strip()
        if 'webster' in bl:
            return 'Webster'
        if 'green wave' in bl or bl == 'green':
            return 'Green Wave'

    # Fallback: first mention
    text_lower = text.lower()
    w_pos = text_lower.find('webster')
    g_pos = text_lower.find('green wave')
    if w_pos >= 0 and g_pos >= 0:
        return 'Webster' if w_pos < g_pos else 'Green Wave'
    if w_pos >= 0:
        return 'Webster'
    if g_pos >= 0:
        return 'Green Wave'

    return None


def evaluate_numeric_exact(gt_answer: float, response: str, tolerance: float = 0.05) -> tuple[bool | None, float | None]:
    """Evaluate numeric question as exact match with tolerance."""
    extracted = extract_number(response)
    if extracted is None:
        return None, None

    if gt_answer == 0:
        return abs(extracted) < 0.5, extracted

    error = abs(extracted - gt_answer) / abs(gt_answer)
    return error <= tolerance, extracted


def evaluate_choice(gt_answer: str, response: str) -> tuple[bool | None, str | None]:
    """Evaluate exact match choice question."""
    choice = extract_choice(response)
    if choice is None:
        return None, None
    return choice.lower() == gt_answer.lower(), choice


def evaluate_question(gt_entry: dict, response: str) -> tuple[bool | None, str]:
    """Evaluate a single question. Returns (correct, extracted_str)."""
    eval_type = gt_entry["eval"]
    answer = gt_entry["answer"]

    if eval_type == "numeric":
        correct, extracted = evaluate_numeric_exact(answer, response)
        ext_str = f"{extracted:,.2f}" if extracted is not None else "N/A"
        return correct, ext_str

    elif eval_type == "exact_match":
        correct, extracted = evaluate_choice(answer, response)
        ext_str = extracted if extracted else "N/A"
        return correct, ext_str

    return None, "unknown"


def get_level_group(qid: str) -> str:
    """Map question ID to level group."""
    level = qid.split("_")[0]
    for group, levels in LEVEL_GROUPS.items():
        if level in levels:
            return group
    return level


def evaluate_city(city: str):
    """Evaluate all conditions for a city."""
    gt_path = GT_DIR / f"gt_{city}.json"
    if not gt_path.exists():
        print(f"  GT not found: {gt_path}")
        return None

    with open(gt_path) as f:
        gt = json.load(f)

    results = {}

    for cond in CONDITIONS:
        log_path = RESULTS_DIR / city / cond / "experiment_log.json"
        if not log_path.exists():
            results[cond] = None
            continue

        with open(log_path) as f:
            data = json.load(f)

        cond_result = {
            "questions": {},
            "summary": data.get("summary", {}),
            "metadata": data.get("metadata", {}),
            "by_group": {g: {"correct": 0, "total": 0} for g in LEVEL_GROUPS},
            "overall": {"correct": 0, "total": 0},
        }

        # Build response lookup
        responses = {q["question_id"]: q for q in data["question_results"]}

        for qid in sorted(gt.keys()):
            gt_entry = gt[qid]
            group = get_level_group(qid)

            if qid not in responses:
                cond_result["questions"][qid] = {
                    "correct": None, "extracted": "MISSING", "gt": gt_entry["answer"]
                }
                cond_result["by_group"][group]["total"] += 1
                cond_result["overall"]["total"] += 1
                continue

            response = responses[qid]["response"]
            correct, ext_str = evaluate_question(gt_entry, response)

            cond_result["questions"][qid] = {
                "correct": correct,
                "extracted": ext_str,
                "gt": gt_entry["answer"],
                "tokens": responses[qid].get("total_tokens", 0),
                "elapsed": responses[qid].get("elapsed_seconds", 0),
                "api_calls": responses[qid].get("api_calls", 0),
            }

            cond_result["by_group"][group]["total"] += 1
            cond_result["overall"]["total"] += 1
            if correct:
                cond_result["by_group"][group]["correct"] += 1
                cond_result["overall"]["correct"] += 1

        results[cond] = cond_result

    return gt, results


def print_results(city: str, gt: dict, results: dict):
    """Print formatted results table."""
    print(f"\n{'=' * 110}")
    print(f"  {city.upper()}")
    print(f"{'=' * 110}")

    # Header
    header = f"{'ID':<8} {'Group':<6} {'GT':<18}"
    for cond in CONDITIONS:
        header += f" {'':>1}{cond:<18}"
    print(header)
    print("-" * 110)

    prev_group = None
    for qid in sorted(gt.keys()):
        gt_entry = gt[qid]
        group = get_level_group(qid)
        gt_ans = gt_entry["answer"]

        if prev_group and prev_group != group:
            print()
        prev_group = group

        if isinstance(gt_ans, float):
            if abs(gt_ans) >= 1000:
                gt_str = f"{gt_ans:,.0f}"
            else:
                gt_str = f"{gt_ans:.2f}"
        else:
            gt_str = str(gt_ans)

        row = f"{qid:<8} {group:<6} {gt_str:<18}"

        for cond in CONDITIONS:
            if results[cond] is None:
                row += f" {'N/A':<19}"
                continue

            q = results[cond]["questions"].get(qid)
            if q is None:
                row += f" {'N/A':<19}"
                continue

            if q["correct"] is None:
                mark = "?"
            elif q["correct"]:
                mark = "O"
            else:
                mark = "X"

            ext = q["extracted"]
            if isinstance(ext, str) and len(ext) > 14:
                ext = ext[:14]

            row += f" {mark} {ext:<17}"

        print(row)

    # Summary table
    print(f"\n{'--- Summary ---':^110}")
    print(f"{'':12} {'Accuracy':<14}", end="")
    for g in LEVEL_GROUPS:
        print(f" {g:<12}", end="")
    print(f" {'Tokens':<12} {'API':<6} {'Tools':<6} {'Time':<8}")
    print("-" * 110)

    for cond in CONDITIONS:
        if results[cond] is None:
            print(f"  {cond:<10} N/A")
            continue

        r = results[cond]
        ov = r["overall"]
        pct = ov["correct"] / ov["total"] * 100 if ov["total"] > 0 else 0

        print(f"  {cond:<10} {ov['correct']}/{ov['total']} ({pct:4.0f}%)  ", end="")

        for g in LEVEL_GROUPS:
            bg = r["by_group"][g]
            print(f" {bg['correct']}/{bg['total']:<10}", end="")

        s = r["summary"]
        m = r["metadata"]
        tokens = s.get("total_tokens", 0)
        api = s.get("total_api_calls", 0)
        tools = s.get("total_tool_calls", 0)
        time_s = m.get("session_duration_seconds", 0)

        print(f" {tokens:>10,}  {api:>4}  {tools:>4}  {time_s:>6.0f}s")


def print_aggregate(all_results: dict):
    """Print aggregate across all cities."""
    print(f"\n{'=' * 110}")
    print(f"  AGGREGATE (ALL CITIES)")
    print(f"{'=' * 110}")

    print(f"\n{'':12} {'Accuracy':<14}", end="")
    for g in LEVEL_GROUPS:
        print(f" {g:<12}", end="")
    print(f" {'Tokens':<12} {'Avg Time':<10}")
    print("-" * 90)

    for cond in CONDITIONS:
        total_correct = 0
        total_questions = 0
        total_tokens = 0
        total_time = 0
        group_agg = {g: {"correct": 0, "total": 0} for g in LEVEL_GROUPS}
        n_cities = 0

        for city, (gt, results) in all_results.items():
            if results[cond] is None:
                continue
            r = results[cond]
            total_correct += r["overall"]["correct"]
            total_questions += r["overall"]["total"]
            total_tokens += r["summary"].get("total_tokens", 0)
            total_time += r["metadata"].get("session_duration_seconds", 0)
            n_cities += 1
            for g in LEVEL_GROUPS:
                group_agg[g]["correct"] += r["by_group"][g]["correct"]
                group_agg[g]["total"] += r["by_group"][g]["total"]

        if total_questions == 0:
            print(f"  {cond:<10} N/A")
            continue

        pct = total_correct / total_questions * 100
        avg_time = total_time / n_cities if n_cities > 0 else 0

        print(f"  {cond:<10} {total_correct}/{total_questions} ({pct:4.0f}%)  ", end="")
        for g in LEVEL_GROUPS:
            bg = group_agg[g]
            print(f" {bg['correct']}/{bg['total']:<10}", end="")
        print(f" {total_tokens:>10,}  {avg_time:>7.0f}s")


def main():
    all_results = {}

    for city in CITIES:
        result = evaluate_city(city)
        if result is None:
            continue
        gt, results = result
        all_results[city] = (gt, results)
        print_results(city, gt, results)

    if len(all_results) > 1:
        print_aggregate(all_results)


if __name__ == "__main__":
    main()
