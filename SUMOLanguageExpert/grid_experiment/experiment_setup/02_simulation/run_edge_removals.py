#!/usr/bin/env python3
"""
Step 3: Edge Removal Simulations

엣지 각각을 제거하며 시뮬레이션 실행.
- 80%: DB + JSON에 저장 (Training)
- 20%: JSON에만 저장 (Testing - Ground Truth)

Grid 네트워크에서는 1 엣지 = 1 블록이므로 블록 단위가 아닌 엣지 단위로 제거.
"""

import os
import sys
import subprocess
import json
import time
import random
import shutil
import datetime
import sqlite3
from pathlib import Path

# AgentSUMO import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from agentsumo.server.settings.settings import sumo_environment
from agentsumo.server.baseline.simulation_runner import SimulationRunner
from agentsumo.server.baseline.trip_generator import TripGenerator
from agentsumo.server.analysis.xml_to_sqlite import XMLToSQLiteConverter

import sumolib


def get_trips_from_db(db_file, simulation_id):
    """Read trips from DB for JSON export (same data as DB)."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM trips WHERE simulation_id = ?",
        (simulation_id,)
    )
    trips = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return trips


def get_edge_metrics_from_db(db_file, simulation_id):
    """Read edge_metrics from DB for JSON export (same data as DB)."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM edge_metrics WHERE simulation_id = ?",
        (simulation_id,)
    )
    edge_metrics = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return edge_metrics


# Parameters
GRID_SIZE = 11  # 11x11 grid = 440 edges (220 unique pairs)
SIMULATION_TIME = 3600
RANDOM_SEED = 424242
TRAIN_RATIO = 0.8

# Paths relative to this script
BASE_DIR = Path(__file__).parent.parent
NETWORK_DIR = BASE_DIR / "data" / "network"
TRIPS_DIR = BASE_DIR / "data" / "trips"
SIM_DIR = BASE_DIR / "data" / "simulations"
RESULTS_DIR = BASE_DIR / "results"


def get_removable_edges(net):
    """Get all edges that can be removed (non-internal, one direction only).

    For bidirectional edges (A0A1 and A1A0), only keep one direction
    by selecting the edge where from_node < to_node lexicographically.
    This reduces 224 edges to 112 unique undirected edges.
    """
    edges = []
    seen_pairs = set()

    for edge in net.getEdges():
        edge_id = edge.getID()
        # Skip internal edges (junction connectors)
        if edge_id.startswith(":"):
            continue

        from_node = edge.getFromNode().getID()
        to_node = edge.getToNode().getID()

        # Create canonical key (sorted pair)
        pair_key = tuple(sorted([from_node, to_node]))

        if pair_key in seen_pairs:
            continue  # Skip reverse direction

        seen_pairs.add(pair_key)
        edges.append(edge)

    return edges


def split_train_test(edges):
    """Split edges into training (80%) and testing (20%) sets."""
    random.seed(RANDOM_SEED)
    indices = list(range(len(edges)))
    random.shuffle(indices)
    split_idx = int(len(indices) * TRAIN_RATIO)
    train_indices = set(indices[:split_idx])
    test_indices = set(indices[split_idx:])
    return train_indices, test_indices


def create_disrupted_network(net_file, edge_id, output_file):
    """Remove edge and its reverse direction using netconvert.

    For edge A0A1, also removes A1A0 (if exists) to simulate
    bidirectional road closure.
    """
    # Get reverse edge ID (e.g., A0A1 -> A1A0)
    from_node = edge_id[:2]
    to_node = edge_id[2:]
    reverse_edge_id = to_node + from_node

    # Remove both directions
    edges_to_remove = f"{edge_id},{reverse_edge_id}"

    cmd = [
        sumo_environment.get_binary_path("netconvert"),
        "-s", str(net_file),
        "--remove-edges.explicit", edges_to_remove,
        "-o", str(output_file),
        "--no-warnings"
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=60)
    return result.returncode == 0


