from __future__ import annotations

from typing import Any

from .budget_router import route_budget
from .tool_policy import select_tool_policy


def route_task(task_spec: dict[str, Any], quality_report: dict[str, Any] | None = None, critique: dict[str, Any] | None = None, kg_context: dict[str, Any] | None = None) -> dict[str, Any]:
    budget = route_budget(task_spec, quality_report, critique)
    policy = select_tool_policy(task_spec, budget, kg_context)
    return {
        "route_id": f"{task_spec.get('task_type', 'task')}::{policy['budget_level']}",
        "task_type": task_spec.get("task_type"),
        "budget": budget,
        "tool_policy": policy,
        "selected_tools": policy["tools"],
        "candidate_skills": policy["skills"],
        "requires_repair_loop": budget.get("max_revisions", 0) > 1,
    }

