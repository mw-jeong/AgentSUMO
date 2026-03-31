#!/usr/bin/env python3
"""
IPP Ablation — Evaluation Script

Two types of evaluation:
1. Direct metrics (from experiment_log.json): turns, tokens, tool sequence, parameter consistency
2. DeepEval metrics (LLM-as-judge): ConversationCompleteness, ArgumentCorrectness,
   G-Eval x2, GoalAccuracy, MCPTaskCompletion, MCPUse, MultiTurnMCPUse

Usage:
    # Direct metrics only (no API calls)
    python -m experiments_ceus.ipp_ablation.evaluate_ipp --mode direct

    # DeepEval metrics only (first iteration only for quick test)
    python -m experiments_ceus.ipp_ablation.evaluate_ipp --mode deepeval --iterations 1

    # Both, all iterations
    python -m experiments_ceus.ipp_ablation.evaluate_ipp --mode all
"""

import json
import argparse
import os
import time
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
PROJECT_ROOT = BASE_DIR.parent.parent

SCENARIOS = ["s1", "s2", "s3", "s4"]
CONDITIONS = ["full", "no_ipp"]

SCENARIO_DESCRIPTIONS = {
    "s1": "How congested is the traffic around Gangnam Station?",
    "s2": "What would be the impact of lane closure on Teheran-ro near Gangnam Station?",
    "s3": "How would increasing the EV ratio affect air quality near Gangnam Station?",
    "s4": "Post-event at Gangnam Station — find where congestion builds and how to clear it faster",
}

# AgentSUMO MCP server tool descriptions (for MCP metrics)
AGENTSUMO_TOOLS = [
    {"name": "net_generate", "description": "Generate SUMO road network from OSM data around a location"},
    {"name": "trip_generate", "description": "Generate vehicle trips/routes for SUMO simulation"},
    {"name": "sumo_runner", "description": "Run SUMO traffic simulation with given network and routes"},
    {"name": "xml_to_sqlite_tool", "description": "Convert SUMO XML output files to SQLite database"},
    {"name": "speed_limit_edit_tool", "description": "Modify speed limits on specific roads in the network"},
    {"name": "reduce_lanes_tool", "description": "Reduce number of lanes on specific roads"},
    {"name": "edge_edit_tool", "description": "Edit edge properties in the network"},
    {"name": "vehicle_type_edit_tool", "description": "Edit vehicle type distribution (e.g., EV ratio)"},
    {"name": "vehicle_generation_tool", "description": "Generate vehicles with specific properties"},
    {"name": "tls_adaptation_tool", "description": "Apply Webster-based traffic light signal adaptation"},
    {"name": "tls_offset_tool", "description": "Apply Green Wave traffic light offset optimization"},
    {"name": "read_query", "description": "Execute SQL query on the analysis SQLite database"},
    {"name": "list_tables", "description": "List all tables in the SQLite database"},
    {"name": "describe_table", "description": "Show schema of a specific table"},
    {"name": "get_road_names_tool", "description": "Get road names from edge IDs in the network"},
    {"name": "get_edge_ids_from_road_name_tool", "description": "Get edge IDs for a given road name"},
    {"name": "analyze_road_details_tool", "description": "Analyze detailed properties of a road segment"},
    {"name": "db_based_simulation_report_tool", "description": "Generate simulation comparison report from DB"},
    {"name": "simulation_qa_tool", "description": "Answer questions about simulation results"},
]


# ═══════════════════════════════════════════════════════════════════════
# Part 1: Direct Metrics
# ═══════════════════════════════════════════════════════════════════════

