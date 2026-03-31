#!/usr/bin/env python3
"""
AgentSUMO SQLite Ablation - Automated Benchmark Runner

자동으로 20개 벤치마크 질문을 순차 실행하고 결과를 저장.

Usage:
    # Full (SQLite MCP)
    python -m experiments_ceus.sqlite_ablation.auto_ablation_sqlite \
        --condition full --db-path /path/to/analysis.db --city gangnam

    # XML Only (Filesystem MCP)
    python -m experiments_ceus.sqlite_ablation.auto_ablation_sqlite \
        --condition xml_only --xml-dir /path/to/xml/files --city gangnam

    # No Data
    python -m experiments_ceus.sqlite_ablation.auto_ablation_sqlite \
        --condition no_data --city gangnam
"""

import asyncio
import sys
import argparse
import os
import json
import time
from pathlib import Path
from datetime import datetime

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


# ── Benchmark Questions ───────────────────────────────────────────────

CONTEXT_PREFIX_BASE = (
    "We have run three traffic simulations for this network in order: "
    "(1) a baseline simulation, "
    "(2) a Webster-based TLS adaptation scenario (Webster), "
    "(3) a Green Wave TLS offset scenario (Green Wave)."
)

CONTEXT_PREFIX_XML = (
    "We have run three traffic simulations for this network in order: "
    "(1) a baseline simulation, "
    "(2) a Webster-based TLS adaptation scenario (Webster), "
    "(3) a Green Wave TLS offset scenario (Green Wave). "
    "The simulation output XML files are stored in the provided directory. "
    "The files were generated in this order, so the first set of tripinfo/edgedata files "
    "corresponds to baseline, the second to Webster, and the third to Green Wave. "
    "Please answer the following questions based on the simulation data."
)

BENCHMARK_QUESTIONS = [
    # L1 — Single simulation, single numeric value
    {"id": "L1_01", "level": "L1", "question": "What is the average trip duration (in seconds) in the baseline?"},
    {"id": "L1_02", "level": "L1", "question": "What is the total waiting time of all vehicles (in seconds) in the baseline?"},
    {"id": "L1_03", "level": "L1", "question": "What is the average CO2 emission per vehicle (CO2_abs in mg) in the Webster scenario?"},
    {"id": "L1_04", "level": "L1", "question": "What is the maximum trip duration (in seconds) in the Green Wave scenario?"},
    {"id": "L1_05", "level": "L1", "question": "What percentage of vehicles have a waiting time greater than 60 seconds in the baseline?"},

    # L2 — Single simulation, aggregated value
    {"id": "L2_01", "level": "L2", "question": "What is the sum of density (veh/km) of the top 5 densest edges in the baseline?"},
    {"id": "L2_02", "level": "L2", "question": "What is the minimum speed (m/s) among the top 5 fastest edges in the Webster scenario?"},
    {"id": "L2_03", "level": "L2", "question": "What is the total trip duration (in seconds) of the top 5 longest-duration vehicles in the baseline?"},
    {"id": "L2_04", "level": "L2", "question": "What is the average CO2 emission (CO2_abs) of the top 5 highest-emission edges in the Green Wave scenario?"},
    {"id": "L2_05", "level": "L2", "question": "What percentage of vehicles have zero waiting time in the Green Wave scenario?"},

    # L3 — Multi-simulation, numeric comparison
    {"id": "L3_01", "level": "L3", "question": "What is the percentage reduction in average trip duration from baseline to Webster?"},
    {"id": "L3_02", "level": "L3", "question": "What is the percentage reduction in average waiting time from baseline to Green Wave?"},
    {"id": "L3_03", "level": "L3", "question": "What is the difference in average fuel consumption per vehicle (fuel_abs in ml) between Webster and Green Wave?"},
    {"id": "L3_04", "level": "L3", "question": "What is the percentage reduction in maximum edge density from baseline to Webster?"},
    {"id": "L3_05", "level": "L3", "question": "What is the difference in average time loss between baseline and Webster for the top 10% longest-duration vehicles (in seconds)?"},

    # L4 — Multi-simulation, judgment/synthesis
    {"id": "L4_01", "level": "L4", "question": "Which scenario has a higher percentage of vehicles with zero waiting time: Webster or Green Wave?"},
    {"id": "L4_02", "level": "L4", "question": "Which policy achieves a lower average edge density: Webster or Green Wave?"},
    {"id": "L4_03", "level": "L4", "question": "Which policy achieves a lower average CO2 emission on the top 5 highest-emission edges in the baseline: Webster or Green Wave?"},
    {"id": "L4_04", "level": "L4", "question": "Considering both average CO2 emission reduction and average fuel consumption reduction compared to baseline, which policy is more environmentally effective: Webster or Green Wave?"},
    {"id": "L4_05", "level": "L4", "question": "Among the top 10% vehicles by duration in the baseline, which policy reduces their average trip duration more: Webster or Green Wave?"},
]


# ── Session Logger (from chat_ablation_sqlite.py) ─────────────────────

