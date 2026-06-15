from __future__ import annotations

from typing import Any


def route_budget(task_spec: dict[str, Any], quality_report: dict[str, Any] | None = None, critique: dict[str, Any] | None = None) -> dict[str, Any]:
    quality_report = quality_report or {}
    critique = critique or {}
    task_type = task_spec.get("task_type", "descriptive_analysis")
    complex_types = {"causal_hypothesis_generation", "causal_effect_estimation", "counterfactual_analysis", "experiment_design", "workflow_debugging"}
    risky = bool(quality_report.get("warnings")) or bool(critique.get("unsupported_causal_claim")) or bool(critique.get("unstable_ci"))
    if task_type in complex_types or risky:
        return {
            "budget_level": "deep_path",
            "max_plans": 3,
            "max_revisions": 2,
            "bootstrap_samples": 1600,
            "reason": "复杂或高不确定任务需要多计划、区间估计和修复循环。",
        }
    if task_type in {"descriptive_analysis", "data_analysis"}:
        return {
            "budget_level": "fast_path",
            "max_plans": 1,
            "max_revisions": 1,
            "bootstrap_samples": 500,
            "reason": "低风险数据理解任务走快速路径。",
        }
    return {
        "budget_level": "normal_path",
        "max_plans": 2,
        "max_revisions": 2,
        "bootstrap_samples": 1000,
        "reason": "常规任务需要基础验证。",
    }

