from __future__ import annotations

import uuid
from typing import Any

from solodeck_v4.context.compressor import compress_session_context, merge_turn_into_summary
from solodeck_v4.planning.task_planner import default_tool_sequence, plan_task_steps
from solodeck_v4.risk.risk_router import assess_risk
from solodeck_v4.session.store import append_turn, get_session, update_session
from solodeck_v4.tools.registry import call_tool
from solodeck_v4.verification.post_writer import validate_post_writer
from solodeck_v3.nlp.entity_linker import link_entities
from solodeck_v3.reward.process_reward import assign_process_rewards
from solodeck_v3.runtime.trace_logger import append_trace


def run_v4_agent(
    message: str,
    df: Any,
    session_id: str,
    text: str = "",
) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"session not found: {session_id}")

    append_turn(session_id, "user", message)
    session = get_session(session_id) or session

    state: dict[str, Any] = {
        "message": message,
        "df": df,
        "text": text,
        "session_id": session_id,
        "trace_id": f"v4_{uuid.uuid4().hex[:12]}",
        "trace": [],
        "artifacts": [],
        "tool_calls": [],
        "cost_spent": 0.0,
    }

    compressed = compress_session_context(session)
    state["compressed_context"] = compressed
    state["linked_entities"] = session.get("linked_entities") or {}
    state["artifact_cache"] = session.get("artifact_cache") or {}

    columns = list(df.columns) if df is not None and not getattr(df, "empty", True) else []
    state["entity_link"] = link_entities(message, columns, state["linked_entities"])

    append_trace(state, "LoadSession", "Orchestrator", {"turns": len(session.get("turns", []))})

    call_tool("compile_task", state, {})
    task_spec = state.get("task_spec") or {}
    risk = assess_risk(message, task_spec, session, state["entity_link"])
    state["risk_profile"] = risk
    state["budget"] = risk
    state["reuse_cache"] = risk.get("reuse_cache", False)

    append_trace(state, "RiskRoute", "PlannerAgent", risk)

    if risk.get("needs_clarification"):
        result = call_tool("clarify", state, {})
        state["cost_spent"] += result.get("cost", 0)
        state["tool_calls"].append(result)
        reply = state.get("clarification", "")
        _finalize_session(session_id, session, state, reply)
        return _package(state, reply)

    state["plan_steps"] = plan_task_steps(task_spec, risk)
    tool_sequence = default_tool_sequence(risk)

    for tool_name in tool_sequence:
        if tool_name == "compile_task":
            continue
        if session.get("cost_spent", 0) + state["cost_spent"] >= session.get("cost_budget", 1.0):
            append_trace(state, "BudgetStop", "Orchestrator", {"reason": "cost budget exceeded"})
            break
        result = call_tool(tool_name, state, {})
        state["cost_spent"] += float(result.get("cost", 0))
        state["tool_calls"].append(result)
        append_trace(state, "ToolCall", "ExecutorAgent", {"tool": tool_name, "ok": result.get("ok")})

    post = validate_post_writer(state)
    state["post_writer_validation"] = post
    append_trace(state, "PostWriterValidate", "VerifierAgent", post)

    rewards = assign_process_rewards(state["trace"], state.get("validation_report") or {"issues": post.get("issues", []), "checks": []})
    state["step_rewards"] = rewards

    artifact = state.get("user_artifact") or {}
    reply = _format_reply(artifact, state)
    _finalize_session(session_id, session, state, reply)
    return _package(state, reply)


def _format_reply(artifact: dict[str, Any], state: dict[str, Any]) -> str:
    if state.get("clarification"):
        return state["clarification"]
    title = artifact.get("title") or "分析完成"
    result = artifact.get("result") or ""
    cards = artifact.get("action_cards") or state.get("action_cards") or []
    parts = [title]
    if result:
        parts.append(result[:400])
    if cards:
        first = cards[0]
        action = first.get("title") or first.get("action") or ""
        if action:
            parts.append(f"建议：{action}")
    if state.get("risk_profile", {}).get("high_risk"):
        parts.append("（高风险因果问题已走深度校验路径）")
    if state.get("reuse_cache"):
        parts.append("（复用上轮分析结果以降低成本）")
    return "\n".join(parts)


def _finalize_session(session_id: str, session: dict[str, Any], state: dict[str, Any], reply: str) -> None:
    append_turn(session_id, "assistant", reply, {
        "trace_id": state.get("trace_id"),
        "cost": state.get("cost_spent"),
        "tools": [t.get("tool") for t in state.get("tool_calls", [])],
    })
    linked = {}
    for item in (state.get("entity_link") or {}).get("linked_entities") or []:
        if item.get("mention") and item.get("column"):
            linked[item["mention"]] = item["column"]

    cache = dict(session.get("artifact_cache") or {})
    for art in state.get("artifacts") or []:
        if art.get("id"):
            cache[art["id"]] = art

    summary = merge_turn_into_summary(session, state.get("message", ""), reply[:120])
    update_session(
        session_id,
        linked_entities={**session.get("linked_entities", {}), **linked},
        last_task_spec=state.get("task_spec"),
        last_trace_id=state.get("trace_id"),
        artifact_cache=cache,
        compressed_summary=summary,
        cost_spent=float(session.get("cost_spent", 0)) + float(state.get("cost_spent", 0)),
        plan_history=(session.get("plan_history") or []) + [{"trace_id": state.get("trace_id"), "steps": state.get("plan_steps", [])}],
    )


def _package(state: dict[str, Any], reply: str) -> dict[str, Any]:
    session = get_session(state["session_id"]) or {}
    return {
        "session_id": state["session_id"],
        "trace_id": state.get("trace_id"),
        "reply": reply,
        "user_artifact": state.get("user_artifact"),
        "developer_trace": state.get("developer_trace"),
        "task_spec": state.get("task_spec"),
        "plan_steps": state.get("plan_steps"),
        "tool_calls": state.get("tool_calls"),
        "risk_profile": state.get("risk_profile"),
        "validation_report": state.get("validation_report"),
        "post_writer_validation": state.get("post_writer_validation"),
        "step_rewards": state.get("step_rewards"),
        "cost_spent": state.get("cost_spent"),
        "session_cost_total": session.get("cost_spent"),
        "compressed_context": state.get("compressed_context"),
        "trace": state.get("trace"),
        "version": "4.0.0",
    }


def create_session(dataset_id: str | None = None, cost_budget: float = 1.0) -> dict[str, Any]:
    from solodeck_v4.session.store import create_session as _create

    return _create(dataset_id=dataset_id, cost_budget=cost_budget)
