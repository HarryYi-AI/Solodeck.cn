from __future__ import annotations


def summarize_benchmark(rows: list[dict]) -> dict:
    n = max(1, len(rows))
    return {
        "task_success_rate": sum(r["success"] for r in rows) / n,
        "artifact_validity_rate": sum(r["artifact_validity"] for r in rows) / n,
        "causal_overclaim_rate": sum(r["causal_overclaim"] for r in rows) / n,
        "statistical_warning_recall": sum(r["statistical_warning_recall"] for r in rows) / n,
        "repair_success_rate": sum(r["repair_success"] for r in rows) / n,
        "route_accuracy": sum(r.get("route_accuracy", 0) for r in rows) / n,
        "average_latency": sum(r["latency"] for r in rows) / n,
        "average_cost": sum(r["cost"] for r in rows) / n,
        "agent_reward_variance": _variance([r["agent_reward_total"] for r in rows]),
        "improvement_after_memory_update": sum(r["memory_updated"] for r in rows) / n,
    }


def _variance(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)
