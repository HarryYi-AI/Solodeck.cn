from __future__ import annotations

from typing import Any

from .method_scheduler import select_methods


METHOD_TO_SKILLS = {
    "schema_quality": ["SchemaSkill", "DataQualitySkill"],
    "kg_causal_bootstrap": ["KGConstructionSkill", "CausalDiscoverySkill", "CausalReadinessSkill", "BootstrapSkill"],
    "regression_check": ["RegressionSkill", "CausalReadinessSkill"],
    "did_check": ["DIDSkill", "CausalReadinessSkill"],
    "counterfactual": ["CounterfactualSkill", "BootstrapSkill"],
    "report": ["ReportSkill"],
}


def schedule_skills(task_spec: dict[str, Any], budget: dict[str, Any], history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    history = history or []
    if task_spec.get("task_type") == "descriptive_analysis":
        candidates = ["schema_quality", "report"]
    elif task_spec.get("task_type") == "counterfactual_analysis":
        candidates = ["kg_causal_bootstrap", "counterfactual", "report"]
    elif task_spec.get("task_type") == "experiment_design":
        candidates = ["kg_causal_bootstrap", "did_check", "report"]
    else:
        candidates = ["kg_causal_bootstrap", "regression_check", "report"]
    uncertainty = 0.75 if budget.get("budget_level") == "deep_path" else 0.35
    method_info = select_methods(candidates, history, uncertainty, k=min(len(candidates), budget.get("max_plans", 1)))
    skills = []
    for method in method_info["selected_methods"]:
        for skill in METHOD_TO_SKILLS[method]:
            if skill not in skills:
                skills.append(skill)
    return {"methods": method_info["selected_methods"], "skills": skills, "method_entropy": method_info["method_entropy"], "scores": method_info["scores"]}
