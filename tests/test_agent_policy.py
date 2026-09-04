from __future__ import annotations

import tempfile
from pathlib import Path

from solodeck_v4.critics import evaluate_run
from solodeck_v4.bench import AgentEvalCase, evaluate_agent_result
from solodeck_v4.evidence import build_claim_records, validate_claim_records
from solodeck_v4.evolution import AdaptivePlanPolicy
from solodeck_v4.memory import SQLiteMemoryBackend, UnifiedMemory
from solodeck_v4.routing import route_task_intent
from solodeck_v4.tools import call_tool


def test_l2_routes_implicit_group_effect_question() -> None:
    route = route_task_intent(
        "我想分个组看看效果",
        ["title_style", "consultations", "content_id"],
        baseline_task_type="descriptive_analysis",
        allow_llm=False,
    )
    assert route.layer == "L2"
    assert route.task_type == "causal_effect_estimation"
    assert route.confidence >= 0.48


def test_l2_keeps_plain_ranking_descriptive() -> None:
    route = route_task_intent(
        "哪个平台转化更好？",
        ["platform", "conversion_rate"],
        baseline_task_type="descriptive_analysis",
        allow_llm=False,
    )
    assert route.task_type == "descriptive_analysis"


def test_critic_returns_repair_directive_for_unstable_unsafe_action() -> None:
    state = {
        "task_spec": {
            "task_type": "causal_effect_estimation",
            "objective": "标题是否提升咨询",
            "candidate_treatments": ["title_style"],
            "candidate_outcomes": ["consultations"],
            "expected_artifacts": ["causal_readiness", "bootstrap_ci"],
            "unit": "content_id",
        },
        "semantic_route": {"layer": "L2", "confidence": 0.8},
        "artifacts": [
            {"id": "causal_readiness", "valid": True, "source_type": "python", "content": {"score": 85}},
            {"id": "bootstrap_ci", "valid": True, "source_type": "python", "content": {"sample_size": 40, "ci_95": [-1.0, 2.0]}},
        ],
        "action_cards": [{"title": "直接放大痛点标题", "action": "全面使用"}],
        "trace": [{"step": "CompileTask"}, {"step": "ExecuteSkills"}, {"step": "ValidateArtifacts"}],
    }
    report = evaluate_run(state).to_dict()
    assert report["decision"] == "repair"
    assert any(item["failure_type"] == "uncertainty_ignored" for item in report["repair_directives"])


def test_adaptive_policy_learns_plan_utility_and_changes_selection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        memory = UnifiedMemory(SQLiteMemoryBackend(Path(tmp) / "policy.db"))
        policy = AdaptivePlanPolicy(memory)
        plans = [
            {"plan_id": "a", "skills": ["BootstrapSkill"], "estimated_cost": 0.1},
            {"plan_id": "b", "skills": ["RegressionSkill"], "estimated_cost": 0.1},
        ]
        state = {
            "project_id": "p1",
            "trace_id": "trace_b",
            "task_spec": {"task_type": "causal_effect_estimation"},
            "selected_plan": plans[1],
            "critic_report": {"overall_score": 0.95, "trajectory_informative": True},
            "failure_report": {"failures": []},
            "industrial_process_reward": {"total": 5},
        }
        for index in range(5):
            state["trace_id"] = f"trace_b_{index}"
            assert policy.update_from_run(state)["updated"] is True
        selected, decision = policy.select_plan(plans, task_type="causal_effect_estimation", project_id="p1")
        assert selected["plan_id"] == "b"
        assert decision["history_items"] == 1


def test_tool_contract_denies_missing_permission_and_writes_audit() -> None:
    state = {"message": "test", "permissions": []}
    result = call_tool("retrieve_memory", state, {})
    assert result["ok"] is False
    assert result["error"]["type"] == "permission_denied"
    assert state["tool_audit"][0]["status"] == "error"


def test_claim_ledger_binds_numeric_result_to_python_artifact() -> None:
    state = {
        "task_spec": {"unit": "content_id", "time": "publish_time"},
        "final_report": {
            "result": "痛点标题咨询增量 2.30。",
            "method": "Bootstrap",
            "confidence": "需要验证",
            "limitation": "当前样本较小",
        },
        "artifacts": [
            {"id": "bootstrap_ci", "source_type": "python", "generated_by": "BootstrapSkill", "content": {"ate": 2.3}},
        ],
    }
    state["claims"] = build_claim_records(state)
    report = validate_claim_records(state)
    assert report["valid"] is True
    assert state["claims"][0]["source_artifact_ids"] == ["bootstrap_ci"]


def test_agent_eval_scores_route_tools_claims_and_critic() -> None:
    case = AgentEvalCase(
        case_id="c1",
        message="哪个平台更好",
        expected_task_type="descriptive_analysis",
        expected_critic_decision="pass",
        expected_tools=["compile_task", "execute_analysis"],
    )
    result = {
        "semantic_route": {"task_type": "descriptive_analysis"},
        "task_spec": {"task_type": "descriptive_analysis", "objective": "比较平台"},
        "critic_report": {"decision": "pass"},
        "tool_audit": [
            {"tool": "compile_task", "status": "ok", "latency_ms": 2},
            {"tool": "execute_analysis", "status": "ok", "latency_ms": 8},
        ],
        "claims": [{"source_artifact_ids": ["descriptive_comparison"]}],
        "governance_report": {"block_output": False},
        "cost_spent": 0.1,
    }
    evaluated = evaluate_agent_result(case, result)
    assert evaluated["passed"] is True
    assert evaluated["metrics"]["task_success"] == 1.0
