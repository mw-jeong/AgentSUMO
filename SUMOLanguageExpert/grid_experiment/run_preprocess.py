#!/usr/bin/env python3
"""
Preprocess a SUMO net.xml file to extract an adjacency list for edges.

Reads a SUMO network file (.net.xml) and outputs:
- adjacency_list: For each edge, the list of successor edge IDs (edges reachable
  from that edge via its destination junction)
- edges: Optional metadata (edge_id, from_node, to_node, length) for each edge

Internal edges (junction-internal, IDs starting with ":") are excluded by default.
"""

import argparse
import json
import sys
from pathlib import Path

import sumolib


def get_removable_edges(net):
    """Get all non-internal edges (exclude junction-internal edges)."""
    edges = []
    for edge in net.getEdges():
        edge_id = edge.getID()
        if edge_id.startswith(":"):
            continue
        edges.append(edge)
    return edges


def extract_adjacency_list(net, include_internal: bool = False):
    """
    Extract adjacency list from SUMO network.

    For each edge E, the adjacency list contains edge IDs of edges reachable
    from E (successor edges via E's destination junction).

    Args:
        net: sumolib.net.Net object
        include_internal: If True, include internal edges in the adjacency list.
            If False, only list non-internal successors.

    Returns:
        dict: {edge_id: [successor_edge_id, ...], ...}
    """
    adjacency = {}
    for edge in net.getEdges():
        edge_id = edge.getID()
        if edge_id.startswith(":") and not include_internal:
            continue

        successors = []
        for out_edge in edge.getOutgoing():
            out_id = out_edge.getID()
            if include_internal or not out_id.startswith(":"):
                successors.append(out_id)

        adjacency[edge_id] = successors

    return adjacency


def extract_edge_metadata(edges):
    """Extract metadata for each edge."""
    return [
        {
            "edge_id": e.getID(),
            "from_node": e.getFromNode().getID(),
            "to_node": e.getToNode().getID(),
            "length": round(e.getLength(), 2),
        }
        for e in edges
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Extract adjacency list from SUMO net.xml file"
    )
    parser.add_argument(
        "net_file",
        type=Path,
        help="Path to SUMO network file (.net.xml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: <name>_adjacency.json, e.g. grid_11x11.net.xml -> grid_11x11_adjacency.json)",
    )
    parser.add_argument(
        "--include-internal",
        action="store_true",
        help="Include internal (junction) edges in adjacency list",
    )
    parser.add_argument(
        "--include-metadata",
        action="store_true",
        help="Include edge metadata (from_node, to_node, length) in output",
    )
    args = parser.parse_args()

    net_path = args.net_file
    if not net_path.exists():
        print(f"Error: Network file not found: {net_path}", file=sys.stderr)
        return 1

    output_path = args.output
    if output_path is None:
        # grid_11x11.net.xml -> grid_11x11_adjacency.json
        name = net_path.stem.removesuffix(".net") if net_path.stem.endswith(".net") else net_path.stem
        output_path = net_path.parent / f"{name}_adjacency.json"

    print(f"Loading network: {net_path}")
    net = sumolib.net.readNet(str(net_path))

    edges = get_removable_edges(net)
    print(f"Found {len(edges)} non-internal edges")

    adjacency = extract_adjacency_list(net, include_internal=args.include_internal)
    # Filter to only non-internal edges in keys if not including internal
    if not args.include_internal:
        adjacency = {k: v for k, v in adjacency.items() if not k.startswith(":")}

    result = {"adjacency_list": adjacency}

    if args.include_metadata:
        result["edges"] = extract_edge_metadata(edges)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Saved to {output_path}")
    print(f"  - {len(adjacency)} edges in adjacency list")

    # Show sample
    sample_id = next(iter(adjacency))
    print(f"  - Sample: {sample_id} -> {adjacency[sample_id][:5]}{'...' if len(adjacency[sample_id]) > 5 else ''}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
