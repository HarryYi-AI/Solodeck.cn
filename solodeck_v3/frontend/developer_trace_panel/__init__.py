from __future__ import annotations


def build_developer_trace_panel(state: dict) -> dict:
    selected_plan = state.get("selected_plan", {})
    return {
        "task_spec": state.get("task_spec", {}),
        "route_decision": state.get("route_decision", {}),
        "selected_workflow": selected_plan,
        "executed_skills": state.get("selected_skills", []),
        "validation_report": state.get("validation_report", {}),
        "process_rewards": state.get("process_rewards", state.get("step_rewards", {})),
        "step_rewards": state.get("step_rewards", {}),
        "agent_rewards": state.get("agent_rewards", {}),
        "memory_updates": state.get("memory_updates", []),
        "failure_report": state.get("failure_report", {}),
        "claim_review": state.get("claim_review", {}),
        "validation_summary": state.get("validation_summary", {}),
        "trace": state.get("trace", []),
    }
