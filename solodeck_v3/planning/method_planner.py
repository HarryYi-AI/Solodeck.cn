from __future__ import annotations

from typing import Any


def generate_candidate_plans(task_spec: dict[str, Any], hypothesis_tree: dict[str, Any], budget: dict[str, Any]) -> list[dict[str, Any]]:
    task_type = task_spec.get("task_type", "descriptive_analysis")
    base = []
    if task_type in {"causal_hypothesis_generation", "causal_effect_estimation", "counterfactual_analysis", "experiment_design"}:
        base.extend([
            {
                "plan_id": "plan_kg_bootstrap",
                "method": "kg_constrained_bootstrap",
                "skills": ["SchemaSkill", "DataQualitySkill", "KGConstructionSkill", "CausalDiscoverySkill", "CausalReadinessSkill", "BootstrapSkill", "CounterfactualSkill", "ReportSkill"],
                "expected_artifacts": ["kg_context", "causal_context", "bootstrap_ci", "counterfactual_simulation", "final_report"],
                "estimated_cost": 0.28,
            },
            {
                "plan_id": "plan_regression_critic",
                "method": "regression_with_causal_critic",
                "skills": ["SchemaSkill", "DataQualitySkill", "KGConstructionSkill", "CausalReadinessSkill", "RegressionSkill", "BootstrapSkill", "ReportSkill"],
                "expected_artifacts": ["kg_context", "causal_readiness", "regression_effect", "bootstrap_ci", "final_report"],
                "estimated_cost": 0.22,
            },
        ])
    if task_type == "experiment_design":
        base.insert(0, {
            "plan_id": "plan_did_validation",
            "method": "did_with_bootstrap_guard",
            "skills": ["SchemaSkill", "DataQualitySkill", "KGConstructionSkill", "CausalReadinessSkill", "DIDSkill", "BootstrapSkill", "ReportSkill"],
            "expected_artifacts": ["kg_context", "causal_readiness", "did_effect", "bootstrap_ci", "final_report"],
            "estimated_cost": 0.24,
        })
    if task_type in {"ideation", "planning", "writing"}:
        base.append({
            "plan_id": "plan_fars_kg_report",
            "method": "fars_kg_guided_writing",
            "skills": ["SchemaSkill", "DataQualitySkill", "KGConstructionSkill", "ReportSkill"],
            "expected_artifacts": ["schema_summary", "data_quality_report", "kg_context", "final_report"],
            "estimated_cost": 0.14,
        })
    if task_type in {"descriptive_analysis", "data_analysis", "data_quality_repair", "report_generation", "method_comparison"}:
        comparison_requested = task_type in {"descriptive_analysis", "data_analysis", "method_comparison"} and bool(task_spec.get("candidate_treatments") and task_spec.get("candidate_outcomes"))
        auto_insights_requested = task_type == "report_generation"
        base.append({
            "plan_id": "plan_schema_report",
            "method": "descriptive_metric_comparison" if comparison_requested else ("automatic_data_profile" if auto_insights_requested else "schema_quality_report"),
            "skills": ["SchemaSkill", "DataQualitySkill"] + (["DescriptiveComparisonSkill"] if comparison_requested else []) + (["AutoInsightsSkill"] if auto_insights_requested else []) + ["ReportSkill"],
            "expected_artifacts": ["schema_summary", "data_quality_report"] + (["descriptive_comparison"] if comparison_requested else []) + (["auto_insights"] if auto_insights_requested else []) + ["final_report"],
            "estimated_cost": 0.1 if comparison_requested else 0.08,
        })
    if task_type == "workflow_debugging":
        base.append({
            "plan_id": "plan_debug_repair",
            "method": "trace_validation_repair",
            "skills": ["SchemaSkill", "DataQualitySkill", "KGConstructionSkill", "ReportSkill"],
            "expected_artifacts": ["trace", "validation_report", "final_report"],
            "estimated_cost": 0.16,
        })
    if not base:
        base.append({
            "plan_id": "plan_schema_report",
            "method": "schema_quality_report",
            "skills": ["SchemaSkill", "DataQualitySkill", "ReportSkill"],
            "expected_artifacts": ["schema_summary", "data_quality_report", "final_report"],
            "estimated_cost": 0.08,
        })
    max_plans = budget.get("max_plans", 2)
    return base[:max_plans]