def load_experiment_log(scenario, condition, iteration):
    path = RESULTS_DIR / scenario / condition / f"iteration{iteration}" / "experiment_log.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_conversation_history(scenario, condition, iteration):
    path = RESULTS_DIR / scenario / condition / f"iteration{iteration}" / "conversation_history.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def evaluate_direct_metrics(iterations):
    """Evaluate direct metrics from experiment logs."""
    print("\n" + "=" * 90)
    print("  DIRECT METRICS")
    print("=" * 90)

    # Collect all data first
    data = {}  # data[scenario][condition][iteration] = {...}
    for scenario in SCENARIOS:
        data[scenario] = {}
        for condition in CONDITIONS:
            data[scenario][condition] = {}
            for i in iterations:
                log = load_experiment_log(scenario, condition, i)
                if log is None:
                    continue
                s = log["summary"]
                m = log["metadata"]
                data[scenario][condition][i] = {
                    "turns": s.get("user_turns", s.get("interaction_turns", 0)),
                    "tokens": s["total_tokens"],
                    "tool_calls": s["total_tool_calls"],
                    "tool_sequence": s.get("tool_sequence", list(s.get("tool_call_breakdown", {}).keys())),
                    "parameters": s.get("parameters_used", {}),
                    "duration": m["session_duration_seconds"],
                }

    # ── Per-scenario, per-iteration detail ──
    for scenario in SCENARIOS:
        print(f"\n{'─' * 90}")
        print(f"  {scenario}: {SCENARIO_DESCRIPTIONS[scenario]}")
        print(f"{'─' * 90}")

        # Iteration-level table
        iter_list = sorted(set(list(data[scenario].get("full", {}).keys()) + list(data[scenario].get("no_ipp", {}).keys())))
        if not iter_list:
            print("  No data")
            continue

        print(f"\n  {'iter':<6}", end="")
        for metric_name in ["turns", "tokens", "tool_calls", "duration"]:
            print(f" {'full_'+metric_name:>16} {'noipp_'+metric_name:>16}", end="")
        print()
        print(f"  {'─' * 134}")

        for i in iter_list:
            print(f"  {i:<6}", end="")
            for metric_name in ["turns", "tokens", "tool_calls", "duration"]:
                full_val = data[scenario].get("full", {}).get(i, {}).get(metric_name)
                noipp_val = data[scenario].get("no_ipp", {}).get(i, {}).get(metric_name)
                fmt = '.1f' if metric_name == 'duration' else '.0f'
                full_str = f"{full_val:{fmt}}" if full_val is not None else "—"
                noipp_str = f"{noipp_val:{fmt}}" if noipp_val is not None else "—"
                print(f" {full_str:>16} {noipp_str:>16}", end="")
            print()

        # Summary row
        print(f"  {'avg':<6}", end="")
        for metric_name in ["turns", "tokens", "tool_calls", "duration"]:
            for cond in ["full", "no_ipp"]:
                vals = [data[scenario][cond][i][metric_name] for i in iter_list if i in data[scenario].get(cond, {})]
                fmt = '.1f' if metric_name == 'duration' else '.0f'
                avg_str = f"{sum(vals)/len(vals):{fmt}}" if vals else "—"
                print(f" {avg_str:>16}", end="")
        print()

        # Parameter comparison table
        print(f"\n  Parameters per iteration:")
        all_keys = set()
        for cond in CONDITIONS:
            for i in iter_list:
                params = data[scenario].get(cond, {}).get(i, {}).get("parameters", {})
                all_keys.update(params.keys())

        for key in sorted(all_keys):
            print(f"    {key}:")
            for cond in CONDITIONS:
                vals = []
                for i in iter_list:
                    v = data[scenario].get(cond, {}).get(i, {}).get("parameters", {}).get(key)
                    vals.append(str(v) if v is not None else "—")
                unique = set(v for v in vals if v != "—")
                consistency = f"consistent" if len(unique) <= 1 else f"VARIES ({len(unique)} unique)"
                print(f"      {cond:>8}: {vals}  [{consistency}]")

        # Parameter consistency score
        print(f"\n  Parameter consistency score:")
        for cond in CONDITIONS:
            scores = []
            for key in sorted(all_keys):
                vals = [str(data[scenario].get(cond, {}).get(i, {}).get("parameters", {}).get(key)) for i in iter_list if i in data[scenario].get(cond, {})]
                vals = [v for v in vals if v != "None"]
                if vals:
                    unique = set(vals)
                    scores.append(1.0 / len(unique))  # 1.0 if all same, 0.5 if 2 unique, etc.
            avg_score = sum(scores) / len(scores) if scores else 0
            print(f"    {cond:>8}: {avg_score:.2f}")

        # Tool sequence comparison
        print(f"\n  Tool sequence consistency:")
        for cond in CONDITIONS:
            seqs = []
            for i in iter_list:
                seq = data[scenario].get(cond, {}).get(i, {}).get("tool_sequence", [])
                seqs.append(" → ".join(seq))
            unique_seqs = set(seqs)
            if seqs:
                most_common = max(unique_seqs, key=lambda s: seqs.count(s))
                most_common_ratio = seqs.count(most_common) / len(seqs)
            else:
                most_common_ratio = 0
            print(f"    {cond:>8}: {len(unique_seqs)} unique out of {len(seqs)}  (most common: {most_common_ratio:.0%})")

        # Clarification rate
        print(f"\n  Clarification rate (turns > 1):")
        for cond in CONDITIONS:
            turns = [data[scenario].get(cond, {}).get(i, {}).get("turns", 0) for i in iter_list if i in data[scenario].get(cond, {})]
            clarified = sum(1 for t in turns if t > 1)
            rate = clarified / len(turns) if turns else 0
            print(f"    {cond:>8}: {clarified}/{len(turns)} ({rate:.0%})")

    # ── Overall Aggregate ──
    print(f"\n{'=' * 90}")
    print(f"  OVERALL AGGREGATE")
    print(f"{'=' * 90}")
    print(f"\n  {'Metric':<25} {'full':>20} {'no_ipp':>20} {'delta':>15}")
    print(f"  {'─' * 80}")

    for metric_name in ["turns", "tokens", "tool_calls", "duration"]:
        for label, cond in [("full", "full"), ("no_ipp", "no_ipp")]:
            pass
        full_vals = [data[s]["full"][i][metric_name] for s in SCENARIOS for i in data[s].get("full", {})]
        noipp_vals = [data[s]["no_ipp"][i][metric_name] for s in SCENARIOS for i in data[s].get("no_ipp", {})]
        fmt = '.1f' if metric_name == 'duration' else '.0f'
        full_avg = sum(full_vals) / len(full_vals) if full_vals else None
        noipp_avg = sum(noipp_vals) / len(noipp_vals) if noipp_vals else None
        full_str = _stats(full_vals, fmt=fmt) if full_vals else "N/A"
        noipp_str = _stats(noipp_vals, fmt=fmt) if noipp_vals else "N/A"
        if full_avg is not None and noipp_avg is not None:
            delta_str = f"{full_avg - noipp_avg:+{fmt}}"
        else:
            delta_str = "—"
        print(f"  {metric_name:<25} {full_str:>20} {noipp_str:>20} {delta_str:>15}")

    # Clarification rate aggregate
    full_turns_all = [data[s]["full"][i]["turns"] for s in SCENARIOS for i in data[s].get("full", {})]
    noipp_turns_all = [data[s]["no_ipp"][i]["turns"] for s in SCENARIOS for i in data[s].get("no_ipp", {})]
    full_clar = sum(1 for t in full_turns_all if t > 1)
    noipp_clar = sum(1 for t in noipp_turns_all if t > 1)
    full_rate = full_clar / len(full_turns_all) if full_turns_all else 0
    noipp_rate = noipp_clar / len(noipp_turns_all) if noipp_turns_all else 0
    print(f"  {'clarification_rate':<25} {f'{full_clar}/{len(full_turns_all)} ({full_rate:.0%})':>20} {f'{noipp_clar}/{len(noipp_turns_all)} ({noipp_rate:.0%})':>20} {f'{full_rate - noipp_rate:+.0%}':>15}")

    # Parameter consistency aggregate
    full_consistency = []
    noipp_consistency = []
    for scenario in SCENARIOS:
        all_keys = set()
        for cond in CONDITIONS:
            for i in iterations:
                params = data[scenario].get(cond, {}).get(i, {}).get("parameters", {})
                all_keys.update(params.keys())
        for cond, store in [("full", full_consistency), ("no_ipp", noipp_consistency)]:
            for key in all_keys:
                vals = [str(data[scenario].get(cond, {}).get(i, {}).get("parameters", {}).get(key)) for i in iterations if i in data[scenario].get(cond, {})]
                vals = [v for v in vals if v != "None"]
                if vals:
                    store.append(1.0 / len(set(vals)))
    full_con = sum(full_consistency) / len(full_consistency) if full_consistency else 0
    noipp_con = sum(noipp_consistency) / len(noipp_consistency) if noipp_consistency else 0
    print(f"  {'param_consistency':<25} {full_con:>20.2f} {noipp_con:>20.2f} {full_con - noipp_con:>+15.2f}")

    # Return structured results
    return_data = {"per_scenario": data, "aggregate": {}}
    for metric_name in ["turns", "tokens", "tool_calls", "duration"]:
        return_data["aggregate"][metric_name] = {}
        for cond in CONDITIONS:
            vals = [data[s][cond][i][metric_name] for s in SCENARIOS for i in data[s].get(cond, {})]
            return_data["aggregate"][metric_name][cond] = {
                "values": vals,
                "avg": sum(vals) / len(vals) if vals else None,
            }
    return_data["aggregate"]["clarification_rate"] = {"full": full_rate, "no_ipp": noipp_rate}
    return_data["aggregate"]["param_consistency"] = {"full": full_con, "no_ipp": noipp_con}
    return return_data


