from __future__ import annotations

from typing import Any

from solodeck_v4.governance import govern_claims, score_process
from solodeck_v4.memory import MemoryItem, UnifiedMemory
from solodeck_v4.runtime.checkpoint import CheckpointStore


def initialize_industrial_state(state: dict[str, Any], *, project_id: str = "solodeck") -> dict[str, Any]:
    state.setdefault("project_id", project_id)
    state.setdefault("user_task", state.get("message") or state.get("task") or "")
    state.setdefault("session_context", {})
    state.setdefault("memory_context", {})
    state.setdefault("evidence_pack", {})
    state.setdefault("route_decision", {})
    state.setdefault("selected_skills", [])
    state.setdefault("artifacts", [])
    state.setdefault("validators", [])
    state.setdefault("critique", {})
    state.setdefault("evidence_level", 1)
    state.setdefault("final_answer", "")
    state.setdefault("revision_number", 0)
    state.setdefault("max_revisions", 2)
    state.setdefault("failure_report", {})
    state.setdefault("memory_updates", [])
    state.setdefault("tool_audit", [])
    state.setdefault("permissions", [
        "memory:read", "schema:read", "plan:write", "analysis:execute",
        "artifact:validate", "response:write",
    ])
    return state


def checkpoint(state: dict[str, Any], node: str, store: CheckpointStore | None = None) -> str:
    path = (store or CheckpointStore()).save(state["trace_id"], node, state)
    return str(path)


def finalize_industrial_runtime(
    state: dict[str, Any], draft: str, *, memory: UnifiedMemory | None = None,
) -> dict[str, Any]:
    initialize_industrial_state(state)
    governance = govern_claims(state, draft)
    state["governance_report"] = governance
    state["validators"] = governance["checks"]
    state["evidence_level"] = governance["evidence_level"]
    state["final_answer"] = governance["answer"]
    state["failure_report"] = _failure_report(governance)
    from solodeck_v4.critics import evaluate_run
    critic = evaluate_run(state, phase="postwrite")
    state["critic_report"] = critic.to_dict()
    if critic.failures:
        known = {failure.get("failure_type") for failure in state["failure_report"].get("failures", [])}
        state["failure_report"].setdefault("failures", []).extend(
            failure for failure in critic.failures if failure.get("failure_type") not in known
        )
    state["industrial_process_reward"] = score_process(state, governance)
    from solodeck_v4.evolution import AdaptivePlanPolicy
    state["plan_utility_update"] = AdaptivePlanPolicy().update_from_run(state)
    from solodeck_v4.evolution import SkillOptLite
    failures = state["failure_report"].get("failures", [])
    normalized_failures = [
        {"failure_type": failure["failure_type"], "failure_id": f"{state.get('trace_id')}:{index}"}
        for index, failure in enumerate(failures)
    ]
    state["skill_patches"] = [patch.to_dict() for patch in SkillOptLite().propose(normalized_failures)]
    from solodeck_v3.frontend.developer_trace_panel import build_developer_trace_panel
    state["developer_trace"] = build_developer_trace_panel(state)
    checkpoint(state, "post_writer_gate")

    store = memory or UnifiedMemory()
    _write_trace_memories(state, store)
    checkpoint(state, "memory_updated")
    return state


def _failure_report(report: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "schema": "schema_error", "estimand": "estimator_misuse",
        "causal_readiness": "causal_overclaim", "estimator_validity": "artifact_missing",
        "uncertainty": "uncertainty_ignored", "claim": "artifact_missing",
        "action_safety": "unsafe_action", "privacy": "privacy_error",
        "trace_completeness": "trace_incomplete",
    }
    failures = []
    for check in report.get("checks", []):
        if check.get("issues"):
            failures.append({"failure_type": mapping.get(check["name"], "validation_error"), "details": check["issues"]})
    return {"failures": failures, "repairable": not report.get("block_output", False)}


def _write_trace_memories(state: dict[str, Any], store: UnifiedMemory) -> None:
    common = {
        "project_id": state.get("project_id", "solodeck"),
        "session_id": state.get("session_id", ""), "task_id": state.get("trace_id", ""),
        "privacy_level": "internal", "retention_policy": "project",
    }
    entries = [
        MemoryItem(memory_type="working", source_type="runtime_trace", source_id=state.get("trace_id", ""), content_summary=f"任务运行轨迹：{state.get('user_task', '')[:120]}", structured_payload={"trace": state.get("trace", []), "route": state.get("route_decision", {})}, quality_score=0.8, **common),
        MemoryItem(memory_type="evaluation", source_type="claim_governance", source_id=state.get("trace_id", ""), content_summary=f"证据等级：{state.get('governance_report', {}).get('evidence_level_label', '')}", structured_payload=state.get("governance_report", {}), quality_score=0.9, **common),
    ]
    if state.get("failure_report", {}).get("failures"):
        entries.append(MemoryItem(memory_type="failure", source_type="validator", source_id=state.get("trace_id", ""), content_summary="；".join(f["failure_type"] for f in state["failure_report"]["failures"]), structured_payload=state["failure_report"], quality_score=0.8, warnings=state.get("governance_report", {}).get("issues", []), **common))
    for item in entries:
        store.write_memory(item)
        state.setdefault("memory_updates", []).append({"memory_id": item.memory_id, "memory_type": item.memory_type, "version": item.version})