def run_simulation(edge, net_file, trip_file, output_dir, runner, trip_generator):
    """Run simulation with a single edge removed."""
    edge_id = edge.getID()
    work_dir = output_dir / f"edge_{edge_id.replace('/', '_')}"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Copy vehicle_types.add.xml (required by SimulationRunner)
    vehicle_types_src = sumo_environment.DEFAULT_OUTPUT_DIR / "simulations" / "vehicle_types.add.xml"
    if vehicle_types_src.exists():
        shutil.copy2(vehicle_types_src, work_dir / "vehicle_types.add.xml")
    else:
        # Create a basic vehicle_types.add.xml if it doesn't exist
        with open(work_dir / "vehicle_types.add.xml", "w") as f:
            f.write('''<?xml version="1.0" encoding="UTF-8"?>
<additional xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/additional_file.xsd">
    <vType id="passenger" vClass="passenger" color="yellow"/>
</additional>
''')

    # 1. Create disrupted network (remove edge)
    disrupted_net = work_dir / "disrupted.net.xml"
    if not create_disrupted_network(net_file, edge_id, disrupted_net):
        return None

    # 2. Generate routes using TripGenerator
    disrupted_route = work_dir / "disrupted.rou.xml"
    try:
        trip_generator._generate_routes(str(disrupted_net), str(trip_file), str(disrupted_route))
    except Exception as e:
        print(f"  Route generation failed: {e}")
        return None

    if not disrupted_route.exists():
        return None

    # 3. Run simulation using SimulationRunner
    result = runner.run(
        net_file=str(disrupted_net),
        route_file=str(disrupted_route),
        duration=SIMULATION_TIME,
        output_dir=str(work_dir),
        policy_type="edge_removal"
    )

    if result['status'] == 'error':
        return None

    tripinfo_file = result['metadata']['absolute_tripinfo']
    edgedata_file = result['metadata']['absolute_edgedata']
    emission_file = result['metadata']['absolute_edgedata_emission']

    # Verify output files exist
    if not Path(tripinfo_file).exists():
        return None

    return {
        "edge_id": edge_id,
        "simulation_time": result['simulation_time'],
        "tripinfo_file": tripinfo_file,
        "edgedata_file": edgedata_file,
        "emission_file": emission_file,
        "net_file": str(disrupted_net),
        "route_file": str(disrupted_route),
    }


