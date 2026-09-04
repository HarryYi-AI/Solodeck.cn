from __future__ import annotations

from typing import Any, Callable, TypedDict

from solodeck_v3.runtime.trace_logger import append_trace
from solodeck_v4.governance import govern_claims, run_governance_suite
from solodeck_v4.risk.risk_router import assess_risk
from solodeck_v4.tools.registry import call_tool
from solodeck_v4.verification.post_writer import validate_post_writer
from solodeck_v4.workflows.industrial_runtime import checkpoint, finalize_industrial_runtime, initialize_industrial_state


class IndustrialAgentState(TypedDict, total=False):
    message: str
    df: Any
    text: str
    session_id: str
    trace_id: str
    task_spec: dict[str, Any]
    session_context: dict[str, Any]
    memory_context: dict[str, Any]
    evidence_pack: dict[str, Any]
    route_decision: dict[str, Any]
    risk_profile: dict[str, Any]
    plan_steps: list[dict[str, Any]]
    budget: dict[str, Any]
    entity_link: dict[str, Any]
    semantic_route: dict[str, Any]
    linked_entities: dict[str, Any]
    artifact_cache: dict[str, Any]
    compressed_context: dict[str, Any]
    selected_skills: list[str]
    selected_plan: dict[str, Any]
    schema_summary: dict[str, Any]
    data_quality_report: dict[str, Any]
    kg_context: dict[str, Any]
    causal_context: dict[str, Any]
    hypothesis_tree: dict[str, Any]
    artifacts: list[dict[str, Any]]
    skill_manifests: dict[str, Any]
    validators: list[dict[str, Any]]
    validation_report: dict[str, Any]
    post_writer_validation: dict[str, Any]
    governance_report: dict[str, Any]
    critic_report: dict[str, Any]
    critique: dict[str, Any]
    evidence_level: int
    draft_answer: str
    final_answer: str
    revision_number: int
    max_revisions: int
    trace: list[dict[str, Any]]
    failure_report: dict[str, Any]
    memory_updates: list[dict[str, Any]]
    skill_patches: list[dict[str, Any]]
    industrial_process_reward: dict[str, Any]
    final_report: dict[str, Any]
    action_cards: list[dict[str, Any]]
    user_artifact: dict[str, Any]
    developer_trace: dict[str, Any]