def _stats(values, fmt='.0f'):
    if not values:
        return "N/A"
    avg = sum(values) / len(values)
    if len(values) > 1:
        var = sum((v - avg) ** 2 for v in values) / len(values)
        std = var ** 0.5
        return f"{avg:{fmt}} ± {std:{fmt}}"
    return f"{avg:{fmt}}"


# ═══════════════════════════════════════════════════════════════════════
# Part 2: DeepEval Metrics
# ═══════════════════════════════════════════════════════════════════════

def evaluate_deepeval_metrics(iterations):
    """Evaluate using DeepEval LLM-as-judge metrics."""

    # Load OpenAI key
    openai_key_file = PROJECT_ROOT / "openai_api.txt"
    if openai_key_file.exists():
        with open(openai_key_file) as f:
            os.environ["OPENAI_API_KEY"] = f.read().strip()

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found. Required for DeepEval.")
        return

    from deepeval.test_case import (
        ConversationalTestCase, LLMTestCase, ToolCall, Turn,
    )
    from deepeval.metrics import (
        ConversationCompletenessMetric,
        GEval,
        ArgumentCorrectnessMetric,
    )
    from deepeval.test_case import LLMTestCaseParams

    # Optional metrics
    try:
        from deepeval.metrics import GoalAccuracyMetric
        HAS_GOAL_ACCURACY = True
    except ImportError:
        HAS_GOAL_ACCURACY = False

    # MCP metrics
    try:
        from deepeval.test_case import MCPServer, MCPToolCall
        from deepeval.metrics import MCPUseMetric
        HAS_MCP_USE = True
    except ImportError:
        HAS_MCP_USE = False

    try:
        from deepeval.metrics import MCPTaskCompletionMetric
        HAS_MCP_TASK = True
    except ImportError:
        HAS_MCP_TASK = False

    try:
        from deepeval.metrics import MultiTurnMCPUseMetric
        HAS_MULTI_MCP = True
    except ImportError:
        HAS_MULTI_MCP = False

    print("\n" + "=" * 90)
    print("  DEEPEVAL METRICS")
    print("=" * 90)

    all_scores = defaultdict(lambda: defaultdict(list))
    per_scenario_scores = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    DELAY = 5  # seconds between API calls to avoid rate limit

    for scenario in SCENARIOS:
        for condition in CONDITIONS:
            for i in iterations:
                hist = load_conversation_history(scenario, condition, i)
                log = load_experiment_log(scenario, condition, i)
                if hist is None or log is None:
                    continue

                print(f"\n  [{scenario}/{condition}/iter{i}]")

                # Build data
                turns = _build_turns(hist)
                user_input, final_output, _ = _extract_test_case_data(hist)
                full_conversation = _build_full_conversation_text(hist)
                tools_with_args = _extract_tools_with_args(hist)

                # ── 1. ConversationCompleteness (sees full turns) ──
                try:
                    metric = ConversationCompletenessMetric(threshold=0.5)
                    convo_test = ConversationalTestCase(turns=turns)
                    metric.measure(convo_test)
                    print(f"    ConversationCompleteness: {metric.score:.2f} — {metric.reason[:100]}")
                    all_scores[condition]["ConversationCompleteness"].append(metric.score)
                    per_scenario_scores[scenario][condition]["ConversationCompleteness"].append(metric.score)
                except Exception as e:
                    print(f"    ConversationCompleteness: ERROR — {e}")
                time.sleep(DELAY)

                # ── 2. ArgumentCorrectness (sees tool calls with args) ──
                try:
                    test_case = LLMTestCase(
                        input=user_input,
                        actual_output=final_output,
                        tools_called=tools_with_args,
                    )
                    metric = ArgumentCorrectnessMetric(threshold=0.5)
                    metric.measure(test_case)
                    print(f"    ArgumentCorrectness: {metric.score:.2f} — {metric.reason[:100]}")
                    all_scores[condition]["ArgumentCorrectness"].append(metric.score)
                    per_scenario_scores[scenario][condition]["ArgumentCorrectness"].append(metric.score)
                except Exception as e:
                    print(f"    ArgumentCorrectness: ERROR — {e}")
                time.sleep(DELAY)

                # ── 3. G-Eval DesignQuality (sees full conversation) ──
                try:
                    geval = GEval(
                        name="SimulationDesignQuality",
                        evaluation_steps=[
                            "Check if the final simulation scenario accurately reflects the user's original intent",
                            "Check if the agent completed the task efficiently without redundant or unnecessary steps",
                            "Check if the agent chose appropriate simulation parameters (radius, traffic condition, duration) for the given scenario",
                        ],
                        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                        threshold=0.5,
                    )
                    test_case = LLMTestCase(input=user_input, actual_output=full_conversation)
                    geval.measure(test_case)
                    print(f"    G-Eval (DesignQuality): {geval.score:.2f} — {geval.reason[:100]}")
                    all_scores[condition]["G-Eval-Design"].append(geval.score)
                    per_scenario_scores[scenario][condition]["G-Eval-Design"].append(geval.score)
                except Exception as e:
                    print(f"    G-Eval (DesignQuality): ERROR — {e}")
                time.sleep(DELAY)

                # ── 4. G-Eval ProcessQuality (sees full conversation) ──
                try:
                    geval2 = GEval(
                        name="PlanningProcessQuality",
                        evaluation_steps=[
                            "Check if the agent presented an execution plan before calling any tools",
                            "Check if the agent asked the user about missing or ambiguous parameters",
                            "Check if the agent waited for user confirmation before proceeding with execution",
                            "Check if the agent engaged interactively with the user rather than making unilateral decisions",
                        ],
                        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                        threshold=0.5,
                    )
                    test_case = LLMTestCase(input=user_input, actual_output=full_conversation)
                    geval2.measure(test_case)
                    print(f"    G-Eval (ProcessQuality): {geval2.score:.2f} — {geval2.reason[:100]}")
                    all_scores[condition]["G-Eval-Process"].append(geval2.score)
                    per_scenario_scores[scenario][condition]["G-Eval-Process"].append(geval2.score)
                except Exception as e:
                    print(f"    G-Eval (ProcessQuality): ERROR — {e}")
                time.sleep(DELAY)

                # ── 5. GoalAccuracy (sees full turns) ──
                if HAS_GOAL_ACCURACY:
                    try:
                        metric = GoalAccuracyMetric(threshold=0.5)
                        convo_test = ConversationalTestCase(turns=turns)
                        metric.measure(convo_test)
                        print(f"    GoalAccuracy: {metric.score:.2f} — {metric.reason[:100]}")
                        all_scores[condition]["GoalAccuracy"].append(metric.score)
                        per_scenario_scores[scenario][condition]["GoalAccuracy"].append(metric.score)
                    except Exception as e:
                        print(f"    GoalAccuracy: ERROR — {e}")
                    time.sleep(DELAY)

                # ── 6. MCPUse (sees MCP tool calls with args and results) ──
                if HAS_MCP_USE:
                    try:
                        mcp_server, mcp_tools = _build_mcp_data(hist)
                        test_case = LLMTestCase(
                            input=user_input,
                            actual_output=final_output,
                            mcp_servers=[mcp_server],
                            mcp_tools_called=mcp_tools,
                        )
                        metric = MCPUseMetric(threshold=0.5)
                        metric.measure(test_case)
                        print(f"    MCPUse: {metric.score:.2f} — {metric.reason[:100]}")
                        all_scores[condition]["MCPUse"].append(metric.score)
                        per_scenario_scores[scenario][condition]["MCPUse"].append(metric.score)
                    except Exception as e:
                        print(f"    MCPUse: ERROR — {e}")
                    time.sleep(DELAY)

                # ── 7. MCPTaskCompletion (sees full turns + MCP data) ──
                if HAS_MCP_TASK:
                    try:
                        mcp_server, _ = _build_mcp_data(hist)
                        mcp_turns = _build_mcp_turns(hist)
                        convo_test = ConversationalTestCase(
                            turns=mcp_turns,
                            mcp_servers=[mcp_server],
                        )
                        metric = MCPTaskCompletionMetric(threshold=0.5)
                        metric.measure(convo_test)
                        print(f"    MCPTaskCompletion: {metric.score:.2f} — {metric.reason[:100]}")
                        all_scores[condition]["MCPTaskCompletion"].append(metric.score)
                        per_scenario_scores[scenario][condition]["MCPTaskCompletion"].append(metric.score)
                    except Exception as e:
                        print(f"    MCPTaskCompletion: ERROR — {e}")
                    time.sleep(DELAY)

                # ── 8. MultiTurnMCPUse (sees full turns + MCP data) ──
                if HAS_MULTI_MCP:
                    try:
                        mcp_server, _ = _build_mcp_data(hist)
                        mcp_turns = _build_mcp_turns(hist)
                        convo_test = ConversationalTestCase(
                            turns=mcp_turns,
                            mcp_servers=[mcp_server],
                        )
                        metric = MultiTurnMCPUseMetric(threshold=0.5)
                        metric.measure(convo_test)
                        print(f"    MultiTurnMCPUse: {metric.score:.2f} — {metric.reason[:100]}")
                        all_scores[condition]["MultiTurnMCPUse"].append(metric.score)
                        per_scenario_scores[scenario][condition]["MultiTurnMCPUse"].append(metric.score)
                    except Exception as e:
                        print(f"    MultiTurnMCPUse: ERROR — {e}")
                    time.sleep(DELAY)

    # ── Aggregate ──
    print(f"\n{'=' * 90}")
    print(f"  DEEPEVAL AGGREGATE")
    print(f"{'=' * 90}")
    print(f"\n{'Metric':<30} {'full':>15} {'no_ipp':>15} {'delta':>10}")
    print(f"{'─' * 72}")

    all_metric_names = set()
    for cond in CONDITIONS:
        all_metric_names.update(all_scores[cond].keys())

    for metric_name in sorted(all_metric_names):
        full_scores = all_scores["full"].get(metric_name, [])
        noipp_scores = all_scores["no_ipp"].get(metric_name, [])

        full_avg = sum(full_scores) / len(full_scores) if full_scores else None
        noipp_avg = sum(noipp_scores) / len(noipp_scores) if noipp_scores else None

        full_str = f"{full_avg:.2f}" if full_avg is not None else "N/A"
        noipp_str = f"{noipp_avg:.2f}" if noipp_avg is not None else "N/A"

        if full_avg is not None and noipp_avg is not None:
            delta = full_avg - noipp_avg
            delta_str = f"{delta:+.2f}"
        else:
            delta_str = "—"

        print(f"  {metric_name:<28} {full_str:>15} {noipp_str:>15} {delta_str:>10}")

    # ── Per-scenario breakdown ──
    print(f"\n{'=' * 90}")
    print(f"  DEEPEVAL PER-SCENARIO BREAKDOWN")
    print(f"{'=' * 90}")

    for scenario in SCENARIOS:
        print(f"\n  {scenario}: {SCENARIO_DESCRIPTIONS[scenario]}")
        print(f"  {'Metric':<28} {'full':>15} {'no_ipp':>15} {'delta':>10}")
        print(f"  {'─' * 70}")
        for metric_name in sorted(all_metric_names):
            full_s = per_scenario_scores[scenario]["full"].get(metric_name, [])
            noipp_s = per_scenario_scores[scenario]["no_ipp"].get(metric_name, [])
            full_avg = sum(full_s) / len(full_s) if full_s else None
            noipp_avg = sum(noipp_s) / len(noipp_s) if noipp_s else None
            full_str = f"{full_avg:.2f}" if full_avg is not None else "N/A"
            noipp_str = f"{noipp_avg:.2f}" if noipp_avg is not None else "N/A"
            if full_avg is not None and noipp_avg is not None:
                delta_str = f"{full_avg - noipp_avg:+.2f}"
            else:
                delta_str = "—"
            print(f"  {metric_name:<28} {full_str:>15} {noipp_str:>15} {delta_str:>10}")

    # Return structured results
    return_data = {
        "aggregate": {},
        "per_scenario": {},
    }
    for condition in CONDITIONS:
        return_data["aggregate"][condition] = {}
        for metric_name in sorted(all_metric_names):
            scores = all_scores[condition].get(metric_name, [])
            return_data["aggregate"][condition][metric_name] = {
                "scores": scores,
                "avg": sum(scores) / len(scores) if scores else None,
            }
    for scenario in SCENARIOS:
        return_data["per_scenario"][scenario] = {}
        for condition in CONDITIONS:
            return_data["per_scenario"][scenario][condition] = {}
            for metric_name in sorted(all_metric_names):
                scores = per_scenario_scores[scenario][condition].get(metric_name, [])
                return_data["per_scenario"][scenario][condition][metric_name] = {
                    "scores": scores,
                    "avg": sum(scores) / len(scores) if scores else None,
                }
    return return_data


