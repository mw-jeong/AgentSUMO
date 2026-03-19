#!/usr/bin/env python3
"""
Preprocess a SUMO net.xml file to extract connections and metadata for edges and junctions.

Reads a SUMO network file (.net.xml) and outputs:
- edges: List of edges with their connected edges and nodes.
- junctions: List of junctions with their connected edges, nodes, and coordinates.

Internal edges/nodes (IDs starting with ":") are excluded by default.
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


def extract_edges(net, include_internal: bool = False):
    """Extract edge data including connections and metadata."""
    edges_data = []
    for edge in net.getEdges():
        edge_id = edge.getID()
        if edge_id.startswith(":") and not include_internal:
            continue

        # Successor edges
        connected_edges = []
        for out_edge in edge.getOutgoing():
            out_id = out_edge.getID()
            if include_internal or not out_id.startswith(":"):
                connected_edges.append(out_id)

        # Successor node (to_node)
        connected_nodes = []
        to_node_id = edge.getToNode().getID()
        if include_internal or not to_node_id.startswith(":"):
            connected_nodes.append(to_node_id)

        edges_data.append(
            {
                "edge_id": edge_id,
                "connected_edges": sorted(connected_edges),
                "connected_nodes": sorted(connected_nodes),
            }
        )
    return edges_data


def extract_junctions(net, include_internal: bool = False):
    """Extract junction data including connections and metadata."""
    junctions_data = []
    for node in net.getNodes():
        node_id = node.getID()
        if node_id.startswith(":") and not include_internal:
            continue

        # Outgoing edges
        connected_edges = []
        for out_edge in node.getOutgoing():
            out_id = out_edge.getID()
            if include_internal or not out_id.startswith(":"):
                connected_edges.append(out_id)

        # Neighboring nodes (via outgoing edges)
        connected_nodes = set()
        for out_edge in node.getOutgoing():
            if not include_internal and out_edge.getID().startswith(":"):
                continue
            neighbor_id = out_edge.getToNode().getID()
            if neighbor_id != node_id:
                if include_internal or not neighbor_id.startswith(":"):
                    connected_nodes.add(neighbor_id)

        junctions_data.append(
            {
                "junction_id": node_id,
                "connected_edges": sorted(connected_edges),
                "connected_nodes": sorted(list(connected_nodes)),
                "x": round(node.getCoord()[0], 2),
                "y": round(node.getCoord()[1], 2),
            }
        )
    return junctions_data


def main():
    parser = argparse.ArgumentParser(
        description="Extract adjacency list (including junctions and edges) from SUMO net.xml file"
    )
    parser.add_argument(
        "--net_file",
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
        help="Include internal (junction) edges and nodes",
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

    edges_data = extract_edges(net, include_internal=args.include_internal)
    junctions_data = extract_junctions(net, include_internal=args.include_internal)

    result = {
        "adjacency_list": {
            "edges": edges_data,
            "junctions": junctions_data,
        }
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Saved to {output_path}")
    print(f"  - {len(edges_data)} edges")
    print(f"  - {len(junctions_data)} junctions")

    # Show sample
    if edges_data:
        sample = edges_data[0]
        print(f"  - Sample Edge: {sample['edge_id']} -> {sample['connected_edges'][:3]}...")
    if junctions_data:
        sample = junctions_data[0]
        print(f"  - Sample Junction: {sample['junction_id']} -> {sample['connected_nodes'][:3]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
