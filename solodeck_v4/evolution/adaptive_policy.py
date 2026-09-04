from __future__ import annotations

import hashlib
import math
from typing import Any

from solodeck_v4.memory import MemoryItem, UnifiedMemory


class AdaptivePlanPolicy:
    """DAPO-inspired workflow policy; updates plan utility, never LLM weights.

    Dynamic sampling keeps informative trajectories. Asymmetric clipping limits
    abrupt utility changes. This is deliberately not the token-level DAPO loss.
    """

    def __init__(self, memory: UnifiedMemory | None = None) -> None:
        self.memory = memory or UnifiedMemory()

    def select_plan(
        self,
        plans: list[dict[str, Any]],
        *,
        task_type: str,
        project_id: str = "solodeck",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not plans:
            fallback = {"plan_id": "fallback", "skills": ["SchemaSkill", "DataQualitySkill", "ReportSkill"], "estimated_cost": 0.1}
            return fallback, {"policy": "fallback", "scores": {"fallback": 0.0}}
        memories = self.memory.retrieve_memory(
            query=task_type,
            project_id=project_id,
            memory_type="skill",
            limit=100,
        )
        history: dict[str, dict[str, float]] = {}
        for item in memories:
            payload = item.structured_payload or {}
            if payload.get("kind") != "plan_utility" or payload.get("task_type") != task_type:
                continue
            history[payload.get("plan_id", "")] = {
                "utility": float(payload.get("utility", 0.5)),
                "count": float(payload.get("count", 0)),
            }
        total = sum(row["count"] for row in history.values())
        scores: dict[str, dict[str, float]] = {}
        for index, plan in enumerate(plans):
            plan_id = plan.get("plan_id", f"plan_{index}")
            prior = history.get(plan_id, {"utility": 0.5, "count": 0.0})
            exploration = math.sqrt(math.log(total + 2.0) / (prior["count"] + 1.0))
            cost_penalty = min(0.2, float(plan.get("estimated_cost", 0.1)) * 0.25)
            order_prior = max(0.0, 0.02 - index * 0.005)
            score = prior["utility"] + 0.08 * exploration - cost_penalty + order_prior
            scores[plan_id] = {
                "score": round(score, 6),
                "utility": round(prior["utility"], 6),
                "count": int(prior["count"]),
                "exploration_bonus": round(0.08 * exploration, 6),
                "cost_penalty": round(cost_penalty, 6),
            }
        selected = max(plans, key=lambda plan: scores[plan.get("plan_id")]["score"])
        return selected, {
            "policy": "critic_rewarded_ucb",
            "task_type": task_type,
            "selected_plan_id": selected.get("plan_id"),
            "scores": scores,
            "history_items": len(history),
        }

    def update_from_run(self, state: dict[str, Any]) -> dict[str, Any]:
        plan = state.get("selected_plan") or {}
        plan_id = plan.get("plan_id")
        task_type = (state.get("task_spec") or {}).get("task_type")
        if not plan_id or not task_type:
            return {"updated": False, "reason": "missing plan or task type"}
        critic = state.get("critic_report") or {}
        failures = (state.get("failure_report") or {}).get("failures") or []
        informative = bool(critic.get("trajectory_informative") or failures)
        if not informative:
            return {"updated": False, "reason": "dynamic sampling skipped saturated trajectory"}

        project_id = state.get("project_id", "solodeck")
        memory_id = _stable_memory_id(project_id, task_type, plan_id)
        current = self.memory.read_memory(memory_id)
        payload = dict(current.structured_payload) if current else {}
        old_utility = float(payload.get("utility", 0.5))
        old_count = int(payload.get("count", 0))
        critic_score = float(critic.get("overall_score", 0.0))
        process_total = float((state.get("industrial_process_reward") or {}).get("total", 0.0))
        process_score = (math.tanh(process_total / 5.0) + 1.0) / 2.0
        observed_reward = 0.7 * critic_score + 0.3 * process_score
        delta = observed_reward - old_utility
        clipped_delta = max(-0.15, min(0.25, delta))
        alpha = 1.0 / min(10.0, old_count + 2.0)
        utility = max(0.0, min(1.0, old_utility + alpha * clipped_delta))
        next_payload = {
            "kind": "plan_utility",
            "task_type": task_type,
            "plan_id": plan_id,
            "skills": plan.get("skills", []),
            "utility": round(utility, 6),
            "count": old_count + 1,
            "last_reward": round(observed_reward, 6),
            "critic_score": round(critic_score, 6),
            "process_score": round(process_score, 6),
            "positive_clip": 0.25,
            "negative_clip": 0.15,
            "source_trace_id": state.get("trace_id"),
        }
        if current:
            item = self.memory.update_memory(memory_id, {
                "structured_payload": next_payload,
                "content_summary": f"{task_type} 的 {plan_id} 效用 {utility:.3f}",
                "quality_score": utility,
                "warnings": [failure.get("failure_type", "") for failure in failures],
            })
        else:
            item = self.memory.write_memory(MemoryItem(
                memory_id=memory_id,
                memory_type="skill",
                project_id=project_id,
                session_id="policy",
                task_id=state.get("trace_id", ""),
                source_type="adaptive_plan_policy",
                source_id=plan_id,
                content_summary=f"{task_type} 的 {plan_id} 效用 {utility:.3f}",
                structured_payload=next_payload,
                quality_score=utility,
                warnings=[failure.get("failure_type", "") for failure in failures],
                retention_policy="permanent",
            ))
        return {"updated": True, "memory_id": item.memory_id, **next_payload}


def _stable_memory_id(project_id: str, task_type: str, plan_id: str) -> str:
    digest = hashlib.sha256(f"{project_id}:{task_type}:{plan_id}".encode("utf-8")).hexdigest()[:24]
    return f"planutil_{digest}"
