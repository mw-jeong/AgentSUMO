#!/usr/bin/env python3
"""
Heuristic baseline that uses distance-weighted nearest-neighbor regression
over training simulations (from `ground_truth_train_176.csv`) to predict,
for each unseen removed edge, which edge in the grid will have the largest
density increase (column A–K or row 0–10), without calling any LLM.

Heuristic baseline for the grid experiment (no LLM).

This script:
- Loads the same test edges / ground-truth as `run_experiment.py`
- Reads the training SQLite DB in `experiment_setup/results/simulations.db`
- Extracts training samples via SQL:
  - Each training sample corresponds to one "X edge removed" simulation
  - For each such simulation, it finds the road segment with the largest
    density INCREASE compared to a baseline simulation of the same network
- Represents each removed edge on an 11x11 grid and computes spatial
  distances between edges
- Performs a distance‑weighted k‑NN style regression/classification over
  the training samples to predict the answer (column A‑K or row 0‑10)
  for unseen test edges.

Assumptions (documented so they can be adjusted if needed):
- Baseline simulations exist in the DB with a `description` that contains
  the word "baseline" (case‑insensitive). For each training simulation,
  we search for a baseline with the same `(net_file, route_file)`.
- `simulations.description` follows the pattern "`<EDGE_ID> edge removed`"
  for training simulations, so we can recover the removed edge.
- `edge_metrics` contains a `density` column for each `(simulation_id,
  edge_id, interval_begin, interval_end)`. We compute average density
  increase per edge by differencing with the corresponding baseline
  metrics and then averaging over all intervals.
- The answer definition matches the ground‑truth logic:
  - For vertical edges (same column), the label is the column letter
    (A‑K) of the congested edge.
  - For horizontal edges (same row), the label is the row index string
    ("0"‑"10") of the congested edge.

If any of these assumptions are different in your data, adapt the CSV
parsing or geometric logic below accordingly.
"""

import csv
import json
import math
import random
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================
# Paths / shared settings (aligned with run_experiment.py)
# ============================================================
BASE_DIR = Path(__file__).parent
SETUP_DIR = BASE_DIR / "experiment_setup"
DATA_DIR = SETUP_DIR / "results"
RESULTS_DIR = BASE_DIR / "results"


# ============================================================
# Utilities for edge geometry on the 11x11 grid
# ============================================================

@dataclass
class EdgeGeom:
    """Geometric representation of an edge on the grid."""

    edge_id: str
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def midpoint(self) -> Tuple[float, float]:
        return (0.5 * (self.x1 + self.x2), 0.5 * (self.y1 + self.y2))

    @property
    def is_vertical(self) -> bool:
        return self.x1 == self.x2

    @property
    def is_horizontal(self) -> bool:
        return self.y1 == self.y2


def _node_to_xy(node: str) -> Tuple[int, int]:
    """
    Convert a node like 'C3' to integer grid coordinates (x, y).

    - Columns: A-K -> x = 0-10
    - Rows: '0'-'10' -> y = 0-10
    """
    if len(node) < 2:
        raise ValueError(f"Invalid node format: {node}")

    col = node[0].upper()
    row_str = node[1:]
    if not row_str.isdigit():
        raise ValueError(f"Invalid node row in '{node}'")

    x = ord(col) - ord("A")
    y = int(row_str)
    return x, y


def parse_edge_geom(edge_id: str) -> EdgeGeom:
    """
    Parse an edge ID like 'C3C4' or 'C3D3' into geometry.

    We assume the pattern is two concatenated nodes: [A-K][0-9]+[A-K][0-9]+.
    """
    edge_id = edge_id.strip()
    if not edge_id:
        raise ValueError("Empty edge_id")

    # Find split point (start of second node).
    # First node starts at 0; second node starts at the index of the
    # second letter A-K.
    second_letter_idx = None
    for i in range(1, len(edge_id)):
        c = edge_id[i].upper()
        if "A" <= c <= "K":
            second_letter_idx = i
            break

    if second_letter_idx is None:
        raise ValueError(f"Cannot parse edge_id '{edge_id}' into two nodes")

    node1 = edge_id[:second_letter_idx]
    node2 = edge_id[second_letter_idx:]
    x1, y1 = _node_to_xy(node1)
    x2, y2 = _node_to_xy(node2)
    return EdgeGeom(edge_id=edge_id, x1=x1, y1=y1, x2=x2, y2=y2)


