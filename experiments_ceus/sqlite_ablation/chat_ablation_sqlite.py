#!/usr/bin/env python3
"""
AgentSUMO SQLite Ablation Chat Interface

3-way 비교를 위한 대화 인터페이스 + 세션 로깅.
--condition 플래그로 Full / XML-only / No-data 를 선택하고,
세션 종료 시 모든 로그를 자동 저장합니다.

Conditions:
    full     : SQLite MCP 활성화 (SQL query로 정확한 수치 추출)
    xml_only : Filesystem MCP만 활성화 (원본 XML 파일 직접 접근)
    no_data  : 데이터 접근 도구 없음 (LLM 기존 지식만)

Usage:
    python -m experiments_ceus.sqlite_ablation.chat_ablation_sqlite \
        --condition full --db-path /path/to/simulation.db
    python -m experiments_ceus.sqlite_ablation.chat_ablation_sqlite \
        --condition xml_only --xml-dir /path/to/xml/files
    python -m experiments_ceus.sqlite_ablation.chat_ablation_sqlite \
        --condition no_data
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


# ── Session Logger ─────────────────────────────────────────────────────

class SessionLogger:
    """
    세션별 로그 수집 및 저장.

    Captures:
    - conversation_history (raw, serialized)
    - per-API-call token usage (input/output/cache)
    - tool call details (name, args)
    - wall-clock time per chat turn
    - total session time
    - metadata (condition, model)
    """

    def __init__(self, condition: str, output_dir: Path):
        self.condition = condition
        self.output_dir = output_dir

        self.api_calls: list = []
        self.turn_times: list = []
        self.session_start = time.time()

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log_api_call(self, response):
        """Claude API 응답에서 token usage 기록."""
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
        """chat() 호출 1회의 wall-clock 시간 기록."""
        self.turn_times.append(elapsed)

    def save(self, agent: AgentSUMO):
        """세션 데이터를 2개 파일로 분리 저장.

        - experiment_log.json: metadata, summary, api_calls
        - conversation_history.json: 전체 대화 기록
        """
        session_time = time.time() - self.session_start
        serialized_history = _serialize_conversation_history(agent.conversation_history)
        tool_calls = _count_tool_calls(agent.conversation_history)

        total_input = sum(c.get("input_tokens", 0) for c in self.api_calls)
        total_output = sum(c.get("output_tokens", 0) for c in self.api_calls)
        total_cache_creation = sum(c.get("cache_creation_input_tokens", 0) for c in self.api_calls)
        total_cache_read = sum(c.get("cache_read_input_tokens", 0) for c in self.api_calls)

        # 1. experiment_log.json
        log_data = {
            "metadata": {
                "condition": self.condition,
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
                "interaction_turns": len(agent.conversation_history) // 2,
                "turn_times": self.turn_times,
                "total_session_time_seconds": session_time,
            },
            "api_calls": self.api_calls,
            "simulation_state": agent.simulation_state,
        }

        log_path = self.output_dir / "experiment_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)

        # 2. conversation_history.json
        history_path = self.output_dir / "conversation_history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(serialized_history, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n{'='*60}")
        print(f"  Saved:")
        print(f"    {log_path}")
        print(f"    {history_path}")
        print(f"{'='*60}")
        print(f"  Condition    : {self.condition}")
        print(f"  Duration     : {session_time:.1f}s")
        print(f"  API calls    : {len(self.api_calls)}")
        print(f"  Total tokens : {total_input + total_output:,} (in:{total_input:,} / out:{total_output:,})")
        print(f"  Cache        : creation={total_cache_creation:,}, read={total_cache_read:,}")
        print(f"  Tool calls   : {sum(tool_calls.values())} {tool_calls}")
        print(f"  Turns        : {len(agent.conversation_history) // 2}")
        print(f"{'='*60}")


# ── Serialization Helpers ──────────────────────────────────────────────

def _serialize_conversation_history(history: list) -> list:
    """conversation_history를 JSON-safe 형태로 변환."""
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
    """conversation_history에서 tool call 횟수 집계."""
    counts = {}
    for msg in history:
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "type") and block.type == "tool_use":
                        counts[block.name] = counts.get(block.name, 0) + 1
    return counts


# ── Monkey-patch for API tracking ──────────────────────────────────────

def _patch_agent(agent: AgentSUMO, logger: SessionLogger):
    """_call_claude를 래핑하여 매 API 호출의 usage를 기록."""
    original = agent._call_claude

    def tracked(*args, **kwargs):
        resp = original(*args, **kwargs)
        logger.log_api_call(resp)
        return resp

    agent._call_claude = tracked


# ── Condition Label ────────────────────────────────────────────────────

CONDITION_LABELS = {
    "full": "Full (SQLite MCP)",
    "xml_only": "XML Only (Filesystem MCP)",
    "no_data": "No Data Access",
}


# ── Main ───────────────────────────────────────────────────────────────

async def main(condition: str, db_path: str = None, xml_dir: str = None):
    output_dir = (
        PROJECT_ROOT / "experiments_ceus" / "sqlite_ablation" / "results" / condition
    )

    session_logger = SessionLogger(condition, output_dir)

    print("\n" + "=" * 70)
    print(f"  AgentSUMO SQLite Ablation Chat")
    print(f"  Condition: {CONDITION_LABELS.get(condition, condition)}")
    if condition == "full" and db_path:
        print(f"  DB Path  : {db_path}")
    if condition == "xml_only" and xml_dir:
        print(f"  XML Dir  : {xml_dir}")
    print("=" * 70)
    print("\n초기화 중...")

    # Build AgentSUMO kwargs based on condition
    agent_kwargs = {
        "enable_sumo_mcp": False,  # ablation에서는 SUMO MCP 불필요
        "inject_state": False,     # state 주입 불필요
    }

    if condition == "full":
        # SQLite MCP만 활성화
        agent_kwargs["enable_sqlite_mcp"] = True
        agent_kwargs["enable_filesystem_mcp"] = False
        agent_kwargs["db_path"] = db_path
    elif condition == "xml_only":
        # Filesystem MCP만 활성화
        agent_kwargs["enable_sqlite_mcp"] = False
        agent_kwargs["enable_filesystem_mcp"] = True
        agent_kwargs["filesystem_root"] = xml_dir
    elif condition == "no_data":
        # 데이터 접근 도구 없음
        agent_kwargs["enable_sqlite_mcp"] = False
        agent_kwargs["enable_filesystem_mcp"] = False

    try:
        async with AgentSUMO(**agent_kwargs) as agent:
            _patch_agent(agent, session_logger)

            # 사용 가능한 도구 목록 표시
            tool_names = [t["name"] for t in agent.tools]
            print(f"\n사용 가능한 도구 ({len(tool_names)}개):")
            for name in tool_names:
                print(f"  - {name}")

            print("\n준비 완료!")
            print("\n명령어:")
            print("  'quit' / 'exit' : 종료 (로그 저장)")
            print("  'state'         : 현재 상태 확인")
            print("  'reset'         : 대화 이력 리셋")
            print("=" * 70 + "\n")

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

                    if user_input.lower() == 'reset':
                        agent.reset_conversation()
                        print("\n대화 이력 리셋됨.")
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
    parser = argparse.ArgumentParser(description="AgentSUMO SQLite Ablation Chat")
    parser.add_argument(
        "--condition", choices=["full", "xml_only", "no_data"], required=True,
        help="full (SQLite), xml_only (Filesystem), no_data (no tools)"
    )
    parser.add_argument(
        "--db-path", default=None,
        help="SQLite DB 경로 (full 조건에서 필수)"
    )
    parser.add_argument(
        "--xml-dir", default=None,
        help="XML 파일 디렉토리 (xml_only 조건에서 필수)"
    )

    args = parser.parse_args()

    # Validation
    if args.condition == "full" and not args.db_path:
        parser.error("--condition full 에는 --db-path 가 필요합니다.")
    if args.condition == "xml_only" and not args.xml_dir:
        parser.error("--condition xml_only 에는 --xml-dir 가 필요합니다.")

    asyncio.run(main(args.condition, args.db_path, args.xml_dir))
