#!/usr/bin/env python3
"""
Step 1a: Generate Grid Network

SUMO netgenerate를 사용하여 추상적인 그리드 네트워크 생성.
- 11x11 그리드, 블록 길이 200m (220 엣지 쌍)
- 노드: A0, A1, ..., K10 형식
- 엣지: A0A1, A0B0 형식 (출발노드 + 도착노드)
"""

import json
import subprocess
import sys
from pathlib import Path

# AgentSUMO import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from agentsumo.server.settings.settings import sumo_environment

import sumolib

# Parameters
GRID_SIZE = 11  # 11x11 grid = 440 edges (220 unique pairs)
BLOCK_LENGTH = 200

# Paths relative to this script
BASE_DIR = Path(__file__).parent.parent
NETWORK_DIR = BASE_DIR / "data" / "network"
EDGES_DIR = BASE_DIR / "data" / "edges"


def get_removable_edges(net):
    """Get all edges that can be removed (non-internal edges)."""
    edges = []
    for edge in net.getEdges():
        edge_id = edge.getID()
        if edge_id.startswith(":"):
            continue
        edges.append(edge)
    return edges


def main():
    print("=" * 60)
    print("Step 1a: Generate Grid Network")
    print("=" * 60)

    NETWORK_DIR.mkdir(parents=True, exist_ok=True)
    EDGES_DIR.mkdir(parents=True, exist_ok=True)

    output_file = NETWORK_DIR / f"grid_{GRID_SIZE}x{GRID_SIZE}.net.xml"

    cmd = [
        sumo_environment.get_binary_path("netgenerate"),
        "--grid",
        f"--grid.x-number={GRID_SIZE}",
        f"--grid.y-number={GRID_SIZE}",
        f"--grid.x-length={BLOCK_LENGTH}",
        f"--grid.y-length={BLOCK_LENGTH}",
        "--default.lanenumber=2",
        "--default-junction-type=traffic_light",
        "-o", str(output_file)
    ]

    print(f"Grid size: {GRID_SIZE}x{GRID_SIZE}")
    print(f"Block length: {BLOCK_LENGTH}m")
    print(f"Output: {output_file}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: netgenerate failed")
        print(result.stderr)
        return 1

    print(f"\nGenerated: {output_file}")

    # Load network and get edges
    net = sumolib.net.readNet(str(output_file))
    edges = get_removable_edges(net)
    print(f"Total edges: {len(edges)}")
    print(f"Sample edge IDs: {[e.getID() for e in edges[:5]]}")

    # Save edges data to JSON
    edges_data = []
    for edge in edges:
        edges_data.append({
            "edge_id": edge.getID(),
            "from_node": edge.getFromNode().getID(),
            "to_node": edge.getToNode().getID(),
            "length": edge.getLength()
        })

    edges_json = EDGES_DIR / "edges.json"
    with open(edges_json, 'w', encoding='utf-8') as f:
        json.dump(edges_data, f, indent=2, ensure_ascii=False)
    print(f"Saved edges data to {edges_json}")

    # Print edge summary
    print("\n" + "=" * 80)
    print("EDGE SUMMARY")
    print("=" * 80)
    for i, edge in enumerate(edges):
        print(f"Edge {i:2d}: {edge.getID()} ({edge.getFromNode().getID()} -> {edge.getToNode().getID()}), {edge.getLength():.1f}m")

    print("\n" + "=" * 60)
    print("SUCCESS")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
