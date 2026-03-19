"""
Shared utilities for baselines.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agentsumo import AgentSUMOConfig

import anthropic

NETWORK_DIR = (
    Path(__file__).parent.parent
    / "data"
    / "network"
)

XML_FILES = {
    "grid_11x11": NETWORK_DIR / "grid_11x11.net.xml",
    "random": NETWORK_DIR / "random.net.xml",
}

ADJ_FILES = {
    "grid_11x11": NETWORK_DIR / "grid_11x11_adjacency.json",
    "random": NETWORK_DIR / "random_adjacency.json",
}

DEFAULT_MODEL = "claude-sonnet-4-6"
# HAIKU_MODEL = "claude-haiku-4-5-20251001"


def get_client() -> anthropic.Anthropic:
    """Return an Anthropic API client."""
    return anthropic.Anthropic(api_key=AgentSUMOConfig.get_claude_api_key())


def load_xml(network: str) -> str:
    """Read the full SUMO .net.xml file as a string."""
    return XML_FILES[network].read_text(encoding="utf-8")


def load_adjacency(network: str) -> dict:
    """Load the edge adjacency list from the pre-generated JSON file."""
    with open(ADJ_FILES[network]) as f:
        return json.load(f)["adjacency_list"]


def adj_to_text(adj: dict) -> str:
    """Convert an adjacency dict with 'edges' and 'junctions' to a human-readable text representation."""
    lines = []

    # Process edges
    if "edges" in adj:
        lines.append("Edges (edge_id: [connected_edges]; [connected_nodes]):")
        for e in sorted(adj["edges"], key=lambda x: x["edge_id"]):
            eid = e["edge_id"]
            c_edges = ", ".join(e["connected_edges"])
            c_nodes = ", ".join(e["connected_nodes"])
            lines.append(f"- {eid}: [{c_edges}]; [{c_nodes}]")

    # Process junctions
    if "junctions" in adj:
        if lines:
            lines.append("")
        lines.append("Junctions (junction_id: [connected_edges]; [connected_nodes]; coordinates):")
        for j in sorted(adj["junctions"], key=lambda x: x["junction_id"]):
            jid = j["junction_id"]
            c_edges = ", ".join(j["connected_edges"])
            c_nodes = ", ".join(j["connected_nodes"])
            lines.append(f"- {jid}: [{c_edges}]; [{c_nodes}]; ({j['x']}, {j['y']})")

    return "\n".join(lines)
