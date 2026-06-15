from __future__ import annotations


def validate_rewards(step_rewards: dict, agent_rewards: dict) -> dict:
    issues = []
    if not step_rewards.get("steps"):
        issues.append("缺少步骤奖励")
    if not agent_rewards:
        issues.append("缺少角色奖励")
    return {"name": "reward", "valid": not issues, "issues": issues}

