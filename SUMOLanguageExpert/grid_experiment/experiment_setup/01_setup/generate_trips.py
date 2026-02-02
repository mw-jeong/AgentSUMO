#!/usr/bin/env python3
"""
Step 1b: Generate Random Trips

그리드 네트워크용 랜덤 트립 생성.
AgentSUMO의 TripGenerator 사용.
"""

import sys
import json
from pathlib import Path

# AgentSUMO import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from agentsumo.server.baseline.trip_generator import TripGenerator

# Parameters
GRID_SIZE = 11  # 11x11 grid = 440 edges (220 unique pairs)

# Paths relative to this script
BASE_DIR = Path(__file__).parent.parent
NETWORK_DIR = BASE_DIR / "data" / "network"
TRIPS_DIR = BASE_DIR / "data" / "trips"


def main():
    print("=" * 60)
    print("Step 1b: Generate Random Trips")
    print("=" * 60)

    net_file = str(NETWORK_DIR / f"grid_{GRID_SIZE}x{GRID_SIZE}.net.xml")
    output_dir = str(TRIPS_DIR)

    # Validate network file
    if not Path(net_file).exists():
        print(f"ERROR: Network file not found: {net_file}")
        print("Run generate_network.py first")
        return 1

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Initialize trip generator
    trip_generator = TripGenerator()

    # Generate random trips with medium traffic
    print(f"Network: {net_file}")
    print("Generating random trips...")

    result = trip_generator.generate(
        trip_type="RandomOD",
        net_file=net_file,
        traffic_condition="medium",  # light, medium, heavy
        output_dir=output_dir
    )

    print("=" * 60)
    print("Trip Generation Result:")
    print(json.dumps(result, indent=2))
    print("=" * 60)

    if result["status"] == "success":
        print(f"\nTrip file: {result['trip_file']}")
        print(f"Route file: {result['route_file']}")
        print(f"Trip count: {result['trip_count']}")
        return 0
    else:
        print(f"\nError: {result['message']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
