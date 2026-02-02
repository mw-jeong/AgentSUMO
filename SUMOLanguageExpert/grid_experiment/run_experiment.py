#!/usr/bin/env python3
"""통합 Text-to-SQL 실험 스크립트

실행할 전략을 SELECTED 리스트에서 선택하세요.
"""

import asyncio
import csv
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentsumo import AgentSUMO

# ============================================================
# 실행할 전략 선택 (원하는 것만 남기세요)
# ============================================================
SELECTED = [
    #"01_autonomous",
    #"02_neighbor",
    #"03_cross",
    "04_exhaustive",
]

# ============================================================
# 전략별 프롬프트 정의
# ============================================================
STRATEGY_PROMPTS = {
    "01_autonomous": "",  # 자율: 추가 유도 없음

    "02_neighbor": """
Search Strategy: NEIGHBOR (adjacent edges only)

Adjacent edges share a node with the target edge.
Example: For C3C4, adjacent edges are C2C3, C4C5 (vertical) and C3D3, C4D4, B3C3, B4C4 (horizontal).

Query adjacent edge removal scenarios from the training DB to infer patterns.
""",

    "03_cross": """
Search Strategy: CROSS (same column/row only)

Query edges in the same column or row as the target edge.
Example: For vertical edge C3C4 (column C), query C0C1, C1C2, C2C3, C4C5, C5C6, etc.
Example: For horizontal edge C3D3 (row 3), query A3B3, B3C3, D3E3, E3F3, etc.

Query same-column/row edge removal scenarios from the training DB.
""",

    "04_exhaustive": """
Search Strategy: EXHAUSTIVE (all training data)

Use all available edge removal scenarios without spatial filtering.
Example: Query all 176 training simulations to find density increase patterns.

Query all edge removal scenarios from the training DB.
""",
}

# ============================================================
# 공통 설정
# ============================================================
BASE_DIR = Path(__file__).parent
SETUP_DIR = BASE_DIR / "experiment_setup"
DATA_DIR = SETUP_DIR / "results"
RESULTS_DIR = BASE_DIR / "results"

QUESTION_TEMPLATE = """If the {edge_id} edge is removed from the 11x11 grid network, which column (A-K) or row (0-10) contains the edge with the largest density INCREASE compared to baseline?

Use the training DB to find similar scenarios. Answer with only one letter (A-K) or number (0-10)."""

COMMON_PROMPT = """
You must use the training DB to infer the answer for this UNSEEN scenario.
This specific edge removal simulation does NOT exist in the DB - you must reason from similar cases.

DB Schema:
- simulations (simulation_id, created_at, vehicle_count, net_file, route_file, description)
- trips (simulation_id, trip_id, duration, routeLength, waitingTime, timeLoss, depart, arrival, ...)
- edge_metrics (simulation_id, edge_id, interval_begin, interval_end, speed, density, waitingTime, timeLoss, ...)

Key columns:
- simulations.description: "A0A1 edge removed" format (identifies which edge was removed in each simulation)
- edge_metrics.density: road density (higher = more congested)
- edge_metrics.edge_id: edge ID (e.g., A0A1, B2C2)

SQL queries must start with SELECT. Do NOT use WITH clauses (CTEs) - rewrite them as subqueries instead.

Output format (exactly 2 lines):
1. ANSWER: <your answer>
2. REASONING: <2 sentences explaining your reasoning>
"""


def load_test_edges():
    """test_*.json에서 테스트 엣지 목록 로드"""
    test_files = list(DATA_DIR.glob("test_*.json"))
    test_file = sorted(test_files)[-1]

    with open(test_file, 'r') as f:
        data = json.load(f)

    edges = []
    for sim in data["simulations"]:
        edge_id = sim["simulation"]["edge_info"]["edge_id"]
        edges.append(edge_id)
    return edges