class SessionLogger:
    def __init__(self, condition: str, city: str, output_dir: Path):
        self.condition = condition
        self.city = city
        self.output_dir = output_dir
        self.api_calls: list = []
        self.turn_times: list = []
        self.question_results: list = []
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

    def log_question_result(self, question_info: dict, response: str, elapsed: float,
                            api_calls_before: int, api_calls_after: int):
        """질문 1개의 결과를 기록."""
        # 이 질문에서 사용된 API calls
        question_api_calls = self.api_calls[api_calls_before:api_calls_after]
        q_input = sum(c.get("input_tokens", 0) for c in question_api_calls)
        q_output = sum(c.get("output_tokens", 0) for c in question_api_calls)

        self.question_results.append({
            "question_id": question_info["id"],
            "level": question_info["level"],
            "question": question_info["question"],
            "response": response,
            "elapsed_seconds": elapsed,
            "api_calls": len(question_api_calls),
            "input_tokens": q_input,
            "output_tokens": q_output,
            "total_tokens": q_input + q_output,
        })
        self.turn_times.append(elapsed)

    def save(self, agent=None):
        session_time = time.time() - self.session_start
        conversation_history = agent.conversation_history if agent is not None else []
        tool_calls = _count_tool_calls(conversation_history)

        total_input = sum(c.get("input_tokens", 0) for c in self.api_calls)
        total_output = sum(c.get("output_tokens", 0) for c in self.api_calls)

        # 1. experiment_log.json
        log_data = {
            "metadata": {
                "condition": self.condition,
                "city": self.city,
                "model": agent.model if agent is not None else "unknown",
                "num_questions": len(self.question_results),
                "session_start": self.session_start,
                "session_end": time.time(),
                "session_duration_seconds": session_time,
            },
            "summary": {
                "total_api_calls": len(self.api_calls),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "total_tool_calls": sum(tool_calls.values()),
                "tool_call_breakdown": tool_calls,
                "avg_time_per_question": session_time / max(len(self.question_results), 1),
            },
            "question_results": self.question_results,
            "api_calls": self.api_calls,
        }

        log_path = self.output_dir / "experiment_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)

        # 2. conversation_history.json
        serialized_history = _serialize_conversation_history(conversation_history)
        history_path = self.output_dir / "conversation_history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(serialized_history, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n{'='*60}")
        print(f"  Saved: {log_path}")
        print(f"         {history_path}")
        print(f"{'='*60}")
        print(f"  Condition    : {self.condition}")
        print(f"  City         : {self.city}")
        print(f"  Questions    : {len(self.question_results)}")
        print(f"  Duration     : {session_time:.1f}s")
        print(f"  API calls    : {len(self.api_calls)}")
        print(f"  Total tokens : {total_input + total_output:,}")
        print(f"  Tool calls   : {sum(tool_calls.values())} {tool_calls}")
        print(f"{'='*60}")


# ── Serialization Helpers ─────────────────────────────────────────────

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


# ── Monkey-patch for API tracking ─────────────────────────────────────

def _patch_agent(agent: AgentSUMO, logger: SessionLogger):
    original = agent._call_claude
    def tracked(*args, **kwargs):
        resp = original(*args, **kwargs)
        logger.log_api_call(resp)
        return resp
    agent._call_claude = tracked


# ── Condition Labels ──────────────────────────────────────────────────

CONDITION_LABELS = {
    "full": "Full (SQLite MCP)",
    "xml_only": "XML Only (Filesystem MCP)",
    "no_data": "No Data Access",
}


# ── Main ──────────────────────────────────────────────────────────────

