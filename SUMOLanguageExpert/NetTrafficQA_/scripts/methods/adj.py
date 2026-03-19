"""
Method — Adjacency List

Gives the LLM the complete edge adjacency list as text and asks a single question.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import DEFAULT_MODEL, get_client, load_adjacency, adj_to_text


SYSTEM_PROMPT = """You are an expert in traffic network analysis specializing in SUMO simulations.
You are given a structural adjacency and coordinate list for a network and a question about it.

Answer the question with ONLY a single value (integer or as instructed).
Do NOT explain your reasoning. Do NOT show your work. Output ONLY the final answer. Nothing else.

Network connection and coordinate data:
{adj_text}"""


def ask(network: str, question: str, model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    adj = load_adjacency(network)
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT.format(adj_text=adj_to_text(adj)),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": f"Question: {question}"}],
    )
    return response.content[0].text.strip()
