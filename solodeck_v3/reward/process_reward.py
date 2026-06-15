from __future__ import annotations

from .reward_schema import REWARD_RULES


def assign_process_rewards(trace: list[dict], validation_report: dict) -> dict:
    issues = validation_report.get("issues", [])
    checks = validation_report.get("checks", [])
    invalid_checks = {c.get("name") for c in checks if not c.get("valid")}
    rewards = []
    for event in trace:
        step = event.get("step", "Unknown")
        agent = event.get("role", "Unknown")
        reward = 0.2
        reason = "完成可追踪步骤"
        if step in {"RouteTools", "PlanWorkflow"} and "trace" not in invalid_checks:
            reward += REWARD_RULES["correct_method_routing"]
            reason = "完成工具路由和方法规划"
        if step == "ValidateArtifacts" and not issues:
            reward += REWARD_RULES["valid_artifact"]
            reason = "产物通过校验"
        if step in {"Reflect", "RepairOrExplore"} and any("因果" in i or "区间" in i for i in issues):
            reward += REWARD_RULES["correct_causal_warning"]
            reason = "识别并处理因果/统计风险"
        if step == "RepairOrExplore" and not validation_report.get("valid"):
            reward += REWARD_RULES["successful_repair"]
            reason = "生成修复或探索计划"
        if any("缺少" in i for i in issues):
            reward += REWARD_RULES["missing_required_field"] * 0.2
        if any("强因果" in i or "unsupported" in i.lower() for i in issues):
            reward += REWARD_RULES["invalid_causal_overclaim"]
            reason = "存在未支持因果表述"
        if validation_report.get("block_output"):
            reward += REWARD_RULES["privacy_leakage"]
            reason = "隐私检查阻断输出"
        rewards.append({"step": step, "role": agent, "agent": agent, "reward": round(reward, 3), "reason": reason})
    return {"steps": rewards, "total": round(sum(r["reward"] for r in rewards), 3), "rules": REWARD_RULES}

