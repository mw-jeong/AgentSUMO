#!/usr/bin/env python3
"""
AgentSUMO IPP Ablation Chat Interface

chat.py와 동일한 대화 인터페이스 + 세션 로깅.
--condition 플래그로 Full / No-IPP 프롬프트를 선택하고,
세션 종료 시 모든 로그(conversation_history, token usage, tool calls, time)를
experiment_log.json으로 자동 저장합니다.

Usage:
    python -m experiments_ceus.ipp_ablation.chat_ablation --condition full --scenario s1 --iteration 1
    python -m experiments_ceus.ipp_ablation.chat_ablation --condition no_ipp --scenario s2 --iteration 3
"""

import asyncio
import sys
import argparse
import os
import json
import time
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agentsumo import AgentSUMO

# Load API key
api_key_file = PROJECT_ROOT / "claude_api.txt"
env_file = PROJECT_ROOT / ".env"

if api_key_file.exists():
    with open(api_key_file) as f:
        api_key = f.read().strip()
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
elif env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value


# ── Scenarios ─────────────────────────────────────────────────────────

SCENARIOS = {
    "s1": "How congested is the traffic around Gangnam Station?",
    "s2": "What would be the impact of lane closure on Teheran-ro near Gangnam Station?",
    "s3": "How would increasing the EV ratio affect air quality near Gangnam Station?",
    "s4": "After an event at Gangnam Station, traffic spreads in all directions. Find where congestion builds and how to clear it faster.",
}


# ── Session Logger ─────────────────────────────────────────────────────

class SessionLogger:
    def __init__(self, condition: str, scenario: str, iteration: int, output_dir: Path):
        self.condition = condition
        self.scenario = scenario
        self.iteration = iteration
        self.output_dir = output_dir

        self.api_calls: list = []
        self.turn_times: list = []
        self.session_start = time.time()

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log_api_call(self, response):
        usage = response.usage
        entry = {
            "timestamp": time.time(),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "model": response.model,
            "stop_reason": response.stop_reason,
        }
        if hasattr(usage, "cache_creation_input_tokens"):
            entry["cache_creation_input_tokens"] = usage.cache_creation_input_tokens
        if hasattr(usage, "cache_read_input_tokens"):
            entry["cache_read_input_tokens"] = usage.cache_read_input_tokens
        self.api_calls.append(entry)

    def log_turn_time(self, elapsed: float):
        self.turn_times.append(elapsed)

    def save(self, agent: AgentSUMO):
        session_time = time.time() - self.session_start
        serialized_history = _serialize_conversation_history(agent.conversation_history)
        tool_calls = _count_tool_calls(agent.conversation_history)
        tool_sequence = _extract_tool_sequence(agent.conversation_history)
        parameters_used = _extract_parameters(agent.conversation_history)

        total_input = sum(c.get("input_tokens", 0) for c in self.api_calls)
        total_output = sum(c.get("output_tokens", 0) for c in self.api_calls)
        total_cache_creation = sum(c.get("cache_creation_input_tokens", 0) for c in self.api_calls)
        total_cache_read = sum(c.get("cache_read_input_tokens", 0) for c in self.api_calls)

        log_data = {
            "metadata": {
                "condition": self.condition,
                "scenario": self.scenario,
                "iteration": self.iteration,
                "model": agent.model,
                "session_start": self.session_start,
                "session_end": time.time(),
                "session_duration_seconds": session_time,
            },
            "summary": {
                "total_api_calls": len(self.api_calls),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "total_cache_creation_tokens": total_cache_creation,
                "total_cache_read_tokens": total_cache_read,
                "total_tool_calls": sum(tool_calls.values()),
                "tool_call_breakdown": tool_calls,
                "tool_sequence": tool_sequence,
                "parameters_used": parameters_used,
                "interaction_turns": len(agent.conversation_history) // 2,
                "user_turns": len(self.turn_times),
                "turn_times": self.turn_times,
                "total_session_time_seconds": session_time,
            },
            "api_calls": self.api_calls,
            "simulation_state": agent.simulation_state,
        }

        log_path = self.output_dir / "experiment_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)

        history_path = self.output_dir / "conversation_history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(serialized_history, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n{'='*60}")
        print(f"  Saved:")
        print(f"    {log_path}")
        print(f"    {history_path}")
        print(f"{'='*60}")
        print(f"  Condition    : {self.condition}")
        print(f"  Scenario     : {self.scenario}")
        print(f"  Iteration    : {self.iteration}")
        print(f"  Duration     : {session_time:.1f}s")
        print(f"  API calls    : {len(self.api_calls)}")
        print(f"  Total tokens : {total_input + total_output:,} (in:{total_input:,} / out:{total_output:,})")
        print(f"  Tool calls   : {sum(tool_calls.values())} {tool_calls}")
        print(f"  Tool sequence: {tool_sequence}")
        print(f"  User turns   : {len(self.turn_times)}")
        print(f"{'='*60}")


# ── Serialization Helpers ──────────────────────────────────────────────

def _serialize_conversation_history(history: list) -> list:
    serialized = []
    for msg in history:
        entry = {"role": msg["role"]}
        content = msg.get("content")

        if isinstance(content, str):
            entry["content"] = content
        elif isinstance(content, list):
            blocks = []
            for block in content:
                if isinstance(block, dict):
                    blocks.append(block)
                elif hasattr(block, "type"):
                    b = {"type": block.type}
                    if block.type == "text":
                        b["text"] = block.text
                    elif block.type == "thinking":
                        b["thinking"] = block.thinking
                    elif block.type == "tool_use":
                        b["id"] = block.id
                        b["name"] = block.name
                        b["input"] = block.input
                    else:
                        b["raw"] = str(block)
                    blocks.append(b)
                else:
                    blocks.append(str(block))
            entry["content"] = blocks
        else:
            entry["content"] = str(content) if content else None

        serialized.append(entry)
    return serialized


