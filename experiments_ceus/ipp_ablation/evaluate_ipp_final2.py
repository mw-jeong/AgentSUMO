#!/usr/bin/env python3
"""
IPP Ablation — Final Evaluation Script

1. Direct metrics: turns, tokens, tool calls, duration, clarification rate,
   parameter consistency, tool sequence consistency, per-iteration details
2. Conversational G-Eval x3: SimulationQuality, PlanningQuality, InteractiveEngagement

Usage:
    python -m experiments_ceus.ipp_ablation.evaluate_ipp_final2 --mode direct
    python -m experiments_ceus.ipp_ablation.evaluate_ipp_final2 --mode geval --iterations 1
    python -m experiments_ceus.ipp_ablation.evaluate_ipp_final2 --mode all --iterations 5
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


# ═══════════════════════════════════════════════════════════════════════
# Helpers
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
# Part 1: Direct Metrics
# ═══════════════════════════════════════════════════════════════════════

def evaluate_direct_metrics(iterations):
    """Evaluate direct metrics from experiment logs."""
    print("\n" + "=" * 90)
    print("  DIRECT METRICS")
    print("=" * 90)

    # Collect all data
    data = {}
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

    # ── Per-scenario detail ──
    for scenario in SCENARIOS:
        print(f"\n{'─' * 90}")
        print(f"  {scenario}: {SCENARIO_DESCRIPTIONS[scenario]}")
        print(f"{'─' * 90}")

        iter_list = sorted(set(
            list(data[scenario].get("full", {}).keys()) +
            list(data[scenario].get("no_ipp", {}).keys())
        ))
        if not iter_list:
            print("  No data")
            continue

        # Iteration-level table
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

        # Parameter comparison
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
                consistency = "consistent" if len(unique) <= 1 else f"VARIES ({len(unique)} unique)"
                print(f"      {cond:>8}: {vals}  [{consistency}]")

        # Parameter consistency score
        print(f"\n  Parameter consistency score:")
        for cond in CONDITIONS:
            scores = []
            for key in sorted(all_keys):
                vals = [str(data[scenario].get(cond, {}).get(i, {}).get("parameters", {}).get(key))
                        for i in iter_list if i in data[scenario].get(cond, {})]
                vals = [v for v in vals if v != "None"]
                if vals:
                    scores.append(1.0 / len(set(vals)))
            avg_score = sum(scores) / len(scores) if scores else 0
            print(f"    {cond:>8}: {avg_score:.2f}")

        # Tool sequence consistency
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
            turns = [data[scenario].get(cond, {}).get(i, {}).get("turns", 0)
                     for i in iter_list if i in data[scenario].get(cond, {})]
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
        full_vals = [data[s]["full"][i][metric_name] for s in SCENARIOS for i in data[s].get("full", {})]
        noipp_vals = [data[s]["no_ipp"][i][metric_name] for s in SCENARIOS for i in data[s].get("no_ipp", {})]
        fmt = '.1f' if metric_name == 'duration' else '.0f'
        full_avg = sum(full_vals) / len(full_vals) if full_vals else None
        noipp_avg = sum(noipp_vals) / len(noipp_vals) if noipp_vals else None
        full_str = _stats(full_vals, fmt=fmt) if full_vals else "N/A"
        noipp_str = _stats(noipp_vals, fmt=fmt) if noipp_vals else "N/A"
        delta_str = f"{full_avg - noipp_avg:+{fmt}}" if full_avg and noipp_avg else "—"
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
                vals = [str(data[scenario].get(cond, {}).get(i, {}).get("parameters", {}).get(key))
                        for i in iterations if i in data[scenario].get(cond, {})]
                vals = [v for v in vals if v != "None"]
                if vals:
                    store.append(1.0 / len(set(vals)))
    full_con = sum(full_consistency) / len(full_consistency) if full_consistency else 0
    noipp_con = sum(noipp_consistency) / len(noipp_consistency) if noipp_consistency else 0
    print(f"  {'param_consistency':<25} {full_con:>20.2f} {noipp_con:>20.2f} {full_con - noipp_con:>+15.2f}")

    # Tool sequence consistency aggregate
    full_seq_scores = []
    noipp_seq_scores = []
    for scenario in SCENARIOS:
        for cond, store in [("full", full_seq_scores), ("no_ipp", noipp_seq_scores)]:
            seqs = []
            for i in iterations:
                seq = data[scenario].get(cond, {}).get(i, {}).get("tool_sequence", [])
                if seq:
                    seqs.append(" → ".join(seq))
            if seqs:
                unique = set(seqs)
                most_common = max(unique, key=lambda s: seqs.count(s))
                store.append(seqs.count(most_common) / len(seqs))
    full_seq = sum(full_seq_scores) / len(full_seq_scores) if full_seq_scores else 0
    noipp_seq = sum(noipp_seq_scores) / len(noipp_seq_scores) if noipp_seq_scores else 0
    print(f"  {'tool_seq_consistency':<25} {full_seq:>20.2f} {noipp_seq:>20.2f} {full_seq - noipp_seq:>+15.2f}")

    # Build aggregate numeric metrics
    agg_metrics = {}
    for metric_name in ["turns", "tokens", "tool_calls", "duration"]:
        agg_metrics[metric_name] = {}
        for cond in CONDITIONS:
            vals = [data[s][cond][i][metric_name] for s in SCENARIOS for i in data[s].get(cond, {})]
            agg_metrics[metric_name][cond] = {
                "values": vals,
                "avg": sum(vals) / len(vals) if vals else None,
            }
    agg_metrics["clarification_rate"] = {"full": full_rate, "no_ipp": noipp_rate}
    agg_metrics["param_consistency"] = {"full": full_con, "no_ipp": noipp_con}
    agg_metrics["tool_seq_consistency"] = {"full": full_seq, "no_ipp": noipp_seq}

    return {"per_scenario": data, "aggregate": agg_metrics}


# ═══════════════════════════════════════════════════════════════════════
# Part 2: G-Eval (3 metrics)
# ═══════════════════════════════════════════════════════════════════════

GEVAL_METRICS = {
    "SimulationQuality": [
        "Check if the final simulation scenario accurately reflects the user's original intent",
        "Check if the agent completed the task efficiently without redundant or unnecessary steps",
        "Check if the agent chose appropriate simulation parameters (radius, traffic condition, duration) for the given scenario",
    ],
    "PlanningQuality": [
        "Check if the agent assessed the complexity of the task and adapted its reasoning depth accordingly",
        "Check if the agent asked the user about missing or ambiguous parameters",
        "Check if the agent waited for user confirmation before proceeding with execution",
    ],
    "InteractiveEngagement": [
        "Check if the agent presented an execution plan before calling any tools",
        "Check if the agent collaborated with the user to build the simulation scenario together",
        "Check if the agent incorporated user feedback into its execution",
        "Check if the agent engaged interactively with the user rather than making unilateral decisions",
    ],
}


def evaluate_geval_metrics(iterations):
    """Evaluate using Conversational G-Eval LLM-as-judge metrics."""

    # Load OpenAI key
    openai_key_file = PROJECT_ROOT / "openai_api.txt"
    if openai_key_file.exists():
        with open(openai_key_file) as f:
            os.environ["OPENAI_API_KEY"] = f.read().strip()

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found.")
        return None

    from deepeval.test_case import ConversationalTestCase, Turn
    from deepeval.metrics import ConversationalGEval

    print("\n" + "=" * 90)
    print("  CONVERSATIONAL G-EVAL METRICS")
    print("=" * 90)

    DELAY = 5
    all_scores = defaultdict(lambda: defaultdict(list))
    per_scenario_scores = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for scenario in SCENARIOS:
        for condition in CONDITIONS:
            for i in iterations:
                hist = load_conversation_history(scenario, condition, i)
                if hist is None:
                    continue

                print(f"\n  [{scenario}/{condition}/iter{i}]")

                turns = _build_turns(hist)
                convo_test = ConversationalTestCase(turns=turns)

                for geval_name, steps in GEVAL_METRICS.items():
                    try:
                        metric = ConversationalGEval(
                            name=geval_name,
                            evaluation_steps=steps,
                            threshold=0.5,
                        )
                        metric.measure(convo_test)
                        score = metric.score
                        print(f"    {geval_name}: {score:.2f} — {metric.reason[:100]}")
                        all_scores[condition][geval_name].append(score)
                        per_scenario_scores[scenario][condition][geval_name].append(score)
                    except Exception as e:
                        print(f"    {geval_name}: ERROR — {e}")
                    time.sleep(DELAY)

    # ── Aggregate ──
    print(f"\n{'=' * 90}")
    print(f"  CONVERSATIONAL G-EVAL AGGREGATE")
    print(f"{'=' * 90}")
    print(f"\n  {'Metric':<30} {'full':>15} {'no_ipp':>15} {'delta':>10}")
    print(f"  {'─' * 72}")

    all_metric_names = sorted(set(
        list(all_scores["full"].keys()) + list(all_scores["no_ipp"].keys())
    ))

    for metric_name in all_metric_names:
        full_s = all_scores["full"].get(metric_name, [])
        noipp_s = all_scores["no_ipp"].get(metric_name, [])
        full_avg = sum(full_s) / len(full_s) if full_s else None
        noipp_avg = sum(noipp_s) / len(noipp_s) if noipp_s else None
        full_str = f"{full_avg:.2f}" if full_avg is not None else "N/A"
        noipp_str = f"{noipp_avg:.2f}" if noipp_avg is not None else "N/A"
        delta_str = f"{full_avg - noipp_avg:+.2f}" if full_avg and noipp_avg else "—"
        print(f"  {metric_name:<30} {full_str:>15} {noipp_str:>15} {delta_str:>10}")

    # ── Per-scenario breakdown ──
    print(f"\n{'=' * 90}")
    print(f"  CONVERSATIONAL G-EVAL PER-SCENARIO BREAKDOWN")
    print(f"{'=' * 90}")

    for scenario in SCENARIOS:
        print(f"\n  {scenario}: {SCENARIO_DESCRIPTIONS[scenario]}")
        print(f"  {'Metric':<30} {'full':>15} {'no_ipp':>15} {'delta':>10}")
        print(f"  {'─' * 72}")
        for metric_name in all_metric_names:
            full_s = per_scenario_scores[scenario]["full"].get(metric_name, [])
            noipp_s = per_scenario_scores[scenario]["no_ipp"].get(metric_name, [])
            full_avg = sum(full_s) / len(full_s) if full_s else None
            noipp_avg = sum(noipp_s) / len(noipp_s) if noipp_s else None
            full_str = f"{full_avg:.2f}" if full_avg is not None else "N/A"
            noipp_str = f"{noipp_avg:.2f}" if noipp_avg is not None else "N/A"
            delta_str = f"{full_avg - noipp_avg:+.2f}" if full_avg and noipp_avg else "—"
            print(f"  {metric_name:<30} {full_str:>15} {noipp_str:>15} {delta_str:>10}")

    # Return structured results
    return_data = {
        "aggregate": {},
        "per_scenario": {},
    }
    for condition in CONDITIONS:
        return_data["aggregate"][condition] = {}
        for metric_name in all_metric_names:
            scores = all_scores[condition].get(metric_name, [])
            return_data["aggregate"][condition][metric_name] = {
                "scores": scores,
                "avg": sum(scores) / len(scores) if scores else None,
            }
    for scenario in SCENARIOS:
        return_data["per_scenario"][scenario] = {}
        for condition in CONDITIONS:
            return_data["per_scenario"][scenario][condition] = {}
            for metric_name in all_metric_names:
                scores = per_scenario_scores[scenario][condition].get(metric_name, [])
                return_data["per_scenario"][scenario][condition][metric_name] = {
                    "scores": scores,
                    "avg": sum(scores) / len(scores) if scores else None,
                }
    return return_data


# ── G-Eval Helpers ────────────────────────────────────────────────────

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
                        pass
            text = "\n".join(text_parts) if text_parts else ""
        else:
            text = str(content)[:1000] if content else ""

        if text.strip():
            turns.append(Turn(role=role, content=text[:3000]))

    return turns


def _extract_test_case_data(hist):
    """Extract input, final output, and tool call names."""
    user_input = ""
    final_output = ""
    tools_called = []

    for msg in hist:
        role = msg["role"]
        content = msg.get("content", "")

        if role == "user" and not user_input:
            if isinstance(content, str):
                user_input = content.split("---\n\n")[-1].strip() if "---\n\n" in content else content

        if role == "assistant" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools_called.append(block["name"])
                if isinstance(block, dict) and block.get("type") == "text":
                    final_output = block["text"]

    return user_input, final_output, tools_called


def _build_full_conversation_text(hist):
    """Build full conversation as a single string for G-Eval."""
    parts = []
    for msg in hist:
        role = msg["role"].upper()
        content = msg.get("content", "")

        if isinstance(content, str):
            text = content.split("---\n\n")[-1].strip() if role == "USER" and "---\n\n" in content else content[:2000]
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


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def _save_results(direct_results=None, geval_results=None):
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
    if geval_results is not None:
        results["geval_metrics"] = geval_results

    output_path = output_dir / "evaluation_results_final2.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")


class _Tee:
    """Write to both stdout and a file."""
    def __init__(self, file_path):
        import sys
        self._file = open(file_path, "w", encoding="utf-8")
        self._stdout = sys.stdout
    def write(self, text):
        self._stdout.write(text)
        self._file.write(text)
    def flush(self):
        self._stdout.flush()
        self._file.flush()
    def close(self):
        self._file.close()


def main():
    import sys

    parser = argparse.ArgumentParser(description="IPP Ablation — Final Evaluation")
    parser.add_argument("--mode", choices=["direct", "geval", "all"], default="all")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()

    # Tee stdout to file
    log_path = RESULTS_DIR / "eval_final2.txt"
    tee = _Tee(log_path)
    sys.stdout = tee

    iters = range(1, args.iterations + 1)
    direct_results = None
    geval_results = None

    try:
        if args.mode in ("direct", "all"):
            direct_results = evaluate_direct_metrics(iters)

        if args.mode in ("geval", "all"):
            geval_results = evaluate_geval_metrics(iters)

        _save_results(direct_results, geval_results)
    finally:
        sys.stdout = tee._stdout
        tee.close()
        print(f"  Terminal output saved to: {log_path}")


if __name__ == "__main__":
    main()