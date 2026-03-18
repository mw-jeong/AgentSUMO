"""
Method — Raw XML

Gives the LLM the full SUMO .net.xml as context and asks a single question.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import DEFAULT_MODEL, get_client, load_xml


SYSTEM_PROMPT = """You are an expert in traffic network analysis specializing in SUMO simulations.
You are given the full SUMO .net.xml file below and a question about the network.

Answer the question with ONLY a single value (integer or as instructed).
Do NOT explain your reasoning. Do NOT show your work. Output ONLY the final answer. Nothing else.

Network file content:
{xml_text}"""


def ask(network: str, question: str, model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    xml_text = load_xml(network)
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT.format(xml_text=xml_text),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": f"Question: {question}"}],
    )
    return response.content[0].text.strip()
