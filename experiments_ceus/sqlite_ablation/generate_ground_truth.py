#!/usr/bin/env python3
"""
Generate Ground Truth for SQLite Ablation Benchmark

Usage:
    python -m experiments_ceus.sqlite_ablation.generate_ground_truth \
        --db-path experiments_ceus/gangnam/analysis/hour_00_analysis.db \
        --city gangnam
"""

import argparse
import json
import sqlite3
from pathlib import Path


def detect_simulation_ids(conn):
    cursor = conn.execute("SELECT simulation_id, description FROM simulations")
    rows = cursor.fetchall()
    mapping = {"baseline": None, "adaptation": None, "greenwave": None}
    for sim_id, desc in rows:
        s, d = sim_id.lower(), (desc or "").lower()
        if "baseline" in s or "baseline" in d:
            mapping["baseline"] = sim_id
        elif "offset" in s or "green" in d or "offset" in d:
            mapping["greenwave"] = sim_id
        elif "adapt" in s or "webster" in d or "adapt" in d:
            mapping["adaptation"] = sim_id
    unmapped = [r[0] for r in rows if r[0] not in mapping.values()]
    for key in mapping:
        if mapping[key] is None and unmapped:
            mapping[key] = unmapped.pop(0)
    return mapping


def generate_gt(db_path: str, city: str):
    conn = sqlite3.connect(db_path)
    sim = detect_simulation_ids(conn)

    print(f"Simulation ID mapping:")
    for role, sid in sim.items():
        print(f"  {role}: {sid}")
    print()

    b = sim["baseline"]
    g = sim["greenwave"]
    a = sim["adaptation"]

    gt = {}

    # ── L1 ────────────────────────────────────────────────────────────────

    # L1_01: avg trip duration in baseline
    r = conn.execute("SELECT AVG(duration) FROM trips WHERE simulation_id=?", (b,)).fetchone()
    gt["L1_01"] = {"answer": round(r[0], 2), "unit": "seconds", "eval": "numeric"}

    # L1_02: total waiting time in baseline
    r = conn.execute("SELECT SUM(waitingTime) FROM trips WHERE simulation_id=?", (b,)).fetchone()
    gt["L1_02"] = {"answer": round(r[0], 2), "unit": "seconds", "eval": "numeric"}

    # L1_03: avg CO2 emission per vehicle in Webster
    r = conn.execute("SELECT AVG(CO2_abs) FROM trips WHERE simulation_id=?", (a,)).fetchone()
    gt["L1_03"] = {"answer": round(r[0], 2), "unit": "mg", "eval": "numeric"}

    # L1_04: max trip duration in Green Wave
    r = conn.execute("SELECT MAX(duration) FROM trips WHERE simulation_id=?", (g,)).fetchone()
    gt["L1_04"] = {"answer": round(r[0], 2), "unit": "seconds", "eval": "numeric"}

    # L1_05: % vehicles with waitingTime > 60s in baseline
    total = conn.execute("SELECT COUNT(*) FROM trips WHERE simulation_id=?", (b,)).fetchone()[0]
    over60 = conn.execute("SELECT COUNT(*) FROM trips WHERE simulation_id=? AND waitingTime > 60", (b,)).fetchone()[0]
    gt["L1_05"] = {"answer": round(over60 / total * 100, 2), "unit": "percent", "eval": "numeric"}

    # ── L2 ────────────────────────────────────────────────────────────────

    # L2_01: sum of density of top 5 densest edges in baseline
    r = conn.execute(
        "SELECT SUM(density) FROM (SELECT density FROM edge_metrics WHERE simulation_id=? ORDER BY density DESC LIMIT 5)", (b,)
    ).fetchone()
    gt["L2_01"] = {"answer": round(r[0], 2), "unit": "veh/km", "eval": "numeric"}

    # L2_02: min speed among top 5 fastest edges in Webster
    r = conn.execute(
        "SELECT MIN(speed) FROM (SELECT speed FROM edge_metrics WHERE simulation_id=? ORDER BY speed DESC LIMIT 5)", (a,)
    ).fetchone()
    gt["L2_02"] = {"answer": round(r[0], 2), "unit": "m/s", "eval": "numeric"}

    # L2_03: total trip duration of top 5 longest-duration vehicles in baseline
    r = conn.execute(
        "SELECT SUM(duration) FROM (SELECT duration FROM trips WHERE simulation_id=? ORDER BY duration DESC LIMIT 5)", (b,)
    ).fetchone()
    gt["L2_03"] = {"answer": round(r[0], 2), "unit": "seconds", "eval": "numeric"}

    # L2_04: avg CO2 emission of top 5 highest-emission edges in Green Wave
    r = conn.execute(
        "SELECT AVG(CO2_abs) FROM (SELECT CO2_abs FROM edge_metrics WHERE simulation_id=? ORDER BY CO2_abs DESC LIMIT 5)", (g,)
    ).fetchone()
    gt["L2_04"] = {"answer": round(r[0], 2), "unit": "mg", "eval": "numeric"}

    # L2_05: % vehicles with zero waiting time in Green Wave
    total_g = conn.execute("SELECT COUNT(*) FROM trips WHERE simulation_id=?", (g,)).fetchone()[0]
    zero_g = conn.execute("SELECT COUNT(*) FROM trips WHERE simulation_id=? AND waitingTime=0", (g,)).fetchone()[0]
    gt["L2_05"] = {"answer": round(zero_g / total_g * 100, 2), "unit": "percent", "eval": "numeric"}

    # ── L3 ────────────────────────────────────────────────────────────────

    # L3_01: % reduction in avg duration baseline → Webster
    avg_dur_b = conn.execute("SELECT AVG(duration) FROM trips WHERE simulation_id=?", (b,)).fetchone()[0]
    avg_dur_a = conn.execute("SELECT AVG(duration) FROM trips WHERE simulation_id=?", (a,)).fetchone()[0]
    gt["L3_01"] = {"answer": round((avg_dur_b - avg_dur_a) / avg_dur_b * 100, 2), "unit": "percent", "eval": "numeric"}

    # L3_02: % reduction in avg waiting time baseline → Green Wave
    avg_wait_b = conn.execute("SELECT AVG(waitingTime) FROM trips WHERE simulation_id=?", (b,)).fetchone()[0]
    avg_wait_g = conn.execute("SELECT AVG(waitingTime) FROM trips WHERE simulation_id=?", (g,)).fetchone()[0]
    gt["L3_02"] = {"answer": round((avg_wait_b - avg_wait_g) / avg_wait_b * 100, 2), "unit": "percent", "eval": "numeric"}

    # L3_03: difference in avg fuel consumption per vehicle Webster vs Green Wave
    avg_fuel_a = conn.execute("SELECT AVG(fuel_abs) FROM trips WHERE simulation_id=?", (a,)).fetchone()[0]
    avg_fuel_g = conn.execute("SELECT AVG(fuel_abs) FROM trips WHERE simulation_id=?", (g,)).fetchone()[0]
    gt["L3_03"] = {"answer": round(avg_fuel_a - avg_fuel_g, 2), "unit": "ml", "eval": "numeric",
                   "note": "negative means Green Wave has higher fuel consumption"}

    # L3_04: % reduction in max edge density from baseline to Webster
    max_density_b = conn.execute(
        "SELECT MAX(density) FROM edge_metrics WHERE simulation_id=?", (b,)
    ).fetchone()[0]
    max_density_a = conn.execute(
        "SELECT MAX(density) FROM edge_metrics WHERE simulation_id=?", (a,)
    ).fetchone()[0]
    gt["L3_04"] = {"answer": round((max_density_b - max_density_a) / max_density_b * 100, 2),
                   "unit": "percent", "eval": "numeric"}

    # L3_05: difference in avg time loss between baseline and Webster for top 10% longest-duration vehicles
    count_b = conn.execute("SELECT COUNT(*) FROM trips WHERE simulation_id=?", (b,)).fetchone()[0]
    top_n = max(1, count_b // 10)
    tl_b_top10 = conn.execute(
        "SELECT AVG(timeLoss) FROM (SELECT timeLoss FROM trips WHERE simulation_id=? ORDER BY duration DESC LIMIT ?)",
        (b, top_n)
    ).fetchone()[0]
    tl_a_top10 = conn.execute(
        "SELECT AVG(timeLoss) FROM (SELECT timeLoss FROM trips WHERE simulation_id=? ORDER BY duration DESC LIMIT ?)",
        (a, top_n)
    ).fetchone()[0]
    gt["L3_05"] = {"answer": round(tl_b_top10 - tl_a_top10, 2), "unit": "seconds", "eval": "numeric"}

    # ── L4 ────────────────────────────────────────────────────────────────

    # L4_01: which has higher % zero waiting time: Webster or Green Wave?
    total_a = conn.execute("SELECT COUNT(*) FROM trips WHERE simulation_id=?", (a,)).fetchone()[0]
    zero_a = conn.execute("SELECT COUNT(*) FROM trips WHERE simulation_id=? AND waitingTime=0", (a,)).fetchone()[0]
    pct_zero_a = zero_a / total_a * 100
    pct_zero_g = zero_g / total_g * 100
    gt["L4_01"] = {
        "answer": "Webster" if pct_zero_a > pct_zero_g else "Green Wave",
        "webster_pct": round(pct_zero_a, 2),
        "greenwave_pct": round(pct_zero_g, 2),
        "eval": "exact_match"
    }

    # L4_02: which policy achieves a lower average edge density?
    avg_density_a = conn.execute(
        "SELECT AVG(density) FROM edge_metrics WHERE simulation_id=?", (a,)
    ).fetchone()[0]
    avg_density_g = conn.execute(
        "SELECT AVG(density) FROM edge_metrics WHERE simulation_id=?", (g,)
    ).fetchone()[0]
    gt["L4_02"] = {
        "answer": "Webster" if avg_density_a < avg_density_g else "Green Wave",
        "webster_avg_density": round(avg_density_a, 4),
        "greenwave_avg_density": round(avg_density_g, 4),
        "eval": "exact_match"
    }

    # L4_03: which policy achieves lower avg CO2 on top 5 highest-emission edges in baseline?
    top5_co2_edges = conn.execute(
        "SELECT edge_id FROM edge_metrics WHERE simulation_id=? ORDER BY CO2_abs DESC LIMIT 5", (b,)
    ).fetchall()
    top5_co2_ids = [r[0] for r in top5_co2_edges]
    ph = ",".join("?" * len(top5_co2_ids))
    avg_co2_a_top5 = conn.execute(
        f"SELECT AVG(CO2_abs) FROM edge_metrics WHERE simulation_id=? AND edge_id IN ({ph})",
        [a] + top5_co2_ids
    ).fetchone()[0]
    avg_co2_g_top5 = conn.execute(
        f"SELECT AVG(CO2_abs) FROM edge_metrics WHERE simulation_id=? AND edge_id IN ({ph})",
        [g] + top5_co2_ids
    ).fetchone()[0]
    gt["L4_03"] = {
        "answer": "Webster" if avg_co2_a_top5 < avg_co2_g_top5 else "Green Wave",
        "webster_avg_co2": round(avg_co2_a_top5, 2),
        "greenwave_avg_co2": round(avg_co2_g_top5, 2),
        "top5_edges": top5_co2_ids,
        "eval": "exact_match"
    }

    # L4_04: considering both avg CO2 and fuel reduction, which is more environmentally effective?
    avg_co2_b = conn.execute("SELECT AVG(CO2_abs) FROM trips WHERE simulation_id=?", (b,)).fetchone()[0]
    avg_co2_a = conn.execute("SELECT AVG(CO2_abs) FROM trips WHERE simulation_id=?", (a,)).fetchone()[0]
    avg_co2_g = conn.execute("SELECT AVG(CO2_abs) FROM trips WHERE simulation_id=?", (g,)).fetchone()[0]
    avg_fuel_b = conn.execute("SELECT AVG(fuel_abs) FROM trips WHERE simulation_id=?", (b,)).fetchone()[0]
    co2_reduction_a = avg_co2_b - avg_co2_a
    co2_reduction_g = avg_co2_b - avg_co2_g
    fuel_reduction_a = avg_fuel_b - avg_fuel_a
    fuel_reduction_g = avg_fuel_b - avg_fuel_g
    # Combined score: sum of reductions (normalized by baseline)
    score_a = (co2_reduction_a / avg_co2_b) + (fuel_reduction_a / avg_fuel_b)
    score_g = (co2_reduction_g / avg_co2_b) + (fuel_reduction_g / avg_fuel_b)
    gt["L4_04"] = {
        "answer": "Webster" if score_a > score_g else "Green Wave",
        "webster_score": round(score_a, 4),
        "greenwave_score": round(score_g, 4),
        "eval": "exact_match"
    }

    # L4_05: top 10% vehicles by duration in baseline — which policy reduces avg duration more?
    avg_dur_b_top10 = conn.execute(
        "SELECT AVG(duration) FROM (SELECT duration FROM trips WHERE simulation_id=? ORDER BY duration DESC LIMIT ?)",
        (b, top_n)
    ).fetchone()[0]
    avg_dur_a_top10 = conn.execute(
        "SELECT AVG(duration) FROM (SELECT duration FROM trips WHERE simulation_id=? ORDER BY duration DESC LIMIT ?)",
        (a, top_n)
    ).fetchone()[0]
    avg_dur_g_top10 = conn.execute(
        "SELECT AVG(duration) FROM (SELECT duration FROM trips WHERE simulation_id=? ORDER BY duration DESC LIMIT ?)",
        (g, top_n)
    ).fetchone()[0]
    reduction_a = avg_dur_b_top10 - avg_dur_a_top10
    reduction_g = avg_dur_b_top10 - avg_dur_g_top10
    gt["L4_05"] = {
        "answer": "Webster" if reduction_a > reduction_g else "Green Wave",
        "webster_reduction": round(reduction_a, 2),
        "greenwave_reduction": round(reduction_g, 2),
        "eval": "exact_match"
    }

    conn.close()

    output_path = Path(__file__).parent / "ground_truth" / f"gt_{city}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=2)

    print(f"Ground truth saved: {output_path}")
    for qid, val in gt.items():
        print(f"  {qid}: {val['answer']} ({val['eval']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--city", required=True)
    args = parser.parse_args()
    generate_gt(args.db_path, args.city)
