"""
Shared utilities for baselines.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from agentsumo import AgentSUMOConfig

import anthropic

NETWORK_DIR = (
    Path(__file__).parent.parent.parent
    / "grid_experiment"
    / "experiment_setup"
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
    """Convert an adjacency dict to a human-readable text representation.

    Example:
        Input:  {"A0B0": ["B0C0", "B0B1"], "A0A1": ["A1B1", "A1A2"]}
        Output: A0A1: A1B1, A1A2
                A0B0: B0C0, B0B1
    """
    lines = []
    for edge in sorted(adj.keys()):
        lines.append(f"{edge}: {', '.join(adj[edge])}")
    return "\n".join(lines)
