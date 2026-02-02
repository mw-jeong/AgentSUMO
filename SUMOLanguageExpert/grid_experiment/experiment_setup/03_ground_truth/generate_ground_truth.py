#!/usr/bin/env python3
"""
Generate Ground Truth CSV from simulation JSON files.

Question type:
- Q6: baseline 대비 density가 가장 증가한 엣지는 어느 열(A~K) 또는 행(0~10)에 있는가?
      → Answer: "A"~"K" (vertical edges) or "0"~"10" (horizontal edges)

Grid 네트워크 엣지 명명 규칙:
- A0A1: A열의 수직 엣지 (vertical, column A)
- B3C3: 3행의 수평 엣지 (horizontal, row 3)
"""

import json
import csv
import re
from pathlib import Path


# Paths relative to this script
BASE_DIR = Path(__file__).parent.parent
RESULTS_DIR = BASE_DIR / "results"


def parse_edge(edge_id):
    """Parse edge ID to extract direction and road info.

    Returns:
        dict with 'direction' ('vertical' or 'horizontal') and road info
        - vertical: {'direction': 'vertical', 'col': 'A', 'row': 0}
        - horizontal: {'direction': 'horizontal', 'row': 3, 'col': 'B'}
        None if edge_id is invalid or internal
    """
    if not edge_id or len(edge_id) != 4 or edge_id.startswith(':'):
        return None

    try:
        from_col = edge_id[0]
        from_row = int(edge_id[1])
        to_col = edge_id[2]
        to_row = int(edge_id[3])
    except (ValueError, IndexError):
        return None

    if from_col == to_col:
        # Vertical edge (same column)
        return {
            'direction': 'vertical',
            'col': from_col,
            'row': min(from_row, to_row)
        }
    else:
        # Horizontal edge (same row)
        return {
            'direction': 'horizontal',
            'row': from_row,
            'col': min(from_col, to_col, key=lambda x: ord(x))
        }


def get_road_name(edge_id):
    """Get road name for an edge.

    - Vertical edges: column name (A~H)
    - Horizontal edges: row number (0~7)
    """
    parsed = parse_edge(edge_id)
    if not parsed:
        return None

    if parsed['direction'] == 'vertical':
        return parsed['col']  # e.g., "A", "B", ...
    else:
        return str(parsed['row'])  # e.g., "0", "1", ...


def find_json_files():
    """train_*.json, test_*.json 파일 동적 탐색"""
    train_files = list(RESULTS_DIR.glob("train_*.json"))
    test_files = list(RESULTS_DIR.glob("test_*.json"))

    if not train_files:
        raise FileNotFoundError(f"No train_*.json found in {RESULTS_DIR}")
    if not test_files:
        raise FileNotFoundError(f"No test_*.json found in {RESULTS_DIR}")

    # 가장 최신 파일 사용 (숫자가 큰 것)
    train_json = sorted(train_files)[-1]
    test_json = sorted(test_files)[-1]

    return train_json, test_json


def load_baseline_metrics(train_json: Path):
    """Load baseline edge metrics (density) for comparison."""
    with open(train_json, 'r') as f:
        data = json.load(f)

    # First simulation is baseline
    baseline = data["simulations"][0]

    baseline_edge_metrics = {}
    for em in baseline["edge_metrics"]:
        edge_id = em["edge_id"]
        if edge_id.startswith(":"):
            continue
        baseline_edge_metrics[edge_id] = em["density"]

    return baseline_edge_metrics


def compute_q6_for_simulation(sim_data, baseline_edge_metrics):
    """Compute Q6: Which road (column A~H or row 0~7) has the edge with largest density increase?

    Returns: "A"~"H" for vertical edges, "0"~"7" for horizontal edges
    """
    max_increase = -float('inf')
    max_edge_id = None

    for em in sim_data["edge_metrics"]:
        edge_id = em["edge_id"]
        if not parse_edge(edge_id):
            continue

        baseline_density = baseline_edge_metrics.get(edge_id, 0)
        increase = em["density"] - baseline_density

        if increase > max_increase:
            max_increase = increase
            max_edge_id = edge_id

    if not max_edge_id:
        return ""

    return get_road_name(max_edge_id) or ""


def generate_gt_csv(json_file: Path, output_csv: Path, baseline_edge_metrics, skip_baseline=False):
    """Generate ground truth CSV from JSON file."""
    with open(json_file, 'r') as f:
        data = json.load(f)

    simulations = data["simulations"]
    if skip_baseline:
        simulations = simulations[1:]  # Skip baseline

    rows = []
    for sim_data in simulations:
        sim_info = sim_data["simulation"]
        edge_info = sim_info.get("edge_info", {})

        # Edge description (e.g., "A0A1 edge removed")
        edge_id = edge_info.get("edge_id", "")
        edge_desc = f"{edge_id} edge removed"

        q6_answer = compute_q6_for_simulation(sim_data, baseline_edge_metrics)

        rows.append({
            "edge": edge_desc,
            "Q6_max_density_road": q6_answer,
        })

    # Write CSV
    fieldnames = ["edge", "Q6_max_density_road"]

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated: {output_csv} ({len(rows)} rows)")
    return rows


def main():
    print("=" * 60)
    print("Generate Ground Truth CSVs (Q6: road name)")
    print("=" * 60)

    print("\nQuestion definition:")
    print("  Q6: density가 가장 증가한 엣지는 어느 열(A~K) 또는 행(0~10)에 있는가?")

    # Find JSON files dynamically
    print("\nFinding JSON files...")
    train_json, test_json = find_json_files()
    print(f"  Train: {train_json.name}")
    print(f"  Test: {test_json.name}")

    # Load baseline for comparison
    print("\nLoading baseline metrics...")
    baseline_edge_metrics = load_baseline_metrics(train_json)
    print(f"Loaded {len(baseline_edge_metrics)} edge density metrics from baseline")

    # Extract counts from filenames
    train_match = re.search(r'train_(\d+)\.json', train_json.name)
    test_match = re.search(r'test_(\d+)\.json', test_json.name)
    train_count = int(train_match.group(1)) if train_match else 0
    test_count = int(test_match.group(1)) if test_match else 0

    # Generate test GT
    test_csv = RESULTS_DIR / f"ground_truth_test_{test_count}.csv"
    test_rows = generate_gt_csv(test_json, test_csv, baseline_edge_metrics)

    # Generate train GT (exclude baseline)
    train_csv = RESULTS_DIR / f"ground_truth_train_{train_count - 1}.csv"
    train_rows = generate_gt_csv(train_json, train_csv, baseline_edge_metrics, skip_baseline=True)

    # Print summary statistics
    print("\n" + "=" * 60)
    print("Summary Statistics")
    print("=" * 60)

    for name, rows in [("Train", train_rows), ("Test", test_rows)]:
        q6_cols = sum(1 for r in rows if r["Q6_max_density_road"] in "ABCDEFGHIJK")
        q6_rows = len(rows) - q6_cols

        print(f"\n{name} ({len(rows)} simulations):")
        print(f"  Q6: columns(A-K)={q6_cols} ({100*q6_cols/len(rows):.1f}%), rows(0-10)={q6_rows} ({100*q6_rows/len(rows):.1f}%)")

    print("\nDone!")


if __name__ == "__main__":
    main()