def edge_distance(e1: EdgeGeom, e2: EdgeGeom) -> float:
    """Manhattan distance between midpoints of two edges."""
    mx1, my1 = e1.midpoint
    mx2, my2 = e2.midpoint
    return abs(mx1 - mx2) + abs(my1 - my2)


def edge_to_label(edge_id: str) -> str:
    """
    Map an edge ID to the label space used by Q6.

    - If the edge is vertical -> return the column letter (A-K)
    - If the edge is horizontal -> return the row index as string ("0"-"10")
    """
    geom = parse_edge_geom(edge_id)
    if geom.is_vertical:
        # Column is determined by x
        return chr(ord("A") + geom.x1)
    elif geom.is_horizontal:
        # Row is determined by y
        return str(geom.y1)
    else:
        # Diagonal or something unexpected; fall back to column of first node
        return chr(ord("A") + geom.x1)


# ============================================================
# Data loading (shared with run_experiment.py)
# ============================================================

def load_test_edges() -> List[str]:
    """Load test edges from the latest `test_*.json` file."""
    test_files = list(DATA_DIR.glob("test_*.json"))
    if not test_files:
        raise FileNotFoundError(f"No test_*.json found in {DATA_DIR}")

    test_file = sorted(test_files)[-1]

    with open(test_file, "r") as f:
        data = json.load(f)

    edges: List[str] = []
    for sim in data["simulations"]:
        edge_id = sim["simulation"]["edge_info"]["edge_id"]
        edges.append(edge_id)
    return edges


