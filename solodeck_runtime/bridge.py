from __future__ import annotations

import re
from typing import Any

from .grounding import DataGrounder
from .models import AnalysisState, Artifact, TaskSpec
from .persistence import ArtifactRegistry, SQLiteRuntimeRepository, StateStore
from .workflow import WorkflowCompiler, WorkflowValidator


def prepare_runtime_protocol(state: dict[str, Any], repository: SQLiteRuntimeRepository | None = None) -> dict[str, Any]:
    repository = repository or SQLiteRuntimeRepository()
    task = TaskSpec.from_legacy(
        state.get("task_spec") or {},
        project_id=state.get("project_id", "solodeck"),
        session_id=state.get("session_id", ""),
    )
    repository.save_task(task)
    state["task_id"] = task.task_id
    state["task_spec_v2"] = task.to_dict()

    documents = {"uploaded_text": state["text"]} if state.get("text") else {}
    grounding = DataGrounder().ground(task, {"uploaded_data": state["df"]}, text_documents=documents)
    for evidence in grounding.evidence:
        repository.save_evidence(evidence)
    state["data_grounding"] = grounding.to_dict()
    state["dataset_version"] = grounding.dataset_versions.get("uploaded_data")

    workflow = WorkflowCompiler().compile(task, grounding)
    validation = WorkflowValidator().validate(workflow, datasets={"uploaded_data": state["df"]})
    if not validation["valid"]:
        raise ValueError(f"workflow validation failed: {validation['issues']}")
    state["analysis_workflow"] = workflow.to_dict()
    state["workflow_validation"] = validation
    return state


def finalize_runtime_protocol(
    state: dict[str, Any],
    reply: str,
    repository: SQLiteRuntimeRepository | None = None,
) -> AnalysisState:
    repository = repository or SQLiteRuntimeRepository()
    registry = ArtifactRegistry(repository)
    artifact_ids = []
    dataset_version = state.get("dataset_version") or state.get("trace_id", "unknown")
    raw_to_canonical: dict[str, str] = {}
    for raw in state.get("artifacts") or []:
        raw_id = str(raw.get("id") or raw.get("artifact_id") or "artifact")
        safe_raw_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw_id).strip("-") or "artifact"
        artifact_id = f"{state.get('task_id', state.get('trace_id', 'task'))}:{safe_raw_id}"
        declared_inputs = raw.get("input_artifacts") or raw.get("inputs") or []
        input_artifacts = [raw_to_canonical[item] for item in declared_inputs if item in raw_to_canonical]
        artifact = Artifact(
            project_id=state.get("project_id", "solodeck"), task_id=state.get("task_id", state.get("trace_id", "")),
            artifact_type=raw.get("type") or "analysis_result", producer_node=raw.get("producer_node") or "ExecuteSkills",
            skill=raw.get("generated_by") or raw.get("skill_id") or "legacy-skill-adapter",
            artifact_id=artifact_id,
            input_artifacts=input_artifacts,
            input_dataset_versions={"uploaded_data": str(raw.get("dataset_version") or dataset_version)},
            code_or_query=raw.get("code") or raw.get("query") or "",
            parameters=raw.get("parameters") or {}, payload=raw.get("content") or {},
            validation_status="valid" if raw.get("valid", True) else "invalid", warnings=list(raw.get("warnings") or []),
        )
        registry.register(artifact)
        artifact_ids.append(artifact.artifact_id)
        raw_to_canonical[raw_id] = artifact.artifact_id

    # A report summarizes the analytical outputs that actually preceded it. This is
    # the only implicit dependency added by the legacy adapter.
    report_ids = [item for item in artifact_ids if item.endswith(":final_report")]
    if report_ids:
        report = repository.get_artifact(report_ids[-1])
        if report is not None and not report.input_artifacts:
            report.input_artifacts = [item for item in artifact_ids if item != report.artifact_id]
            repository.save_artifact(report)

    task = state.get("task_spec_v2") or {}
    grounding = state.get("data_grounding") or {}
    analytical = AnalysisState(
        project_id=state.get("project_id", "solodeck"), session_id=state.get("session_id", ""),
        task_id=state.get("task_id", state.get("trace_id", "")),
        dataset_versions=grounding.get("dataset_versions") or {"uploaded_data": dataset_version},
        parent_state_id=state.get("parent_state_id"), branch_id=state.get("branch_id", "main"),
        selected_tables=grounding.get("selected_tables") or [], selected_columns=grounding.get("selected_columns") or [],
        filters=list(state.get("filters") or []), joins=list(grounding.get("join_candidates") or []),
        derived_variables=list(state.get("derived_variables") or []), hypotheses=list((state.get("hypothesis_tree") or {}).get("hypotheses") or []),
        assumptions=list(task.get("constraints") or []), current_workflow=state.get("analysis_workflow") or {},
        executed_nodes=[item.get("step") or item.get("node") for item in state.get("trace") or [] if item.get("step") or item.get("node")],
        artifacts=artifact_ids, validation_status="valid" if (state.get("governance_report") or {}).get("valid") else "needs_review",
        unresolved_questions=list(task.get("clarification_requirements") or []),
        evidence_level=str(state.get("evidence_level") or "descriptive_pattern"), final_conclusions=[reply] if reply else [],
    )
    StateStore(repository).snapshot(analytical)
    state["analytical_state"] = analytical.to_dict()
    state["state_id"] = analytical.state_id
    return analytical
