from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskSpec:
    user_goal: str
    task_type: str
    project_id: str = "solodeck"
    session_id: str = ""
    task_id: str = field(default_factory=lambda: _id("task"))
    required_data_sources: list[str] = field(default_factory=list)
    candidate_tables: list[str] = field(default_factory=list)
    candidate_columns: list[str] = field(default_factory=list)
    treatment: str | None = None
    outcome: str | None = None
    dimensions: list[str] = field(default_factory=list)
    time_range: dict[str, Any] = field(default_factory=dict)
    expected_output: list[str] = field(default_factory=lambda: ["final_report"])
    required_evidence: list[str] = field(default_factory=lambda: ["executed_artifact"])
    required_tools: list[str] = field(default_factory=list)
    required_validation: list[str] = field(default_factory=lambda: ["artifact", "claim"])
    confidence: float = 0.0
    ambiguity: list[str] = field(default_factory=list)
    clarification_requirements: list[str] = field(default_factory=list)
    analysis_unit: str | None = None
    time_column: str | None = None
    constraints: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_legacy(cls, value: dict[str, Any], *, project_id: str, session_id: str) -> "TaskSpec":
        treatments = value.get("candidate_treatments") or []
        outcomes = value.get("candidate_outcomes") or []
        return cls(
            user_goal=value.get("objective") or "",
            task_type=value.get("task_type") or "descriptive_analysis",
            project_id=project_id,
            session_id=session_id,
            required_data_sources=list(value.get("required_data") or []),
            candidate_tables=list(value.get("candidate_tables") or ["uploaded_data"]),
            candidate_columns=list(value.get("candidate_variables") or []),
            treatment=treatments[0] if treatments else None,
            outcome=outcomes[0] if outcomes else None,
            dimensions=list(value.get("dimensions") or []),
            expected_output=list(value.get("expected_artifacts") or ["final_report"]),
            required_tools=list(value.get("allowed_skills") or []),
            required_validation=list(value.get("validation_rules") or []),
            confidence=float(value.get("confidence", 0.7)),
            ambiguity=list(value.get("ambiguity") or []),
            clarification_requirements=list(value.get("clarification_requirements") or []),
            analysis_unit=value.get("unit"),
            time_column=value.get("time"),
            constraints=list(value.get("constraints") or []),
        )


@dataclass
class PlanStep:
    goal: str
    operation: str
    source: str | None = None
    expected_output: str = "observation"
    step_id: str = field(default_factory=lambda: _id("step"))
    status: str = "pending"
    arguments: dict[str, Any] = field(default_factory=dict)
    observation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentState:
    task: TaskSpec
    plan: list[PlanStep] = field(default_factory=list)
    current_step: int = 0
    observations: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    critique: dict[str, Any] = field(default_factory=dict)
    revision_count: int = 0
    max_revisions: int = 2
    status: str = "created"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "task": self.task.to_dict(),
            "plan": [step.to_dict() for step in self.plan],
        }


@dataclass
class EvidenceObject:
    project_id: str
    task_id: str
    source_type: str
    source_id: str
    content_summary: str
    evidence_id: str = field(default_factory=lambda: _id("evidence"))
    artifact_id: str | None = None
    dataset_id: str | None = None
    dataset_version: str | None = None
    structured_payload: dict[str, Any] = field(default_factory=dict)
    retrieval_score: float = 0.0
    confidence: float = 0.0
    provenance: list[dict[str, Any]] = field(default_factory=list)
    privacy_scope: str = "project"
    generated_by: str = ""
    validated_by: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Artifact:
    project_id: str
    task_id: str
    artifact_type: str
    producer_node: str
    skill: str
    artifact_id: str = field(default_factory=lambda: _id("artifact"))
    input_artifacts: list[str] = field(default_factory=list)
    input_dataset_versions: dict[str, str] = field(default_factory=dict)
    code_or_query: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    validation_status: str = "pending"
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowNode:
    operation_type: str
    required_skill: str
    node_id: str = field(default_factory=lambda: _id("node"))
    dependencies: list[str] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    execution_environment: str = "python"
    retry_policy: dict[str, Any] = field(default_factory=lambda: {"max_attempts": 1})
    validation_policy: list[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    status: str = "pending"
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Workflow:
    task_id: str
    logical_nodes: list[WorkflowNode]
    physical_nodes: list[WorkflowNode]
    workflow_id: str = field(default_factory=lambda: _id("workflow"))
    version: int = 1
    validation_status: str = "pending"
    optimization_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "logical_nodes": [node.to_dict() for node in self.logical_nodes],
            "physical_nodes": [node.to_dict() for node in self.physical_nodes],
        }


@dataclass
class AnalysisState:
    project_id: str
    session_id: str
    task_id: str
    dataset_versions: dict[str, str]
    state_id: str = field(default_factory=lambda: _id("state"))
    parent_state_id: str | None = None
    branch_id: str = "main"
    selected_tables: list[str] = field(default_factory=list)
    selected_columns: list[str] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    joins: list[dict[str, Any]] = field(default_factory=list)
    derived_variables: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    current_workflow: dict[str, Any] = field(default_factory=dict)
    executed_nodes: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    validation_status: str = "pending"
    unresolved_questions: list[str] = field(default_factory=list)
    evidence_level: str = "descriptive_pattern"
    final_conclusions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnalysisState":
        allowed = cls.__dataclass_fields__
        return cls(**{key: value[key] for key in allowed if key in value})
