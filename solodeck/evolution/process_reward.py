from __future__ import annotations

from typing import Any


def assign_process_rewards(trace: list[dict[str, Any]], final_validation_result: dict[str, Any]) -> dict[str, Any]:
    rewards = []
    validation_issues = final_validation_result.get("issues", [])
    for step in trace:
        name = step.get("step", "unknown") if isinstance(step, dict) else str(step)
        reward = 0.2
        reason = "完成步骤"
        if name in {"Verification", "Evaluation"} and not validation_issues:
            reward += 1.0
            reason = "阻止无效输出或验证通过"
        if validation_issues and name in {"ReportGeneration", "ActionPlan"}:
            reward -= 0.6
            reason = "最终仍有验证问题"
        if "causal" in " ".join(validation_issues).lower() and name in {"Reflection", "Evaluation"}:
            reward += 0.5
            reason = "识别并约束因果风险"
        rewards.append({"step": name, "reward": round(reward, 3), "reason": reason})
    total = round(sum(item["reward"] for item in rewards), 3)
    return {"step_rewards": rewards, "total_reward": total}