def main():
    print("=" * 60)
    print("Step 3: Edge Removal Simulations")
    print("=" * 60)

    net_file = NETWORK_DIR / f"grid_{GRID_SIZE}x{GRID_SIZE}.net.xml"
    trip_file = TRIPS_DIR / f"grid_{GRID_SIZE}x{GRID_SIZE}.net.trips.xml"
    db_file = RESULTS_DIR / "simulations.db"

    if not net_file.exists() or not trip_file.exists():
        print("ERROR: Run step 01 first (generate_network.py and generate_trips.py)")
        return 1

    if not db_file.exists():
        print("ERROR: Run run_baseline.py first to create DB")
        return 1

    # Load network and get edges
    net = sumolib.net.readNet(str(net_file))
    edges = get_removable_edges(net)
    train_indices, test_indices = split_train_test(edges)

    print(f"Total edges: {len(edges)}")
    print(f"Training: {len(train_indices)} edges (DB + JSON)")
    print(f"Testing: {len(test_indices)} edges (JSON only)")

    output_dir = SIM_DIR / "disruptions"
    output_dir.mkdir(parents=True, exist_ok=True)

    runner = SimulationRunner()
    trip_generator = TripGenerator()
    converter = XMLToSQLiteConverter()

    training_results = []
    testing_results = []

    start_time = time.time()

    for idx, edge in enumerate(edges):
        is_training = idx in train_indices
        edge_id = edge.getID()

        elapsed = time.time() - start_time
        if idx > 0:
            remaining = (elapsed / idx) * (len(edges) - idx)
            print(f"[{idx+1}/{len(edges)}] {edge_id} ({'train' if is_training else 'test'}) - ~{remaining:.0f}s remaining")
        else:
            print(f"[{idx+1}/{len(edges)}] {edge_id} ({'train' if is_training else 'test'})")

        result = run_simulation(edge, net_file, trip_file, output_dir, runner, trip_generator)

        if result is None:
            print(f"  FAILED")
            continue

        # Generate description
        description = f"{edge_id} edge removed"

        # simulation_id=None -> auto-generated as sim_{timestamp}_{ms}
        db_result = converter.convert_simulation_results(
            tripinfo_xml=result["tripinfo_file"],
            edgedata_xml=result["edgedata_file"],
            edgedata_emission_xml=result["emission_file"],
            output_db=str(db_file),
            simulation_id=None,
            net_file=result["net_file"],
            route_file=result["route_file"],
            description=description
        )

        if db_result.get('status') != 'success':
            print(f"  FAILED: {db_result.get('message', 'Unknown error')}")
            continue

        sim_id = db_result['simulation_id']
        trip_count = db_result['metadata']['trip_count']

        # Read trips and edge_metrics from DB for JSON (same data as DB)
        trips = get_trips_from_db(str(db_file), sim_id)
        edge_metrics = get_edge_metrics_from_db(str(db_file), sim_id)

        # Build JSON data matching DB structure exactly
        sim_data = {
            "simulation": {
                "simulation_id": sim_id,
                "policy_type": "edge_removal",
                "created_at": datetime.datetime.now().isoformat(),
                "vehicle_count": trip_count,
                "description": description,
                "edge_info": {
                    "edge_id": edge_id
                }
            },
            "trips": trips,
            "edge_metrics": edge_metrics
        }

        if is_training:
            training_results.append(sim_data)
            print(f"  OK -> DB + JSON ({trip_count} trips)")
        else:
            # For testing set, remove from DB (keep only in JSON)
            conn = sqlite3.connect(str(db_file))
            conn.execute("DELETE FROM trips WHERE simulation_id = ?", (sim_id,))
            conn.execute("DELETE FROM edge_metrics WHERE simulation_id = ?", (sim_id,))
            conn.execute("DELETE FROM simulations WHERE simulation_id = ?", (sim_id,))
            conn.commit()
            conn.close()

            testing_results.append(sim_data)
            print(f"  OK -> JSON only ({trip_count} trips)")

    total_time = time.time() - start_time

    # Load baseline and merge with training results
    baseline_json = RESULTS_DIR / "baseline.json"
    if baseline_json.exists():
        with open(baseline_json, 'r') as f:
            baseline_data = json.load(f)
        training_results.insert(0, baseline_data)
        baseline_json.unlink()  # Remove separate baseline.json

    # Save JSON files
    train_count = len(training_results)  # Now includes baseline
    test_count = len(test_indices)

    with open(RESULTS_DIR / f"train_{train_count}.json", 'w') as f:
        json.dump({"simulations": training_results}, f, indent=2)

    with open(RESULTS_DIR / f"test_{test_count}.json", 'w') as f:
        json.dump({"simulations": testing_results}, f, indent=2)

    print("\n" + "=" * 60)
    print("SUCCESS")
    print("=" * 60)
    print(f"Total time: {total_time:.1f}s")
    print(f"Training: {len(training_results)} simulations (1 baseline + {len(training_results)-1} edge removals)")
    print(f"Testing: {len(testing_results)} simulations (JSON only)")
    print(f"\nFiles:")
    print(f"  DB: {db_file}")
    print(f"  Training JSON: {RESULTS_DIR / f'train_{train_count}.json'}")
    print(f"  Testing JSON: {RESULTS_DIR / f'test_{test_count}.json'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
