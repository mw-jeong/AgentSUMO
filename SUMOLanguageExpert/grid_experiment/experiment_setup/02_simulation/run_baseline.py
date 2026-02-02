#!/usr/bin/env python3
"""
Step 2: Baseline Simulation

베이스라인 시뮬레이션 실행 및 DB/JSON 저장.
- DB: simulations.db (새로 생성)
- JSON: baseline.json
"""

import os
import sys
import json
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


def get_trips_from_db(db_file, simulation_id):
    """Read trips from DB for JSON export."""
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
    """Read edge_metrics from DB for JSON export."""
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

# Paths relative to this script
BASE_DIR = Path(__file__).parent.parent
NETWORK_DIR = BASE_DIR / "data" / "network"
TRIPS_DIR = BASE_DIR / "data" / "trips"
SIM_DIR = BASE_DIR / "data" / "simulations"
RESULTS_DIR = BASE_DIR / "results"


def main():
    print("=" * 60)
    print("Step 2: Baseline Simulation")
    print("=" * 60)

    net_file = NETWORK_DIR / f"grid_{GRID_SIZE}x{GRID_SIZE}.net.xml"
    trip_file = TRIPS_DIR / f"grid_{GRID_SIZE}x{GRID_SIZE}.net.trips.xml"
    db_file = RESULTS_DIR / "simulations.db"
    baseline_dir = SIM_DIR / "baseline"

    # Validate input files
    if not net_file.exists():
        print(f"ERROR: Network file not found: {net_file}")
        return 1
    if not trip_file.exists():
        print(f"ERROR: Trip file not found: {trip_file}")
        return 1

    print(f"Network: {net_file}")
    print(f"Trips: {trip_file}")

    # Create output directories
    baseline_dir.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Copy vehicle_types.add.xml (required by SimulationRunner)
    vehicle_types_src = sumo_environment.DEFAULT_OUTPUT_DIR / "simulations" / "vehicle_types.add.xml"
    if vehicle_types_src.exists():
        shutil.copy2(vehicle_types_src, baseline_dir / "vehicle_types.add.xml")
    else:
        # Create a basic vehicle_types.add.xml if it doesn't exist
        with open(baseline_dir / "vehicle_types.add.xml", "w") as f:
            f.write('''<?xml version="1.0" encoding="UTF-8"?>
<additional xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/additional_file.xsd">
    <vType id="passenger" vClass="passenger" color="yellow"/>
</additional>
''')

    # 1. Generate routes using TripGenerator
    print("\n1. Generating routes...")
    route_file = baseline_dir / "baseline.rou.xml"
    trip_generator = TripGenerator()
    trip_generator._generate_routes(str(net_file), str(trip_file), str(route_file))

    if not route_file.exists():
        print("ERROR: Route generation failed")
        return 1
    print(f"   Route file: {route_file}")

    # 2. Run simulation
    print("\n2. Running simulation...")
    runner = SimulationRunner()
    result = runner.run(
        net_file=str(net_file),
        route_file=str(route_file),
        duration=SIMULATION_TIME,
        output_dir=str(baseline_dir),
        policy_type="baseline"
    )

    if result['status'] == 'error':
        print(f"ERROR: Simulation failed: {result['message']}")
        return 1

    print(f"   Simulation time: {result['simulation_time']:.2f}s")

    tripinfo_file = result['metadata']['absolute_tripinfo']
    edgedata_file = result['metadata']['absolute_edgedata']
    emission_file = result['metadata']['absolute_edgedata_emission']

    # 3. Delete old DB if exists and convert to SQLite
    print("\n3. Converting to SQLite...")
    if db_file.exists():
        db_file.unlink()
        print(f"   Deleted old DB: {db_file}")

    converter = XMLToSQLiteConverter()
    db_result = converter.convert_simulation_results(
        tripinfo_xml=tripinfo_file,
        edgedata_xml=edgedata_file,
        edgedata_emission_xml=emission_file,
        output_db=str(db_file),
        simulation_id="baseline",
        net_file=str(net_file),
        route_file=str(route_file),
        description="Baseline simulation"
    )

    if db_result.get('status') != 'success':
        print(f"ERROR: DB conversion failed: {db_result.get('message')}")
        return 1

    trip_count = db_result['metadata']['trip_count']
    print(f"   DB: {db_file}")
    print(f"   Trips: {trip_count}")

    # 4. Export to JSON
    print("\n4. Exporting to JSON...")
    trips = get_trips_from_db(str(db_file), "baseline")
    edge_metrics = get_edge_metrics_from_db(str(db_file), "baseline")

    baseline_json = {
        "simulation": {
            "simulation_id": "baseline",
            "policy_type": "baseline",
            "created_at": datetime.datetime.now().isoformat(),
            "vehicle_count": trip_count,
            "description": "Baseline simulation (no edge removal)"
        },
        "trips": trips,
        "edge_metrics": edge_metrics
    }

    json_file = RESULTS_DIR / "baseline.json"
    with open(json_file, 'w') as f:
        json.dump(baseline_json, f, indent=2)
    print(f"   JSON: {json_file}")

    print("\n" + "=" * 60)
    print("SUCCESS")
    print("=" * 60)
    print(f"Baseline simulation completed: {trip_count} trips")
    print(f"DB: {db_file}")
    print(f"JSON: {json_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
