from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TaskSpec:
    task_type: str
    target_metric: str
    candidate_variables: list[str]
    required_artifacts: list[str]
    constraints: list[str]
    validation_rules: list[str]
    allowed_skills: list[str]
    user_goal: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compile_user_goal(user_goal: str, data_schema: dict[str, Any]) -> TaskSpec:
    goal = (user_goal or "").lower()
    fields = list(data_schema.get("columns", data_schema if isinstance(data_schema, dict) else []))
    metric_candidates = ["revenue", "conversions", "consultations", "favorites", "views"]
    target_metric = next((m for m in metric_candidates if m in fields and m in goal), "")
    if not target_metric:
        target_metric = next((m for m in metric_candidates if m in fields), "revenue")
    causal_words = ["因果", "增量", "影响", "提升", "ate", "cate", "ab", "实验", "cause", "effect", "lift"]
    graph_words = ["图谱", "关系", "实体", "知识", "graph", "kg"]
    if any(word in goal for word in causal_words):
        task_type = "causal_strategy"
    elif any(word in goal for word in graph_words):
        task_type = "graph_exploration"
    else:
        task_type = "descriptive_decision"
    candidate_variables = [c for c in ["platform", "topic", "title_style", "publish_time", "production_hours", "feature_tags"] if c in fields]
    required_artifacts = ["schema", "quality_report", "action_cards"]
    if task_type in {"causal_strategy", "graph_exploration"}:
        required_artifacts.extend(["knowledge_graph", "candidate_dag"])
    if task_type == "causal_strategy":
        required_artifacts.extend(["bootstrap_ci", "causal_claim_check"])
    constraints = [
        "不展示原始私有数据",
        "因果结论必须带置信区间",
        "区间穿过 0 时只能建议验证，不能建议直接放大",
    ]
    return TaskSpec(
        task_type=task_type,
        target_metric=target_metric,
        candidate_variables=candidate_variables,
        required_artifacts=required_artifacts,
        constraints=constraints,
        validation_rules=["artifact_completeness", "statistical_validity", "causal_claim", "privacy", "trace"],
        allowed_skills=["SchemaSkill", "DataQualitySkill", "KGConstructionSkill", "CausalDiscoverySkill", "BootstrapSkill", "RegressionSkill", "ReportSkill", "ActionPlanSkill"],
        user_goal=user_goal,
    )

