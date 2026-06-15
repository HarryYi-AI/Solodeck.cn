from __future__ import annotations

from solodeck_v3.compiler.task_schema import SKILL_ROLES


def assign_process_rewards(trace: list[dict], validation_report: dict) -> dict:
    issues = validation_report.get("issues", [])
    rewards = []
    for event in trace:
        step = event.get("step", "Unknown")
        role = event.get("role", "Unknown")
        reward = 0.2
        reason = "完成可追踪步骤"
        if step in {"ValidateArtifacts", "AssignProcessRewards"} and not issues:
            reward += 1
            reason = "验证通过"
        if step in {"ReflectOrRepair", "RepairPlan"} and any("因果" in i or "区间" in i for i in issues):
            reward += 1
            reason = "识别并处理因果/统计风险"
        if step == "GenerateFinalReport" and issues:
            reward -= 1
            reason = "报告前仍有验证问题"
        if validation_report.get("block_output"):
            reward -= 2
            reason = "隐私检查阻断输出"
        rewards.append({"step": step, "role": role, "reward": round(reward, 3), "reason": reason})
    return {"steps": rewards, "total": round(sum(r["reward"] for r in rewards), 3)}