def build_industrial_graph() -> Any | None:
    """Build the production state graph; return None when LangGraph is unavailable."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None

    graph = StateGraph(IndustrialAgentState)
    nodes = {
        "CompileTask": _compile,
        "RetrieveMemory": _retrieve,
        "RouteTools": _route,
        "PlanSteps": _plan,
        "ExecuteSkills": _execute,
        "ValidateArtifacts": _validate,
        "GenerateDraft": _draft,
        "PostWriterGate": _gate,
        "ReflectRepair": _repair,
        "FinalOutput": _final,
        "WriteTrace": _write_trace,
        "UpdateMemory": _update_memory,
        "UpdateSkillUtility": _update_skill_utility,
    }
    for name, fn in nodes.items():
        graph.add_node(name, _observed_node(name, fn))
    graph.set_entry_point("CompileTask")
    graph.add_edge("CompileTask", "RetrieveMemory")
    graph.add_edge("RetrieveMemory", "RouteTools")
    graph.add_edge("RouteTools", "PlanSteps")
    graph.add_edge("PlanSteps", "ExecuteSkills")
    graph.add_edge("ExecuteSkills", "ValidateArtifacts")
    graph.add_edge("ValidateArtifacts", "GenerateDraft")
    graph.add_edge("GenerateDraft", "PostWriterGate")
    graph.add_conditional_edges("PostWriterGate", _gate_route, {"repair": "ReflectRepair", "finish": "FinalOutput"})
    graph.add_edge("ReflectRepair", "ExecuteSkills")
    graph.add_edge("FinalOutput", "WriteTrace")
    graph.add_edge("WriteTrace", "UpdateMemory")
    graph.add_edge("UpdateMemory", "UpdateSkillUtility")
    graph.add_edge("UpdateSkillUtility", END)
    return graph.compile()


def run_industrial_graph(state: dict[str, Any]) -> dict[str, Any]:
    initialize_industrial_state(state)
    graph = build_industrial_graph()
    if graph is not None:
        from solodeck_v4.observability import get_langgraph_callback

        config: dict[str, Any] = {
            "configurable": {"thread_id": state["trace_id"]},
            "recursion_limit": 32,
        }
        callback = get_langgraph_callback()
        if callback is not None:
            config["callbacks"] = [callback]
        return graph.invoke(state, config=config)
    for node in (_compile, _retrieve, _route, _plan, _execute, _validate, _draft, _gate):
        state = node(state)
    while _gate_route(state) == "repair":
        state = _repair(state)
        for node in (_execute, _validate, _draft, _gate):
            state = node(state)
    for node in (_final, _write_trace, _update_memory, _update_skill_utility):
        state = node(state)
    return state


def _observed_node(name: str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        from solodeck_v4.observability import update_observation, workflow_observation

        with workflow_observation(name, state) as observation:
            result = fn(state)
            update_observation(
                observation,
                output={
                    "artifacts": len(result.get("artifacts") or []),
                    "revision": int(result.get("revision_number", 0)),
                },
            )
            return result

    wrapped.__name__ = f"observed_{fn.__name__.lstrip('_')}"
    return wrapped


def _compile(state: dict[str, Any]) -> dict[str, Any]:
    initialize_industrial_state(state)
    result = call_tool("compile_task", state, {})
    append_trace(state, "CompileTask", "PlannerAgent", {"ok": result.get("ok")})
    checkpoint(state, "compile_task")
    return state


def _retrieve(state: dict[str, Any]) -> dict[str, Any]:
    result = call_tool("retrieve_memory", state, {})
    append_trace(state, "RetrieveMemory", "RetrieverAgent", {"ok": result.get("ok"), "evidence": len((state.get("evidence_pack") or {}).get("evidence", []))})
    return state


def _route(state: dict[str, Any]) -> dict[str, Any]:
    state["risk_profile"] = assess_risk(state.get("message", ""), state.get("task_spec", {}), state.get("session_context", {}), state.get("entity_link", {}))
    state["route_decision"] = state["risk_profile"]
    state["budget"] = state["risk_profile"]
    append_trace(state, "RouteTools", "PlannerAgent", state["risk_profile"])
    return state


def _plan(state: dict[str, Any]) -> dict[str, Any]:
    call_tool("plan_steps", state, {})
    append_trace(state, "PlanSteps", "PlannerAgent", {"steps": len(state.get("plan_steps", []))})
    return state


def _execute(state: dict[str, Any]) -> dict[str, Any]:
    result = call_tool("execute_analysis", state, {})
    append_trace(state, "ExecuteSkills", "ExecutorAgent", {"skills": result.get("skills", [])})
    checkpoint(state, "execute_skills")
    return state


def _validate(state: dict[str, Any]) -> dict[str, Any]:
    result = call_tool("validate_artifacts", state, {})
    append_trace(state, "ValidateArtifacts", "VerifierAgent", {"valid": result.get("valid")})
    return state


def _draft(state: dict[str, Any]) -> dict[str, Any]:
    call_tool("compose_response", state, {})
    user = state.get("user_artifact") or {}
    state["draft_answer"] = "\n".join(str(value) for key, value in user.items() if key in {"title", "result", "limitations"} and value)
    append_trace(state, "GenerateDraft", "WriterAgent", {"characters": len(state["draft_answer"])})
    return state


def _gate(state: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v4.critics import evaluate_run

    state["post_writer_validation"] = validate_post_writer(state)
    state["governance_report"] = run_governance_suite(state)
    state["critic_report"] = evaluate_run(state, phase="postwrite").to_dict()
    state["validators"] = state["governance_report"]["checks"]
    append_trace(state, "PostWriterGate", "VerifierAgent", {"valid": state["governance_report"]["valid"]})
    return state


def _gate_route(state: dict[str, Any]) -> str:
    critic_decision = state.get("critic_report", {}).get("decision", "pass")
    if state.get("governance_report", {}).get("valid") and critic_decision == "pass":
        return "finish"
    if int(state.get("revision_number", 0)) >= int(state.get("max_revisions", 2)):
        return "finish"
    if state.get("governance_report", {}).get("block_output"):
        return "finish"
    return "repair"


def _repair(state: dict[str, Any]) -> dict[str, Any]:
    state["revision_number"] = int(state.get("revision_number", 0)) + 1
    state.setdefault("critique", {})["downgraded_to_validation"] = True
    state["critique"]["needs_repair"] = True
    state["critique"]["repair_directives"] = state.get("critic_report", {}).get("repair_directives", [])
    append_trace(state, "ReflectRepair", "VerifierAgent", {"revision": state["revision_number"], "issues": state.get("governance_report", {}).get("issues", [])})
    return state


def _final(state: dict[str, Any]) -> dict[str, Any]:
    governed = govern_claims(state, state.get("draft_answer", ""))
    state["governance_report"] = governed
    state["final_answer"] = governed["answer"]
    append_trace(state, "FinalOutput", "WriterAgent", {"evidence_level": governed["evidence_level"]})
    return state


def _write_trace(state: dict[str, Any]) -> dict[str, Any]:
    checkpoint(state, "final_output")
    append_trace(state, "WriteTrace", "Orchestrator", {"trace_id": state.get("trace_id")})
    return state


def _update_memory(state: dict[str, Any]) -> dict[str, Any]:
    finalize_industrial_runtime(state, state.get("final_answer", ""))
    append_trace(state, "UpdateMemory", "RetrieverAgent", {"updates": len(state.get("memory_updates", []))})
    return state


def _update_skill_utility(state: dict[str, Any]) -> dict[str, Any]:
    append_trace(state, "UpdateSkillUtility", "Orchestrator", {"patches": len(state.get("skill_patches", [])), "reward": state.get("industrial_process_reward", {}).get("total")})
    checkpoint(state, "complete")
    return state