# ── DeepEval Helpers ──────────────────────────────────────────────────

def _build_turns(hist):
    """Convert conversation_history to DeepEval Turn objects."""
    from deepeval.test_case import Turn
    turns = []
    for msg in hist:
        role = msg["role"]
        content = msg.get("content", "")

        if isinstance(content, str):
            if role == "user" and "---\n\n" in content:
                text = content.split("---\n\n")[-1].strip()
            else:
                text = content[:3000]
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        text_parts.append(f"[Called tool: {block['name']}({json.dumps(block.get('input', {}), ensure_ascii=False)[:200]})]")
                    elif block.get("type") == "tool_result":
                        result_content = block.get("content", "")
                        if isinstance(result_content, str):
                            text_parts.append(f"[Tool result: {result_content[:200]}]")
                        else:
                            text_parts.append("[Tool result received]")
                    elif block.get("type") == "thinking":
                        pass  # Skip thinking blocks
            text = "\n".join(text_parts) if text_parts else ""
        else:
            text = str(content)[:1000] if content else ""

        if text.strip():
            turns.append(Turn(role=role, content=text[:3000]))

    return turns


def _build_full_conversation_text(hist):
    """Build full conversation as a single string for G-Eval."""
    parts = []
    for msg in hist:
        role = msg["role"].upper()
        content = msg.get("content", "")

        if isinstance(content, str):
            if role == "USER" and "---\n\n" in content:
                text = content.split("---\n\n")[-1].strip()
            else:
                text = content[:2000]
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        text_parts.append(f"[Called tool: {block['name']}]")
            text = "\n".join(text_parts) if text_parts else ""
        else:
            text = str(content)[:1000] if content else ""

        if text.strip():
            parts.append(f"[{role}]: {text[:2000]}")

    return "\n\n".join(parts)


