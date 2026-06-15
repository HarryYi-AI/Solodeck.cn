from __future__ import annotations

import time
from typing import Any

from solodeck_v3.runtime.scheduler import schedule_skills


def generate_candidate_plans(task_spec: dict[str, Any], budget: dict[str, Any], history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    scheduled = schedule_skills(task_spec, budget, history)
    plans = []
    for idx, method in enumerate(scheduled["methods"] or ["schema_quality"]):
        skills = scheduled["skills"]
        if method == "regression_check":
            skills = [s for s in skills if s in {"SchemaSkill", "DataQualitySkill", "RegressionSkill", "CausalReadinessSkill", "ReportSkill"}] or ["RegressionSkill", "ReportSkill"]
        plans.append({
            "plan_id": f"plan_{idx + 1}",
            "method": method,
            "skills": skills,
            "estimated_cost": round(0.1 + 0.03 * len(skills), 3),
            "method_entropy": scheduled["method_entropy"],
            "score": 0,
        })
    return plans


def score_plan(plan: dict[str, Any], validation: dict[str, Any], latency: float) -> dict[str, Any]:
    validity = 1 if validation.get("valid") else 0
    causal_penalty = 1 if any("因果" in issue for issue in validation.get("issues", [])) else 0
    cost = plan.get("estimated_cost", 0.1)
    score = validity * 3 - causal_penalty - cost - latency * 0.02 + plan.get("method_entropy", 0) * 0.1
    return {**plan, "score": round(score, 4), "latency": round(latency, 4)}

