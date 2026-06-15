from __future__ import annotations


class PlannerAgent:
    name = "PlannerAgent"

    def plan(self, task_spec: dict, route_decision: dict, plan_candidates: list[dict]) -> dict:
        if route_decision.get("candidate_skills"):
            preferred = next((p for p in plan_candidates if set(route_decision["candidate_skills"]).issuperset(p.get("skills", []))), None)
        else:
            preferred = None
        return preferred or (plan_candidates[0] if plan_candidates else {"plan_id": "fallback", "skills": ["SchemaSkill", "DataQualitySkill", "ReportSkill"], "estimated_cost": 0.1})