def _extract_test_case_data(hist):
    """Extract input, final output, and tool call names from conversation history."""
    user_input = ""
    final_output = ""
    tools_called = []

    for msg in hist:
        role = msg["role"]
        content = msg.get("content", "")

        if role == "user" and not user_input:
            if isinstance(content, str):
                if "---\n\n" in content:
                    user_input = content.split("---\n\n")[-1].strip()
                else:
                    user_input = content

        if role == "assistant" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools_called.append(block["name"])
                if isinstance(block, dict) and block.get("type") == "text":
                    final_output = block["text"]

    return user_input, final_output, tools_called


def _extract_tools_with_args(hist):
    """Extract ToolCall objects with input parameters."""
    from deepeval.test_case import ToolCall
    tools = []
    for msg in hist:
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tools.append(ToolCall(
                            name=block["name"],
                            input_parameters=block.get("input", {}),
                        ))
    return tools


def _build_mcp_data(hist):
    """Build MCPServer and MCPToolCall objects from conversation history."""
    from deepeval.test_case import MCPServer, MCPToolCall
    from mcp.types import Tool as MCPTool, CallToolResult, TextContent

    # Build MCP server with mcp.types.Tool objects
    mcp_server = MCPServer(
        server_name="AgentSUMO",
        available_tools=[
            MCPTool(
                name=t["name"],
                description=t["description"],
                inputSchema={"type": "object", "properties": {}},
            )
            for t in AGENTSUMO_TOOLS
        ],
    )

    # Extract tool calls with args and results
    mcp_tools = []
    # Match tool_use blocks with subsequent tool_result blocks
    pending_tool = None
    for msg in hist:
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        pending_tool = {
                            "name": block["name"],
                            "args": block.get("input", {}),
                        }
                    elif block.get("type") == "tool_result" and pending_tool:
                        result_content = block.get("content", "")
                        if isinstance(result_content, str):
                            result_str = result_content[:500]
                        else:
                            result_str = json.dumps(result_content, ensure_ascii=False)[:500]
                        mcp_tools.append(MCPToolCall(
                            name=pending_tool["name"],
                            args=pending_tool["args"],
                            result=CallToolResult(
                                content=[TextContent(type="text", text=result_str)]
                            ),
                        ))
                        pending_tool = None

    return mcp_server, mcp_tools


