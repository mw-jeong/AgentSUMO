"""
Method — Code Generation (Tool Use Agent)

Gives the LLM a path to the SUMO .net.xml and a question. The LLM can freely
reason and call the `run_python` tool whenever it wants to execute code.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import DEFAULT_MODEL, XML_FILES, get_client


CODE_TIMEOUT = 10
MAX_TURNS = 10

SYSTEM_PROMPT = """You are an expert in traffic network analysis specializing in SUMO simulations.
You are given a path to a SUMO .net.xml file and a question about the network.

You have access to a `run_python` tool that executes Python code and returns stdout/stderr.
Use it to read the network file, analyze it, and compute the answer.

When you have the final answer, respond with ONLY the final value. Nothing else.

SUMO network file path: {xml_path}"""

TOOLS = [
    {
        "name": "run_python",
        "description": "Execute a Python script. The script should be self-contained (no external libraries except standard library). Returns stdout and stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                }
            },
            "required": ["code"],
        },
    }
]


def run_code(code: str, timeout: int = CODE_TIMEOUT) -> tuple[str, str]:
    """Execute code in a temp file. Returns (stdout, stderr)."""
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp = f.name
        result = subprocess.run(
            ["python3", tmp],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "timeout"
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def ask(network: str, question: str, model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    xml_path = str(XML_FILES[network].resolve())
    system = [{
        "type": "text",
        "text": SYSTEM_PROMPT.format(xml_path=xml_path),
        "cache_control": {"type": "ephemeral"},
    }]

    trace = []
    messages = [{"role": "user", "content": f"Question: {question}"}]

    for turn in range(MAX_TURNS):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=messages,
            tools=TOOLS,
        )
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        for block in assistant_content:
            if block.type == "text":
                trace.append({"role": "assistant", "text": block.text})
            elif block.type == "tool_use":
                trace.append({"role": "tool_call", "name": block.name, "code": block.input.get("code", "")})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "max_tokens":
            has_tool_use = any(b.type == "tool_use" for b in assistant_content)
            if has_tool_use:
                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        trace.append({"role": "execution", "stdout": "", "stderr": "max_tokens reached, code truncated"})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Error: response was truncated (max_tokens). Try a shorter approach.",
                            "is_error": True,
                        })
                messages.append({"role": "user", "content": tool_results})
                continue
            else:
                break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    code = block.input.get("code", "")
                    stdout, stderr = run_code(code)
                    result_text = ""
                    if stdout:
                        result_text += f"stdout:\n{stdout}"
                    if stderr:
                        if result_text:
                            result_text += "\n"
                        result_text += f"stderr:\n{stderr}"
                    if not result_text:
                        result_text = "(no output)"

                    trace.append({"role": "execution", "stdout": stdout, "stderr": stderr})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })
            messages.append({"role": "user", "content": tool_results})

    return json.dumps(trace, ensure_ascii=False)
