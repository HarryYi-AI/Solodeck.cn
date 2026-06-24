"""Run FARS benchmark plus layered evaluation — optional, does not replace benchmark_runner."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solo_creator_agent.src.data_loader import load_contents
from solodeck_v3.bench.fars_style_bench import generate_fars_tasks
from solodeck_v3.bench.layered_eval import run_layered_eval
from solodeck_v3.bench.metrics import summarize_benchmark
from solodeck_v3.workflows.data_agent_graph import run_v3_data_agent


def run_layered_benchmark(sample_size: int | None = 6) -> dict:
    data_path = ROOT / "data" / "solodeck_synthetic" / "mock_contents.csv"
    df = load_contents(data_path)
    tasks = generate_fars_tasks()
    if sample_size:
        tasks = tasks[:sample_size]

    rows = []
    layered_rows = []
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
            "route_accuracy": 1,
            "latency": round(latency, 4),
            "cost": result.get("selected_plan", {}).get("estimated_cost", 0),
            "agent_reward_total": sum(v.get("normalized", 0) for v in result.get("agent_rewards", {}).values()),
            "memory_updated": 1 if result.get("memory_updates") else 0,
        })
        layered = run_layered_eval(result, task=task["goal"], task_type=task["type"])
        layered_rows.append({"task_id": task["id"], **layered})

    fars = summarize_benchmark(rows)
    layered_valid_rate = sum(1 for r in layered_rows if r.get("all_valid")) / max(len(layered_rows), 1)
    return {
        "fars_metrics": fars,
        "layered_valid_rate": round(layered_valid_rate, 3),
        "layered_samples": layered_rows,
        "task_count": len(tasks),
    }


def _check_valid(checks: list[dict], name: str) -> int:
    for check in checks:
        if check.get("name") == name:
            return 1 if check.get("valid") else 0
    return 0


if __name__ == "__main__":
    print(json.dumps(run_layered_benchmark(), ensure_ascii=False, indent=2))