def _build_mcp_turns(hist):
    """Build Turn objects with mcp_tools_called for multi-turn MCP metrics."""
    from deepeval.test_case import Turn, MCPToolCall
    from mcp.types import CallToolResult, TextContent

    turns = []
    for msg in hist:
        role = msg["role"]
        content = msg.get("content", "")
        mcp_tools_in_turn = []

        if isinstance(content, str):
            if role == "user" and "---\n\n" in content:
                text = content.split("---\n\n")[-1].strip()
            else:
                text = content[:3000]
        elif isinstance(content, list):
            text_parts = []
            pending_tool = None
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        pending_tool = {
                            "name": block["name"],
                            "args": block.get("input", {}),
                        }
                        text_parts.append(f"[Called tool: {block['name']}]")
                    elif block.get("type") == "tool_result" and pending_tool:
                        result_content = block.get("content", "")
                        result_str = result_content[:500] if isinstance(result_content, str) else json.dumps(result_content, ensure_ascii=False)[:500]
                        mcp_tools_in_turn.append(MCPToolCall(
                            name=pending_tool["name"],
                            args=pending_tool["args"],
                            result=CallToolResult(
                                content=[TextContent(type="text", text=result_str)]
                            ),
                        ))
                        pending_tool = None
                        text_parts.append("[Tool result received]")
                    elif block.get("type") == "thinking":
                        pass
            text = "\n".join(text_parts) if text_parts else ""
        else:
            text = str(content)[:1000] if content else ""

        if text.strip():
            turn_kwargs = {"role": role, "content": text[:3000]}
            if mcp_tools_in_turn:
                turn_kwargs["mcp_tools_called"] = mcp_tools_in_turn
            turns.append(Turn(**turn_kwargs))

    return turns


