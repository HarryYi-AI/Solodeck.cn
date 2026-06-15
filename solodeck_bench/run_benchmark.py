from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solo_creator_agent.src.data_loader import load_contents
from solodeck.workflows.data_agent_graph import run_data_agent_graph


DATA = ROOT / "data" / "solodeck_synthetic" / "mock_contents.csv"
TASKS = Path(__file__).with_name("tasks.json")


def main() -> None:
    df = load_contents(DATA)
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    rows = []
    for task in tasks:
        started = time.time()
        result = run_data_agent_graph(task["goal"], df)
        latency = time.time() - started
        validation = result.get("validation", {})
        rewards = result.get("rewards", {})
        rows.append({
            "task_id": task["id"],
            "success": bool(validation.get("valid")),
            "artifact_validity": 1.0 if validation.get("valid") else 0.0,
            "causal_overclaim_rate": 1.0 if any("因果" in issue and "过度" in issue for issue in validation.get("issues", [])) else 0.0,
            "repair_success": bool(result.get("repair_plan")) or validation.get("valid"),
            "latency": round(latency, 4),
            "reward": rewards.get("total_reward", 0),
            "method_entropy": result.get("evolution", {}).get("selected_plan", {}).get("artifacts", {}).get("method_entropy", 0),
        })
    print(json.dumps({"metrics": summarize(rows), "tasks": rows}, ensure_ascii=False, indent=2))


def summarize(rows: list[dict]) -> dict:
    n = max(1, len(rows))
    return {
        "task_success_rate": sum(r["success"] for r in rows) / n,
        "artifact_validity": sum(r["artifact_validity"] for r in rows) / n,
        "causal_overclaim_rate": sum(r["causal_overclaim_rate"] for r in rows) / n,
        "repair_success_rate": sum(r["repair_success"] for r in rows) / n,
        "average_latency": sum(r["latency"] for r in rows) / n,
        "average_reward": sum(r["reward"] for r in rows) / n,
        "method_entropy": sum(r["method_entropy"] for r in rows) / n,
    }


if __name__ == "__main__":
    main()
