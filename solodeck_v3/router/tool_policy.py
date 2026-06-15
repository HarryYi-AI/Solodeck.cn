from __future__ import annotations

from typing import Any


def select_tool_policy(task_spec: dict[str, Any], budget: dict[str, Any], kg_context: dict[str, Any] | None = None) -> dict[str, Any]:
    task_type = task_spec.get("task_type", "descriptive_analysis")
    tools = ["Python"]
    if kg_context:
        tools.append("KG")
    if task_type in {"causal_hypothesis_generation", "causal_effect_estimation", "counterfactual_analysis", "experiment_design"}:
        tools.extend(["CausalDiscovery", "CI", "Counterfactual"])
    if task_type in {"ideation", "planning", "writing"}:
        tools.append("RAG")
    if task_type == "workflow_debugging":
        tools.extend(["TraceValidator", "RepairLoop"])
    skills = ["SchemaSkill", "DataQualitySkill"]
    if "KG" in tools:
        skills.append("KGConstructionSkill")
    if "CausalDiscovery" in tools:
        skills.extend(["CausalDiscoverySkill", "CausalReadinessSkill", "RegressionSkill", "BootstrapSkill"])
    if "Counterfactual" in tools:
        skills.append("CounterfactualSkill")
    if task_type == "experiment_design":
        skills.append("DIDSkill")
    skills.append("ReportSkill")
    return {
        "tools": list(dict.fromkeys(tools)),
        "skills": list(dict.fromkeys(skills)),
        "budget_level": budget.get("budget_level"),
        "policy_reason": _reason(task_type, tools),
    }


def _reason(task_type: str, tools: list[str]) -> str:
    if "CausalDiscovery" in tools:
        return "任务涉及策略增量或实验，需要候选因果图、混杂检查和区间验证。"
    if task_type in {"ideation", "planning", "writing"}:
        return "任务偏生成与规划，优先检索记忆和图谱，再生成受约束产物。"
    return "任务偏数据理解，优先走结构映射、质量检查和报告。"