def load_ground_truth():
    """Ground Truth 로드"""
    gt_file = DATA_DIR / "ground_truth_test_44.csv"
    gt = {}
    with open(gt_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            edge = row["edge"].replace(" edge removed", "")
            gt[edge] = row["Q6_max_density_road"]
    return gt


def generate_questions(test_edges):
    """질문 생성"""
    questions = []
    for edge_id in test_edges:
        question = QUESTION_TEMPLATE.format(edge_id=edge_id)
        questions.append({
            "edge_id": edge_id,
            "question": question,
        })
    return questions


def parse_answer(response):
    """LLM 응답에서 답변 추출"""
    patterns = [
        r'\*\*ANSWER[:\s]*\*?\*?[:\s]*([A-K]|10|[0-9])\b',
        r'ANSWER[:\s]+([A-K]|10|[0-9])\b',
        r'\*\*ANSWER[:\s]+([A-K]|10|[0-9])\b',
        r'(?:the\s+)?answer\s+(?:is|should be|would be)[:\s]*\*?\*?([A-K]|10|[0-9])\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return ""


def format_conversation_history(history: list) -> str:
    """conversation_history를 읽기 좋은 텍스트로 변환"""
    lines = []
    turn = 0

    for msg in history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "user":
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_content = item.get("content", "")
                        if len(str(tool_content)) > 2000:
                            tool_content = str(tool_content)[:2000] + "\n... [TRUNCATED]"
                        lines.append(f"\n[Turn {turn} - Tool Result]\n{tool_content}")
            else:
                turn += 1
                lines.append(f"\n{'='*60}\n[Turn {turn} - User]\n{content}")

        elif role == "assistant":
            if isinstance(content, list):
                for item in content:
                    item_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)

                    if item_type == "tool_use":
                        tool_name = getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else "unknown")
                        tool_input = getattr(item, "input", None) or (item.get("input") if isinstance(item, dict) else {})
                        lines.append(f"\n[Turn {turn} - Assistant (tool_use)]\nTool: {tool_name}\nInput: {json.dumps(tool_input, indent=2, ensure_ascii=False)}")
                    elif item_type == "text":
                        text = getattr(item, "text", None) or (item.get("text") if isinstance(item, dict) else "")
                        if text:
                            lines.append(f"\n[Turn {turn} - Assistant]\n{text}")
                    elif item_type == "thinking":
                        thinking = getattr(item, "thinking", None) or (item.get("thinking") if isinstance(item, dict) else "")
                        if thinking:
                            lines.append(f"\n[Turn {turn} - Assistant (thinking)]\n{thinking}")
            else:
                lines.append(f"\n[Turn {turn} - Assistant]\n{content}")

    return "\n".join(lines)


def save_conversation(edge_id: str, history: list, strategy: str):
    """conversation_history를 파일로 저장"""
    conv_dir = RESULTS_DIR / f"{strategy}_conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)

    formatted = format_conversation_history(history)
    filename = conv_dir / f"{edge_id}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Strategy: {strategy}\n")
        f.write(f"Edge: {edge_id}\n")
        f.write(f"Messages: {len(history)}\n")
        f.write("=" * 60 + "\n")
        f.write(formatted)

    return filename


async def run_strategy(strategy_name: str, test_edges: list, ground_truth: dict, questions: list):
    """단일 전략 실행"""
    print(f"\n{'='*60}")
    print(f"Text-to-SQL 실험: {strategy_name} 전략")
    print(f"{'='*60}")

    # 시스템 프롬프트 생성
    strategy_prompt = STRATEGY_PROMPTS.get(strategy_name, "")
    system_prompt = COMMON_PROMPT.strip()
    if strategy_prompt:
        system_prompt += "\n\n" + strategy_prompt.strip()

    results = []
    db_path = str(DATA_DIR / "simulations.db")

    async with AgentSUMO(db_path=db_path, system_prompt=system_prompt, enable_sumo_mcp=False, inject_state=False) as agent:
        for i, q in enumerate(questions):
            print(f"[{i+1}/{len(questions)}] {q['edge_id']}")

            try:
                agent.reset_conversation()

                response = await agent.chat(q["question"])

                conv_file = save_conversation(q["edge_id"], agent.conversation_history, strategy_name)
                print(f"   대화 저장: {conv_file.name}")

                answer = parse_answer(response)
                print(f"   응답: {answer}")

                full_prompt = system_prompt + "\n\n" + q["question"]

                results.append({
                    "edge_id": q["edge_id"],
                    "prompt": full_prompt,
                    "response": response,
                    "answer": answer,
                    "gt_answer": ground_truth.get(q["edge_id"], ""),
                })

            except Exception as e:
                print(f"   ERROR: {e}")
                full_prompt = system_prompt + "\n\n" + q["question"]
                results.append({
                    "edge_id": q["edge_id"],
                    "prompt": full_prompt,
                    "response": f"ERROR: {e}",
                    "answer": "",
                    "gt_answer": ground_truth.get(q["edge_id"], ""),
                })

    # 결과 저장
    csv_file = RESULTS_DIR / f"{strategy_name}_answers.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "edge_id", "prompt", "response", "answer", "gt_answer"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n결과 저장: {csv_file}")
    print(f"총 {len(results)}개 응답 저장 완료")

    return strategy_name, results


async def run_experiment():
    """실험 실행"""
    RESULTS_DIR.mkdir(exist_ok=True)

    test_edges = load_test_edges()
    ground_truth = load_ground_truth()
    questions = generate_questions(test_edges)

    print(f"테스트 엣지: {len(test_edges)}개")
    print(f"총 질문: {len(questions)}개")
    print(f"선택된 전략: {SELECTED}")

    all_results = {}

    for strategy_name in SELECTED:
        if strategy_name not in STRATEGY_PROMPTS:
            print(f"WARNING: {strategy_name} 전략이 정의되지 않음, 건너뜀")
            continue

        strategy, results = await run_strategy(strategy_name, test_edges, ground_truth, questions)
        all_results[strategy] = results

    # 요약 출력
    print("\n" + "=" * 60)
    print("실험 완료 요약")
    print("=" * 60)
    for strategy, results in all_results.items():
        correct = sum(1 for r in results if r["answer"] == r["gt_answer"])
        print(f"{strategy}: {correct}/{len(results)} ({correct/len(results)*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(run_experiment())
