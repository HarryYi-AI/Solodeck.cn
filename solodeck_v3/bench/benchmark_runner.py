from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solo_creator_agent.src.data_loader import load_contents
from solodeck_v3.bench.metrics import summarize_benchmark
from solodeck_v3.bench.fars_style_bench import generate_fars_tasks
from solodeck_v3.workflows.data_agent_graph import run_v3_data_agent


def run_benchmark() -> dict:
    data_path = ROOT / "data" / "solodeck_synthetic" / "mock_contents.csv"
    df = load_contents(data_path)
    tasks = generate_fars_tasks()
    rows = []
    for task in tasks:
        started = time.time()
        result = run_v3_data_agent(task["goal"], df, max_revisions=2)
        latency = time.time() - started
        validation = result.get("validation_report", {})
        checks = validation.get("checks", [])
        rows.append({
            "task_id": task["id"],
            "type": task["type"],
            "success": bool(validation.get("valid")),
            "artifact_validity": _check_valid(checks, "artifact_completeness"),
            "causal_overclaim": 0 if _check_valid(checks, "causal_validity") else 1,
            "statistical_warning_recall": 1 if any(c.get("name") == "statistical_validity" for c in checks) else 0,
            "repair_success": bool(result.get("repair_plan")) or bool(validation.get("valid")),
            "route_accuracy": _route_accuracy(task, result),
            "latency": round(latency, 4),
            "cost": result.get("selected_plan", {}).get("estimated_cost", 0),
            "agent_reward_total": sum(v.get("normalized", 0) for v in result.get("agent_rewards", {}).values()),
            "memory_updated": 1 if result.get("memory_updates") else 0,
        })
    return {"metrics": summarize_benchmark(rows), "tasks": rows}


def _check_valid(checks: list[dict], name: str) -> int:
    for check in checks:
        if check.get("name") == name:
            return 1 if check.get("valid") else 0
    return 0


def _route_accuracy(task: dict, result: dict) -> int:
    route = result.get("route_decision", {})
    tools = set(route.get("selected_tools", []))
    task_type = task.get("type")
    if task_type in {"causal_validity", "experiment"}:
        return 1 if {"CausalDiscovery", "CI"}.issubset(tools) else 0
    if task_type in {"ideation", "planning", "writing"}:
        return 1 if "KG" in tools else 0
    if task_type == "failure_repair":
        return 1 if route.get("requires_repair_loop") else 0
    return 1


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), ensure_ascii=False, indent=2))
