from __future__ import annotations

from typing import Any

from solodeck_v3.router.budget_router import route_budget


RISK_KEYWORDS = ("因果", "增量", "置信", "混杂", "ab", "实验", "证明", "一定", "必然")
CHEAP_FOLLOWUP = ("那个", "同样", "继续", "换成", "再看", "呢")


def assess_risk(message: str, task_spec: dict[str, Any], session: dict[str, Any], entity_link: dict[str, Any]) -> dict[str, Any]:
    """Risk-aware routing: deep path for causal risk, cache reuse for cheap follow-ups."""
    msg = message or ""
    task_type = task_spec.get("task_type", "descriptive_analysis")
    causal_types = {"causal_effect_estimation", "counterfactual_analysis", "causal_hypothesis_generation", "experiment_design"}

    needs_clarification = bool(entity_link.get("unresolved")) and not entity_link.get("ready")
    high_risk = any(k in msg for k in RISK_KEYWORDS) or task_type in causal_types
    cheap_followup = any(k in msg for k in CHEAP_FOLLOWUP) and session.get("artifact_cache")

    budget = route_budget(task_spec)
    if cheap_followup and not high_risk:
        return {
            "budget_level": "fast_path",
            "max_plans": 1,
            "max_revisions": 0,
            "reuse_cache": True,
            "high_risk": False,
            "needs_clarification": needs_clarification,
            "reason": "多轮追问且非高风险，复用缓存降低成本。",
        }
    if needs_clarification:
        return {
            "budget_level": "fast_path",
            "reuse_cache": False,
            "needs_clarification": True,
            "high_risk": False,
            "reason": "实体指代未解析，先澄清。",
        }
    if high_risk:
        budget["budget_level"] = "deep_path"
        budget["high_risk"] = True
        budget["reason"] = "因果/高风险问题，走深度验证路径。"
        return budget

    budget["high_risk"] = False
    budget["needs_clarification"] = False
    budget["reuse_cache"] = False
    return budget
