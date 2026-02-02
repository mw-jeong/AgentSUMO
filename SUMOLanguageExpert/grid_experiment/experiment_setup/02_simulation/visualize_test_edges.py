#!/usr/bin/env python3
"""
테스트 엣지(44개)만 색칠한 시각화 생성
"""

import matplotlib
matplotlib.use('Agg')

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from agentsumo.server.visualization.edge_plotter import EdgePlotter

BASE_DIR = Path(__file__).parent.parent
NETWORK_DIR = BASE_DIR / "data" / "network"
EDGES_DIR = BASE_DIR / "data" / "edges"
RESULTS_DIR = BASE_DIR / "results"


def main():
    print("=" * 60)
    print("Test Edges Visualization")
    print("=" * 60)

    # Load test edges from test_44.json
    test_file = RESULTS_DIR / "test_44.json"
    with open(test_file, 'r') as f:
        data = json.load(f)

    test_edges = [sim['simulation']['edge_info']['edge_id'] for sim in data['simulations']]
    print(f"Test edges: {len(test_edges)}개")

    # Network file
    net_file = NETWORK_DIR / "grid_11x11.net.xml"

    # Generate visualization
    edge_plotter = EdgePlotter()

    result = edge_plotter.visualize_edges_by_ids(
        net_file=str(net_file),
        edge_ids=test_edges,
        output_file="test_edges_44.png",
        output_dir=str(EDGES_DIR)
    )

    print(f"Generated: {result['output_file']}")
    print(f"Edges: {len(test_edges)}개")

    return 0


if __name__ == "__main__":
    sys.exit(main())
