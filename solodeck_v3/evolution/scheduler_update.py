from __future__ import annotations

from solodeck_v3.memory.skill_utility_memory import store_skill_utility


def update_scheduler_policy(trace_id: str, selected_plan: dict, agent_rewards: dict) -> dict:
    memory = store_skill_utility(trace_id, selected_plan, agent_rewards)
    return {"updated": True, "memory": memory, "policy_note": "未来同类任务会优先参考该计划得分和角色奖励。"}

