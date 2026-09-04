from __future__ import annotations


def build_developer_trace_panel(state: dict) -> dict:
    selected_plan = state.get("selected_plan", {})
    pack = state.get("evidence_pack") or state.get("retrieved_memory") or {}
    evidence = pack.get("evidence") or []
    return {
        "task_spec": state.get("task_spec", {}),
        "route_decision": state.get("route_decision", {}),
        "selected_workflow": selected_plan,
        "executed_skills": state.get("selected_skills", []),
        "validation_report": state.get("validation_report", {}),
        "process_rewards": state.get("process_rewards", state.get("step_rewards", {})),
        "industrial_process_reward": state.get("industrial_process_reward", {}),
        "step_rewards": state.get("step_rewards", {}),
        "agent_rewards": state.get("agent_rewards", {}),
        "memory_updates": state.get("memory_updates", []),
        "failure_report": state.get("failure_report", {}),
        "evidence_level": state.get("evidence_level"),
        "governance_report": state.get("governance_report", {}),
        "post_writer_gate": state.get("post_writer_validation", {}),
        "skill_manifests": state.get("skill_manifests", {}),
        "skill_patches": state.get("skill_patches", []),
        "semantic_route": state.get("semantic_route", {}),
        "critic_report": state.get("critic_report", {}),
        "plan_policy_decision": state.get("plan_policy_decision", {}),
        "tool_audit": state.get("tool_audit", []),
        "claim_ledger": [_safe_claim_row(item) for item in state.get("claims", [])],
        "claim_review": state.get("claim_review", {}),
        "validation_summary": state.get("validation_summary", {}),
        "trace": state.get("trace", []),
        "retrieval": {
            "retrieval_plan": pack.get("retrieval_plan", ""),
            "selected_sources": sorted({item.get("source_type") for item in evidence if item.get("source_type")}),
            "evidence_table": [_safe_evidence_row(item) for item in evidence],
            "missing_info": pack.get("missing_info", []),
            "warnings": pack.get("warnings", []) + (state.get("retrieval_validation") or {}).get("warnings", []),
            "validation": state.get("retrieval_validation", {}),
        },
    }


def _safe_claim_row(item: dict) -> dict:
    return {
        "claim_id": item.get("claim_id"),
        "claim_type": item.get("claim_type"),
        "evidence_level": item.get("evidence_level"),
        "source_artifact_ids": item.get("source_artifact_ids", []),
        "calculation_method": item.get("calculation_method"),
        "confidence": item.get("confidence"),
        "limitations": item.get("limitations"),
        "applicable_scope": item.get("applicable_scope"),
        "status": item.get("status"),
    }


def _safe_evidence_row(item: dict) -> dict:
    """Expose provenance and scores without leaking retrieved user content."""
    return {
        "evidence_id": item.get("evidence_id"),
        "source_type": item.get("source_type"),
        "source_id": item.get("source_id"),
        "score": item.get("score"),
        "used_for": item.get("used_for"),
        "supports_claims": item.get("supports_claims", []),
        "artifact_id": item.get("artifact_id"),
        "skill_id": item.get("skill_id"),
        "validator_id": item.get("validator_id"),
        "dataset_version": item.get("dataset_version"),
        "warnings": item.get("warnings", []),
    }
