from __future__ import annotations

from typing import Any, Callable


ToolFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _tool_retrieve_memory(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    ctx = state.get("compressed_context") or {}
    return {"ok": True, "memory": ctx, "cost": 0.01}


def _tool_compile_task(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v4.compiler.enhanced_compiler import compile_with_session
    from solodeck_v3.nlp.entity_linker import link_entities

    columns = list(state["df"].columns) if state.get("df") is not None and not getattr(state["df"], "empty", True) else []
    prior = dict(state.get("linked_entities") or {})
    state["entity_link"] = link_entities(
        state["message"],
        columns,
        prior,
    )
    spec = compile_with_session(
        state["message"],
        state["df"],
        state.get("text", ""),
        state.get("compressed_context"),
        state.get("linked_entities"),
    )
    state["task_spec"] = spec.to_dict()
    return {"ok": True, "task_spec": state["task_spec"], "entity_link": state["entity_link"], "cost": 0.02}


def _tool_plan_steps(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v4.planning.task_planner import plan_task_steps

    steps = plan_task_steps(state.get("task_spec") or {}, state.get("risk_profile") or {})
    state["plan_steps"] = steps
    return {"ok": True, "steps": steps, "cost": 0.02}


def _tool_execute_analysis(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v3.planning.method_planner import generate_candidate_plans
    from solodeck_v3.planning.hypothesis_tree import generate_hypothesis_tree
    from solodeck_v3.router.router import route_task
    from solodeck_v3.runtime.skill_runtime import execute_skill_sequence
    from solodeck_v3.graph.kg_builder import build_kg_context
    from solodeck_v3.skills.schema_skill import SchemaSkill
    from solodeck_v3.skills.data_quality_skill import DataQualitySkill

    spec = state.get("task_spec") or {}
    state["task"] = spec.get("objective") or state.get("message", "")
    if state.get("reuse_cache") and state.get("artifact_cache"):
        state["artifacts"] = list(state["artifact_cache"].values())
        return {"ok": True, "reused_cache": True, "cost": 0.03}

    if not state.get("schema_summary"):
        SchemaSkill().run(state)
        DataQualitySkill().run(state)
    if not state.get("kg_context"):
        state["kg_context"] = build_kg_context(state["df"], state.get("text", ""), state.get("trace_id", ""))

    state["hypothesis_tree"] = generate_hypothesis_tree(
        spec,
        state.get("schema_summary", {"columns": list(state["df"].columns)}),
        state.get("kg_context", {}),
    )
    budget = state.get("budget") or {"max_plans": 1}
    plans = generate_candidate_plans(spec, state["hypothesis_tree"], budget)
    state["route_decision"] = route_task(
        spec,
        state.get("data_quality_report"),
        state.get("critique"),
        state.get("kg_context", {}),
    )
    plan = plans[0] if plans else {"skills": ["SchemaSkill", "ReportSkill"], "estimated_cost": 0.08}
    state["selected_plan"] = plan
    execute_skill_sequence(state, plan.get("skills", []))
    cost = float(plan.get("estimated_cost", 0.1))
    return {"ok": True, "skills": plan.get("skills", []), "cost": cost}


def _tool_validate(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v3.verification import validate_all

    state["validation_report"] = validate_all(state)
    return {"ok": True, "valid": state["validation_report"].get("valid"), "cost": 0.01}


def _tool_compose_response(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v3.skills.report_skill import ReportSkill
    from solodeck_v3.agents.writer_agent import WriterAgent
    from solodeck_v3.frontend.user_artifact_view import build_user_artifact_view
    from solodeck_v3.frontend.developer_trace_panel import build_developer_trace_panel
    from solodeck_v3.workflows.data_agent_graph import _action_cards

    if not state.get("final_report"):
        out = ReportSkill().run(state)
        state["final_report"] = out.content
        state.setdefault("artifacts", []).append({
            "id": out.artifact_id,
            "type": out.artifact_type,
            "content": out.content,
            "generated_by": "ReportSkill",
        })
    if not state.get("action_cards") and any(a.get("id") == "bootstrap_ci" for a in state.get("artifacts", [])):
        state["action_cards"] = _action_cards(state)
    state["user_artifact"] = build_user_artifact_view(state)
    state["user_artifact"] = WriterAgent().polish_user_artifact(state["user_artifact"])
    state["developer_trace"] = build_developer_trace_panel(state)
    return {"ok": True, "cost": 0.04}


def _tool_clarify(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    unresolved = (state.get("entity_link") or {}).get("unresolved") or []
    msg = args.get("message") or "请说明您指的是哪个平台或指标？例如：小红书咨询数。"
    if unresolved:
        msg = f"我需要确认指代：{', '.join(unresolved)}。{msg}"
    state["clarification"] = msg
    return {"ok": True, "clarification": msg, "cost": 0.0}


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "retrieve_memory": {"fn": _tool_retrieve_memory, "description": "Load compressed session and memory context", "cost_hint": 0.01},
    "compile_task": {"fn": _tool_compile_task, "description": "Compile user message to TaskSpec with entity linking", "cost_hint": 0.02},
    "plan_steps": {"fn": _tool_plan_steps, "description": "Decompose task into orchestrated steps", "cost_hint": 0.02},
    "execute_analysis": {"fn": _tool_execute_analysis, "description": "Run Python Skills pipeline", "cost_hint": 0.1},
    "validate_artifacts": {"fn": _tool_validate, "description": "Run verification validators", "cost_hint": 0.01},
    "compose_response": {"fn": _tool_compose_response, "description": "Generate user artifact and action cards", "cost_hint": 0.04},
    "clarify": {"fn": _tool_clarify, "description": "Ask user for clarification on ambiguous entities", "cost_hint": 0.0},
}


def list_tools() -> list[dict[str, Any]]:
    return [{"name": k, **{kk: vv for kk, vv in v.items() if kk != "fn"}} for k, v in TOOL_REGISTRY.items()]


def call_tool(name: str, state: dict[str, Any], args: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return {"ok": False, "error": f"unknown tool: {name}", "cost": 0.0}
    result = entry["fn"](state, args or {})
    result.setdefault("tool", name)
    return result
