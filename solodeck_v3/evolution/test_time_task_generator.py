from __future__ import annotations


def generate_test_time_tasks(base_task: str, failure_report: dict | None = None) -> list[dict]:
    failure_type = (failure_report or {}).get("failure_type", "none")
    return [
        {"goal": base_task, "strategy": "fast_path"},
        {"goal": f"{base_task}，补充区间估计和混杂检查", "strategy": "causal_guard"},
        {"goal": f"{base_task}，如果证据不足则降级为验证计划", "strategy": f"repair_{failure_type}"},
    ]

