from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from solodeck_runtime import (
    AnalysisState, Artifact, ArtifactRegistry, DataGrounder, SQLiteRuntimeRepository,
    StateStore, TaskSpec, WorkflowCompiler, WorkflowValidator,
    RetrievalQuery, StructuredRetriever, run_solodatabench_lite,
)
from solodeck_runtime.verifier import ActiveVerifier
from solodeck_v4.runtime.runner import execute_state_command


def _repo(tmp: str) -> SQLiteRuntimeRepository:
    return SQLiteRuntimeRepository(Path(tmp) / "runtime.db")


def test_demo_1_single_file_grounding_and_workflow() -> None:
    frame = pd.DataFrame({"platform": ["a", "b"], "views": [100, 200], "conversions": [2, 8]})
    task = TaskSpec("比较平台转化", "descriptive_analysis", candidate_tables=["content"], outcome="conversions", dimensions=["platform"])
    grounding = DataGrounder().ground(task, {"content": frame})
    workflow = WorkflowCompiler().compile(task, grounding)
    validation = WorkflowValidator().validate(workflow, datasets={"content": frame})
    assert grounding.dataset_versions["content"]
    assert "platform" in grounding.selected_columns
    assert validation["valid"] is True
    assert workflow.logical_nodes[-2].operation_type == "ValidateClaim"


def test_demo_2_multi_source_resolves_mismatched_keys_and_text() -> None:
    orders = pd.DataFrame({"cust_id": ["u1", "u2"], "amount": [10, 20]})
    users = pd.DataFrame({"user_identifier": ["u1", "u2"], "segment": ["new", "old"]})
    task = TaskSpec("结合用户反馈分析收入", "data_analysis", candidate_tables=["orders", "users"], outcome="revenue")
    result = DataGrounder().ground(task, {"orders": orders, "users": users}, text_documents={"feedback": "用户反馈配送速度慢"})
    assert result.join_candidates[0]["canonical_entity"] == "customer_id"
    assert result.join_candidates[0]["confidence"] > 0.9
    assert any(item.source_type == "text" for item in result.evidence)


def test_demo_3_state_snapshot_branch_rollback_and_diff() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(_repo(tmp))
        original = store.snapshot(AnalysisState("p", "s", "t1", {"d": "v1"}, filters=[]))
        cleaned = store.branch(original.state_id, "remove-outliers", filters=[{"column": "revenue", "op": "<", "value": 1000}])
        differences = store.diff(original.state_id, cleaned.state_id)
        restored = store.rollback(cleaned.state_id, original.state_id)
        assert "filters" in differences
        assert restored.filters == []
        assert restored.parent_state_id == cleaned.state_id


def test_demo_4_active_verifier_detects_silent_join_inflation() -> None:
    left = pd.DataFrame({"id": [1, 1], "revenue": [10, 20]})
    right = pd.DataFrame({"id": [1, 1], "label": ["a", "b"]})
    report = ActiveVerifier().inspect_join(left, right, left_on="id", right_on="id")
    assert report["valid"] is False
    assert report["probes"]["row_inflation"] == 2.0
    assert any("重复计算" in issue for issue in report["issues"])


def test_demo_5_causal_workflow_requires_readiness_and_uncertainty() -> None:
    frame = pd.DataFrame({"title_style": [0, 1] * 10, "consultations": range(20), "content_id": range(20)})
    task = TaskSpec("标题是否带来咨询增量", "causal_effect_estimation", treatment="title_style", outcome="consultations", analysis_unit="content_id")
    grounding = DataGrounder().ground(task, {"content": frame})
    workflow = WorkflowCompiler().compile(task, grounding)
    operations = [node.operation_type for node in workflow.physical_nodes]
    assert operations.index("CausalReadiness") < operations.index("Bootstrap")
    assert "Regression" in operations
    assert "ValidateClaim" in operations


def test_workflow_validator_rejects_missing_analysis_columns() -> None:
    frame = pd.DataFrame({"title_style": [0, 1]})
    task = TaskSpec("标题是否影响咨询", "causal_effect_estimation", treatment="title_style", outcome="consultations")
    grounding = DataGrounder().ground(task, {"content": frame})
    workflow = WorkflowCompiler().compile(task, grounding)
    validation = WorkflowValidator().validate(workflow, datasets={"content": frame})
    assert validation["valid"] is False
    assert "consultations" in validation["issues"][0]


def test_artifact_registry_preserves_executable_lineage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        registry = ArtifactRegistry(_repo(tmp))
        schema = registry.register(Artifact("p", "t", "schema_profile", "ProfileSchema", "SchemaSkill"))
        metric = registry.register(Artifact("p", "t", "sql_result", "CreateMetric", "MetricSkill", input_artifacts=[schema.artifact_id], code_or_query="select avg(revenue) from data"))
        lineage = registry.lineage(metric.artifact_id)
        assert {node["artifact_id"] for node in lineage["nodes"]} == {schema.artifact_id, metric.artifact_id}
        assert lineage["edges"] == [{"source": schema.artifact_id, "target": metric.artifact_id}]


def test_source_aware_retrieval_uses_scope_and_exact_lineage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repository = _repo(tmp)
        task = TaskSpec("检查收入", "data_analysis", project_id="p", session_id="s")
        repository.save_task(task)
        artifact = Artifact("p", task.task_id, "sql_result", "CreateMetric", "MetricSkill", payload={"value": 15})
        ArtifactRegistry(repository).register(artifact)
        evidence = StructuredRetriever(repository).retrieve(RetrievalQuery(
            project_id="p", task_id=task.task_id, source_type="artifact", referenced_id=artifact.artifact_id,
        ))
        assert len(evidence) == 1
        assert evidence[0].artifact_id == artifact.artifact_id
        assert evidence[0].structured_payload == {"value": 15}


def test_solodatabench_lite_passes_reference_cases() -> None:
    report = run_solodatabench_lite()
    assert report["summary"]["passed"] == report["summary"]["total"]


def test_natural_language_rollback_uses_persisted_state_ids() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(_repo(tmp))
        first = store.snapshot(AnalysisState("p", "s", "t1", {"d": "v1"}, filters=[]))
        second = store.branch(first.state_id, "main", filters=[{"column": "revenue", "op": ">", "value": 0}])
        session = {
            "last_state_id": second.state_id,
            "state_history": [{"state_id": first.state_id}, {"state_id": second.state_id}],
        }
        result = execute_state_command("回到移除异常值之前并和当前结果比较", session, store)
        assert result is not None
        assert result["analytical_state"]["filters"] == []
        assert "filters" in result["state_diff"]