# ═══════════════════════════════════════��═══════════════════════════════
# Main
# ═════════════════════════════════��═════════════════════════════════════

def _save_results(direct_results=None, deepeval_results=None):
    """Save evaluation results to JSON."""
    from datetime import datetime
    output_dir = RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "scenarios": list(SCENARIO_DESCRIPTIONS.keys()),
        "conditions": CONDITIONS,
    }

    if direct_results is not None:
        results["direct_metrics"] = direct_results
    if deepeval_results is not None:
        results["deepeval_metrics"] = deepeval_results

    output_path = output_dir / "evaluation_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="IPP Ablation Evaluation")
    parser.add_argument(
        "--mode", choices=["direct", "deepeval", "all"], default="all",
        help="Evaluation mode"
    )
    parser.add_argument(
        "--iterations", type=int, default=5,
        help="Number of iterations to evaluate (default: 5)"
    )
    args = parser.parse_args()

    iters = range(1, args.iterations + 1)

    direct_results = None
    deepeval_results = None

    if args.mode in ("direct", "all"):
        direct_results = evaluate_direct_metrics(iters)

    if args.mode in ("deepeval", "all"):
        deepeval_results = evaluate_deepeval_metrics(iters)

    _save_results(direct_results, deepeval_results)


if __name__ == "__main__":
    main()