def load_ground_truth() -> Dict[str, str]:
    """Load ground-truth answers for the test set."""
    gt_file = DATA_DIR / "ground_truth_test_44.csv"
    if not gt_file.exists():
        raise FileNotFoundError(gt_file)

    gt: Dict[str, str] = {}
    with open(gt_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            edge = row["edge"].replace(" edge removed", "")
            gt[edge] = row["Q6_max_density_road"]
    return gt


# ============================================================
# Training data extraction
# ============================================================

@dataclass
class TrainingSample:
    """One training example: (removed edge -> label)."""

    source_edge: str
    source_geom: EdgeGeom
    label: str  # column letter (A-K) OR row index ("0"-"10")


def load_training_samples() -> List[TrainingSample]:
    """
    Build training samples from the prepared ground-truth CSV
    `ground_truth_train_176.csv` in `experiment_setup/results/`.

    Each row has:
        edge  -> "<EDGE_ID> edge removed"
        Q6_max_density_road -> label (A-K or 0-10)
    """
    train_file = DATA_DIR / "ground_truth_train_176.csv"
    if not train_file.exists():
        raise FileNotFoundError(train_file)

    samples: List[TrainingSample] = []
    with open(train_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_edge = row["edge"].replace(" edge removed", "").strip()
            label = row["Q6_max_density_road"].strip()
            if not raw_edge or not label:
                continue
            try:
                source_geom = parse_edge_geom(raw_edge)
            except Exception:
                # Skip malformed edge IDs
                continue
            samples.append(
                TrainingSample(
                    source_edge=raw_edge,
                    source_geom=source_geom,
                    label=label,
                )
            )

    print(f"[TRAIN] Built {len(samples)} training samples from CSV")
    return samples


# ============================================================
# Distance‑weighted heuristic prediction
# ============================================================

def _label_to_index(label: str) -> int:
    """
    Map label (A-K or '0'-'10') to an integer index.
    This is mainly to provide a stable ordering if needed.
    """
    label = label.strip().upper()
    if len(label) == 1 and "A" <= label <= "K":
        return ord(label) - ord("A")
    # Row index
    try:
        val = int(label)
        if 0 <= val <= 10:
            return 11 + val
    except ValueError:
        pass
    # Fallback bucket
    return 999


def predict_label_for_edge(
    target_edge: str,
    training_samples: List[TrainingSample],
    k: int = 20,
    distance_eps: float = 1e-3,
    distance_power: float = 2.0,
    mode: str = "max",  # "max" or "proportional"
) -> str:
    """
    Predict label for a target edge using distance‑weighted k‑NN style
    regression/classification.

    - Compute geometric distance between target edge and each training
      source edge
    - Take the k nearest neighbors
    - For each neighbor i with label L_i and distance d_i, assign weight:
          w_i = 1 / (d_i + eps)^p
    - Sum weights per label and pick label with the highest weight or probability.
    """
    if not training_samples:
        raise ValueError("No training samples available for heuristic.")

    target_geom = parse_edge_geom(target_edge)

    # Compute distances to all training samples
    scored: List[Tuple[float, TrainingSample]] = []
    for s in training_samples:
        d = edge_distance(target_geom, s.source_geom)
        scored.append((d, s))

    scored.sort(key=lambda x: x[0])
    neighbors = scored[: max(1, min(k, len(scored)))]

    label_weights: Dict[str, float] = defaultdict(float)
    for d, s in neighbors:
        w = 1.0 / ((d + distance_eps) ** distance_power)
        label_weights[s.label] += w

    if mode == "max":
        # Deterministic: choose label with maximum total weight
        best_label = None
        best_weight = -1.0
        for label, w in label_weights.items():
            if w > best_weight:
                best_weight = w
                best_label = label
            elif abs(w - best_weight) < 1e-9:
                # Tie-breaker: smaller index wins
                if _label_to_index(label) < _label_to_index(best_label):  # type: ignore[arg-type]
                    best_label = label

        if best_label is None:
            # Fallback: nearest neighbor label
            best_label = neighbors[0][1].label
        return best_label

    elif mode == "proportional":
        # Stochastic: sample label in proportion to its weight
        total_w = sum(max(w, 0.0) for w in label_weights.values())
        if total_w <= 0.0:
            # Degenerate case: fall back to max rule
            return predict_label_for_edge(
                target_edge,
                training_samples,
                k=k,
                distance_eps=distance_eps,
                distance_power=distance_power,
                mode="max",
            )

        # Build CDF
        r = random.random() * total_w
        cumulative = 0.0
        # Iteration order is arbitrary; for reproducibility you can sort by label
        for label, w in sorted(label_weights.items(), key=lambda x: _label_to_index(x[0])):
            cumulative += max(w, 0.0)
            if r <= cumulative:
                return label

        # Numerical safety fallback
        return max(label_weights.items(), key=lambda x: x[1])[0]

    else:
        raise ValueError(f"Unknown mode '{mode}', expected 'max' or 'proportional'.")


# ============================================================
# Main experiment logic (mirrors run_experiment.py structure)
# ============================================================

def run_heuristic(mode: str = "max") -> None:
    """Run the heuristic baseline on the test set."""
    RESULTS_DIR.mkdir(exist_ok=True)

    test_edges = load_test_edges()
    ground_truth = load_ground_truth()

    print(f"테스트 엣지: {len(test_edges)}개")
    print(f"Heuristic mode: {mode}")

    # Build training samples from precomputed training ground-truth CSV
    training_samples = load_training_samples()

    if not training_samples:
        raise RuntimeError("No training samples could be extracted from the DB.")

    results = []
    for i, edge_id in enumerate(test_edges, start=1):
        print(f"[{i}/{len(test_edges)}] {edge_id}")
        try:
            pred = predict_label_for_edge(edge_id, training_samples, mode=mode)
        except Exception as e:
            print(f"   ERROR during prediction: {e}")
            pred = ""

        gt_answer = ground_truth.get(edge_id, "")
        print(f"   예측: {pred}, 정답: {gt_answer}")

        results.append(
            {
                "edge_id": edge_id,
                "answer": pred,
                "gt_answer": gt_answer,
            }
        )

    # Save results (mode-specific filename)
    suffix = mode.lower()
    if suffix not in {"max", "proportional"}:
        suffix = "custom"
    csv_file = RESULTS_DIR / f"heuristic_{suffix}_answers.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["edge_id", "answer", "gt_answer"])
        writer.writeheader()
        writer.writerows(results)

    # Summary
    print("\n" + "=" * 60)
    print("Heuristic 실험 완료 요약")
    print("=" * 60)
    correct = sum(1 for r in results if r["answer"] == r["gt_answer"])
    total = len(results)
    acc = (correct / total * 100.0) if total > 0 else 0.0
    print(f"정확도: {correct}/{total} ({acc:.1f}%)")
    print(f"결과 저장: {csv_file}")


if __name__ == "__main__":
    # Optional CLI arg: heuristic mode ("max" or "proportional")
    import sys

    cli_mode = "max"
    if len(sys.argv) >= 2:
        cli_mode = sys.argv[1].lower()
    run_heuristic(mode=cli_mode)

