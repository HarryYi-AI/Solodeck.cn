from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypedDict


TaskType = Literal[
    "ideation",
    "planning",
    "experiment_design",
    "data_analysis",
    "descriptive_analysis",
    "causal_hypothesis_generation",
    "causal_effect_estimation",
    "counterfactual_analysis",
    "data_quality_repair",
    "report_generation",
    "writing",
    "method_comparison",
    "workflow_debugging",
]


@dataclass
class TaskSpec:
    task_type: TaskType
    objective: str
    required_data: list[str]
    candidate_variables: list[str]
    candidate_treatments: list[str]
    candidate_outcomes: list[str]
    constraints: list[str]
    allowed_skills: list[str]
    validation_rules: list[str]
    budget_level: str
    expected_artifacts: list[str] = field(default_factory=list)
    unit: str | None = None
    time: str | None = None
    estimand: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DataAgentState(TypedDict, total=False):
    task: str
    task_spec: dict[str, Any]
    schema_summary: dict[str, Any]
    data_quality_report: dict[str, Any]
    kg_context: dict[str, Any]
    causal_context: dict[str, Any]
    hypothesis_tree: dict[str, Any]
    route_decision: dict[str, Any]
    plan_candidates: list[dict[str, Any]]
    selected_plan: dict[str, Any]
    selected_skills: list[str]
    artifacts: list[dict[str, Any]]
    critique: dict[str, Any]
    validation_report: dict[str, Any]
    step_rewards: dict[str, Any]
    process_rewards: dict[str, Any]
    agent_rewards: dict[str, Any]
    revision_number: int
    max_revisions: int
    trace_id: str
    memory_updates: list[dict[str, Any]]
    failure_report: dict[str, Any]
    repair_plan: dict[str, Any]
    final_report: dict[str, Any]
    action_cards: list[dict[str, Any]]
    user_artifact: dict[str, Any]
    developer_trace: dict[str, Any]
    df: Any
    text: str
    trace: list[dict[str, Any]]


SKILL_ROLES = {
    "SchemaSkill": "ExecutorAgent",
    "DataQualitySkill": "ExecutorAgent",
    "AutoInsightsSkill": "ExecutorAgent",
    "DescriptiveComparisonSkill": "ExecutorAgent",
    "KGConstructionSkill": "RetrieverAgent",
    "CausalDiscoverySkill": "CausalAnalystAgent",
    "CausalReadinessSkill": "VerifierAgent",
    "BootstrapSkill": "CausalAnalystAgent",
    "RegressionSkill": "CausalAnalystAgent",
    "DIDSkill": "CausalAnalystAgent",
    "CounterfactualSkill": "ExplorerAgent",
    "ReportSkill": "WriterAgent",
}


ALL_SKILLS = list(SKILL_ROLES)
