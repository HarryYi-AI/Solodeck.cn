from __future__ import annotations

from .memory_store import JsonMemoryStore


def store_skill_utility(trace_id: str, selected_plan: dict, agent_rewards: dict) -> dict:
    return JsonMemoryStore("skill_utility_memory").append({
        "trace_id": trace_id,
        "method": selected_plan.get("method"),
        "skills": selected_plan.get("skills", []),
        "score": selected_plan.get("score", 0),
        "agent_rewards": agent_rewards,
    })

