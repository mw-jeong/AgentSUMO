#!/usr/bin/env python3
"""전략별 정확도 비교 출력."""

import csv
from pathlib import Path

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"

STRATEGIES = ["01_autonomous", "02_neighbor", "03_cross", "04_exhaustive"]
STRATEGY_NAMES = ["autonomous", "neighbor", "cross", "exhaustive"]


def load_strategy_data(strategy: str) -> dict:
    """Load answers from CSV for a strategy."""
    csv_file = RESULTS_DIR / f"{strategy}_answers.csv"
    data = {}
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            edge_id = row['edge_id']
            data[edge_id] = {
                'answer': row['answer'].strip(),
                'gt_answer': row['gt_answer'].strip(),
                'correct': 1 if row['answer'].strip().upper() == row['gt_answer'].strip().upper() else 0
            }
    return data


def main():
    all_data = {}
    for strat in STRATEGIES:
        all_data[strat] = load_strategy_data(strat)

    edge_ids = list(all_data[STRATEGIES[0]].keys())
    total = len(edge_ids)

    # 전략별 정답 수 계산
    strategy_correct = {s: 0 for s in STRATEGIES}
    all_correct = []
    all_wrong = []

    for edge_id in edge_ids:
        correct_count = 0
        for strat in STRATEGIES:
            if all_data[strat][edge_id]['correct']:
                strategy_correct[strat] += 1
                correct_count += 1

        if correct_count == 4:
            all_correct.append(edge_id)
        elif correct_count == 0:
            all_wrong.append(edge_id)

    # 출력
    print(f"\n{'='*50}")
    print(" 전략별 정확도")
    print(f"{'='*50}")
    print(f"| {'전략':<12} | {'정답':<8} | {'정확도':<10} |")
    print(f"|{'-'*14}|{'-'*10}|{'-'*12}|")
    for i, strat in enumerate(STRATEGIES):
        correct = strategy_correct[strat]
        acc = correct / total * 100
        print(f"| {STRATEGY_NAMES[i]:<12} | {correct}/{total:<6} | {acc:>6.1f}%    |")

    print(f"\n[모든 전략 정답] ({len(all_correct)}개): {', '.join(all_correct)}")
    print(f"[모든 전략 오답] ({len(all_wrong)}개): {', '.join(all_wrong)}")


if __name__ == "__main__":
    main()