async def main(condition: str, city: str, db_path: str = None, xml_dir: str = None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        PROJECT_ROOT / "experiments_ceus" / "sqlite_ablation" / "results"
        / city / condition / timestamp
    )

    session_logger = SessionLogger(condition, city, output_dir)

    print("\n" + "=" * 70)
    print(f"  AgentSUMO SQLite Ablation - Auto Benchmark")
    print(f"  Condition : {CONDITION_LABELS.get(condition, condition)}")
    print(f"  City      : {city}")
    print(f"  Questions : {len(BENCHMARK_QUESTIONS)}")
    if condition == "full" and db_path:
        print(f"  DB Path   : {db_path}")
    if condition == "xml_only" and xml_dir:
        print(f"  XML Dir   : {xml_dir}")
    print("=" * 70)

    # 조건별 시스템 프롬프트 템플릿
    TEMPLATES_DIR = PROJECT_ROOT / "agentsumo" / "agent" / "prompts" / "templates"
    CONDITION_TEMPLATES = {
        "full": None,  # 기본 unified_system.md (SQLite MCP 포함)
        "xml_only": (TEMPLATES_DIR / "unified_system_xml_only.md").read_text(encoding="utf-8"),
        "no_data": (TEMPLATES_DIR / "unified_system_no_sqlite.md").read_text(encoding="utf-8"),
    }

    # Build AgentSUMO kwargs
    agent_kwargs = {
        "enable_sumo_mcp": False,
        "inject_state": False,
        "system_prompt": CONDITION_TEMPLATES[condition],
    }

    if condition == "full":
        agent_kwargs["enable_sqlite_mcp"] = True
        agent_kwargs["enable_filesystem_mcp"] = False
        agent_kwargs["db_path"] = db_path
    elif condition == "xml_only":
        agent_kwargs["enable_sqlite_mcp"] = False
        agent_kwargs["enable_filesystem_mcp"] = True
        agent_kwargs["filesystem_root"] = xml_dir
    elif condition == "no_data":
        agent_kwargs["enable_sqlite_mcp"] = False
        agent_kwargs["enable_filesystem_mcp"] = False

    context_prefix = CONTEXT_PREFIX_XML if condition == "xml_only" else CONTEXT_PREFIX_BASE

    # xml_only: 각 질문마다 새 세션 (대화 누적으로 인한 토큰 초과 방지)
    # full/no_data: 단일 세션 (대화 이력 유지)
    per_question_session = (condition == "xml_only")

    async def run_question(q, agent_kw):
        """단일 질문을 새 AgentSUMO 인스턴스로 실행"""
        async with AgentSUMO(**agent_kw) as agent:
            _patch_agent(agent, session_logger)
            combined = f"{context_prefix}\n\n{q['question']}"
            return await agent.chat(combined)

    try:
        if per_question_session:
            # 툴 목록 미리 출력용으로 한 번만 연결
            async with AgentSUMO(**agent_kwargs) as agent:
                tool_names = [t["name"] for t in agent.tools]
            print(f"\n  Tools: {len(tool_names)}개 - {tool_names}")
            print(f"\n  Starting benchmark (per-question sessions)...\n")

            for i, q in enumerate(BENCHMARK_QUESTIONS):
                print(f"  [{i+1}/{len(BENCHMARK_QUESTIONS)}] {q['id']} ({q['level']})")
                print(f"  Q: {q['question']}")

                api_calls_before = len(session_logger.api_calls)
                turn_start = time.time()

                try:
                    response = await run_question(q, agent_kwargs)
                except Exception as e:
                    response = f"[ERROR] {e}"

                elapsed = time.time() - turn_start
                api_calls_after = len(session_logger.api_calls)

                session_logger.log_question_result(
                    q, response, elapsed, api_calls_before, api_calls_after
                )

                preview = response[:100].replace('\n', ' ')
                print(f"  A: {preview}...")
                print(f"  ({elapsed:.1f}s, {api_calls_after - api_calls_before} API calls)")
                print()

            session_logger.save(agent=None)

        else:
            async with AgentSUMO(**agent_kwargs) as agent:
                _patch_agent(agent, session_logger)

                tool_names = [t["name"] for t in agent.tools]
                print(f"\n  Tools: {len(tool_names)}개 - {tool_names}")
                print(f"\n  Starting benchmark...\n")

                print(f"  [Context] {context_prefix}")
                await agent.chat(context_prefix)
                print()

                for i, q in enumerate(BENCHMARK_QUESTIONS):
                    print(f"  [{i+1}/{len(BENCHMARK_QUESTIONS)}] {q['id']} ({q['level']})")
                    print(f"  Q: {q['question']}")

                    api_calls_before = len(session_logger.api_calls)
                    turn_start = time.time()

                    try:
                        response = await agent.chat(q["question"])
                    except Exception as e:
                        response = f"[ERROR] {e}"

                    elapsed = time.time() - turn_start
                    api_calls_after = len(session_logger.api_calls)

                    session_logger.log_question_result(
                        q, response, elapsed, api_calls_before, api_calls_after
                    )

                    preview = response[:100].replace('\n', ' ')
                    print(f"  A: {preview}...")
                    print(f"  ({elapsed:.1f}s, {api_calls_after - api_calls_before} API calls)")
                    print()

                session_logger.save(agent)

    except Exception as e:
        print(f"\n  Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentSUMO SQLite Ablation - Auto Benchmark")
    parser.add_argument(
        "--condition", choices=["full", "xml_only", "no_data"], required=True,
        help="full (SQLite), xml_only (Filesystem), no_data (no tools)"
    )
    parser.add_argument("--city", required=True, help="City name (e.g., gangnam, manhattan)")
    parser.add_argument("--db-path", default=None, help="SQLite DB 경로 (full 조건)")
    parser.add_argument("--xml-dir", default=None, help="XML 파일 디렉토리 (xml_only 조건)")

    args = parser.parse_args()

    if args.condition == "full" and not args.db_path:
        parser.error("--condition full 에는 --db-path 가 필요합니다.")
    if args.condition == "xml_only" and not args.xml_dir:
        parser.error("--condition xml_only 에는 --xml-dir 가 필요합니다.")

    # 절대경로로 변환 (MCP 서버 프로세스에서 상대경로 resolve 안 됨)
    db_path = str(Path(args.db_path).resolve()) if args.db_path else None
    xml_dir = str(Path(args.xml_dir).resolve()) if args.xml_dir else None

    asyncio.run(main(args.condition, args.city, db_path, xml_dir))