def _count_tool_calls(history: list) -> dict:
    counts = {}
    for msg in history:
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "type") and block.type == "tool_use":
                        counts[block.name] = counts.get(block.name, 0) + 1
    return counts


def _extract_tool_sequence(history: list) -> list:
    """Extract ordered list of tool calls."""
    sequence = []
    for msg in history:
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "type") and block.type == "tool_use":
                        sequence.append(block.name)
    return sequence


def _extract_parameters(history: list) -> dict:
    """Extract key parameters from tool calls for consistency analysis."""
    params = {}
    for msg in history:
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "type") and block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        if tool_name == "net_generate":
                            params["radius"] = tool_input.get("radius")
                            params["city"] = tool_input.get("city")
                            params["trip_type"] = tool_input.get("trip_type")
                        elif tool_name == "trip_generate":
                            params["traffic_condition"] = tool_input.get("traffic_condition")
                        elif tool_name == "sumo_runner":
                            params["duration"] = tool_input.get("duration")
                        elif tool_name == "speed_limit_edit_tool":
                            params["speed_limit_road"] = tool_input.get("target_road_name")
                            params["speed_limit_value"] = tool_input.get("new_speed")
                        elif tool_name == "vehicle_type_edit_tool":
                            params["electric_ratio"] = tool_input.get("electric_ratio")
    return params


# ── Monkey-patch for API tracking ──────────────────────────────────────

def _patch_agent(agent: AgentSUMO, logger: SessionLogger):
    original = agent._call_claude

    def tracked(*args, **kwargs):
        resp = original(*args, **kwargs)
        logger.log_api_call(resp)
        return resp

    agent._call_claude = tracked


# ── Main ───────────────────────────────────────────────────────────────

async def main(condition: str, scenario: str, iteration: int):
    output_dir = (
        PROJECT_ROOT / "experiments_ceus" / "ipp_ablation" / "results"
        / scenario / condition / f"iteration{iteration}"
    )

    session_logger = SessionLogger(condition, scenario, iteration, output_dir)

    # System prompt selection
    if condition == "no_ipp":
        prompt_path = (
            PROJECT_ROOT / "agentsumo" / "agent" / "prompts" / "templates"
            / "unified_system_no_ipp.md"
        )
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = None  # default (with IPP)

    scenario_prompt = SCENARIOS[scenario]

    print("\n" + "=" * 70)
    print(f"  AgentSUMO IPP Ablation Chat")
    print(f"  Condition : {'Full (with IPP)' if condition == 'full' else 'No IPP'}")
    print(f"  Scenario  : {scenario} - \"{scenario_prompt}\"")
    print(f"  Iteration : {iteration}")
    print("=" * 70)
    print("\n초기화 중...")

    try:
        async with AgentSUMO(system_prompt=system_prompt) as agent:
            _patch_agent(agent, session_logger)

            print("\n준비 완료!")
            print(f"\n첫 입력: \"{scenario_prompt}\"")
            print("\n명령어:")
            print("  'quit' / 'exit' : 종료 (로그 저장)")
            print("  'state'         : 현재 상태 확인")
            print("=" * 70 + "\n")

            # 첫 입력 자동 전송
            print(f"\nYou: {scenario_prompt}")
            print()
            turn_start = time.time()
            response = await agent.chat(scenario_prompt)
            turn_time = time.time() - turn_start
            session_logger.log_turn_time(turn_time)

            print(f"\nAgentSUMO ({turn_time:.1f}s):")
            print("-" * 70)
            print(response)
            print("-" * 70)

            # 이후 대화
            while True:
                try:
                    user_input = input("\nYou: ").strip()

                    if not user_input:
                        continue

                    if user_input.lower() in ('quit', 'exit', 'q', 'bye'):
                        print("\n세션을 종료합니다...")
                        break

                    if user_input.lower() == 'state':
                        state = agent.get_state()
                        print(f"\n  Network: {state['simulation_state']['current_network'] or 'None'}")
                        print(f"  Routes:  {state['simulation_state']['current_routes'] or 'None'}")
                        print(f"  Turns:   {state['conversation_turns']}")
                        print(f"  Tools:   {state['tools_available']}")
                        continue

                    # Chat
                    print()
                    turn_start = time.time()
                    response = await agent.chat(user_input)
                    turn_time = time.time() - turn_start
                    session_logger.log_turn_time(turn_time)

                    print(f"\nAgentSUMO ({turn_time:.1f}s):")
                    print("-" * 70)
                    print(response)
                    print("-" * 70)

                except KeyboardInterrupt:
                    print("\n\nCtrl+C. 'quit'을 입력하면 로그가 저장됩니다.\n")
                    continue

                except EOFError:
                    print("\n세션을 종료합니다...")
                    break

                except Exception as e:
                    print(f"\n오류: {e}")
                    print("계속 대화할 수 있습니다.\n")

            # Save session log
            session_logger.save(agent)

    except KeyboardInterrupt:
        print("\n종료.")
        sys.exit(0)
    except Exception as e:
        print(f"\n초기화 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentSUMO IPP Ablation Chat")
    parser.add_argument(
        "--condition", choices=["full", "no_ipp"], required=True,
        help="full (with IPP) or no_ipp (without IPP)"
    )
    parser.add_argument(
        "--scenario", choices=list(SCENARIOS.keys()), required=True,
        help="Scenario to run (s1/s2/s3/s4)"
    )
    parser.add_argument(
        "--iteration", type=int, required=True,
        help="Iteration number (1-5)"
    )

    args = parser.parse_args()
    asyncio.run(main(args.condition, args.scenario, args.iteration))