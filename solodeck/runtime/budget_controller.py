from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class BudgetPlan:
    level: str
    max_plans: int
    bootstrap_samples: int
    allow_llm: bool
    repair_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assign_reasoning_budget(task_spec: Any, risk_signals: dict[str, Any]) -> BudgetPlan:
    spec = task_spec.to_dict() if hasattr(task_spec, "to_dict") else dict(task_spec)
    unstable_ci = bool(risk_signals.get("unstable_ci"))
    missing_data = bool(risk_signals.get("missing_data"))
    high_risk = spec.get("task_type") == "causal_strategy" or unstable_ci or missing_data
    if high_risk:
        return BudgetPlan("deep_path", 3, 1600, True, True, "因果任务、缺失数据或区间不稳定，需要深度验证。")
    if spec.get("task_type") == "descriptive_decision":
        return BudgetPlan("fast_path", 1, 500, False, False, "低风险描述性任务，走快速路径。")
    return BudgetPlan("normal_path", 2, 1000, True, True, "需要图谱解释和常规验证。")

