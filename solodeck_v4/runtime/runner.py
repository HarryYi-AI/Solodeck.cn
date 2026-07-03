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
from solodeck_v4.workflows.industrial_runtime import checkpoint, finalize_industrial_runtime, initialize_industrial_state


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
    initialize_industrial_state(state)
    checkpoint(state, "input")

    compressed = compress_session_context(session)
    state["compressed_context"] = compressed
    state["linked_entities"] = session.get("linked_entities") or {}
    state["artifact_cache"] = session.get("artifact_cache") or {}

    columns = list(df.columns) if df is not None and not getattr(df, "empty", True) else []
    state["entity_link"] = link_entities(message, columns, state["linked_entities"])

    append_trace(state, "LoadSession", "Orchestrator", {"turns": len(session.get("turns", []))})
    memory_result = call_tool("retrieve_memory", state, {})
    state["cost_spent"] += float(memory_result.get("cost", 0))
    state["tool_calls"].append(memory_result)
    append_trace(state, "ToolCall", "ExecutorAgent", {"tool": "retrieve_memory", "ok": memory_result.get("ok")})

    compile_result = call_tool("compile_task", state, {})
    state["cost_spent"] += float(compile_result.get("cost", 0))
    state["tool_calls"].append(compile_result)
    append_trace(state, "ToolCall", "ExecutorAgent", {"tool": "compile_task", "ok": compile_result.get("ok")})
    append_trace(state, "CompileTask", "PlannerAgent", {"task_type": (state.get("task_spec") or {}).get("task_type")})
    task_spec = state.get("task_spec") or {}
    checkpoint(state, "compiled")
    risk = assess_risk(message, task_spec, session, state["entity_link"])
    state["risk_profile"] = risk
    state["budget"] = risk
    state["reuse_cache"] = risk.get("reuse_cache", False)

    append_trace(state, "RiskRoute", "PlannerAgent", risk)

    estimand_missing = _missing_estimand_fields(task_spec)
    if estimand_missing:
        state["clarification"] = f"要评估策略增量，还需要确认：{'、'.join(estimand_missing)}。补充后再进行因果估计。"
        result = call_tool("clarify", state, {"message": state["clarification"]})
        state["tool_calls"].append(result)
        reply = state["clarification"]
        _finalize_session(session_id, session, state, reply)
        return _package(state, reply)

    if risk.get("needs_clarification"):
        result = call_tool("clarify", state, {})
        state["cost_spent"] += result.get("cost", 0)
        state["tool_calls"].append(result)
        reply = state.get("clarification", "")
        _finalize_session(session_id, session, state, reply)
        return _package(state, reply)

    plan_result = call_tool("plan_steps", state, {})
    state["cost_spent"] += float(plan_result.get("cost", 0))
    state["tool_calls"].append(plan_result)
    append_trace(state, "ToolCall", "ExecutorAgent", {"tool": "plan_steps", "ok": plan_result.get("ok")})
    state["plan_steps"] = state.get("plan_steps") or plan_task_steps(task_spec, risk)
    tool_sequence = default_tool_sequence(risk)
    checkpoint(state, "planned")

    for tool_name in tool_sequence:
        if tool_name in {"retrieve_memory", "compile_task", "plan_steps"}:
            continue
        if session.get("cost_spent", 0) + state["cost_spent"] >= session.get("cost_budget", 1.0):
            append_trace(state, "BudgetStop", "Orchestrator", {"reason": "cost budget exceeded"})
            break
        result = call_tool(tool_name, state, {})
        state["cost_spent"] += float(result.get("cost", 0))
        state["tool_calls"].append(result)
        append_trace(state, "ToolCall", "ExecutorAgent", {"tool": tool_name, "ok": result.get("ok")})
        if tool_name == "execute_analysis":
            append_trace(state, "ExecuteSkills", "ExecutorAgent", {"skills": result.get("skills", [])})
        elif tool_name == "validate_artifacts":
            append_trace(state, "ValidateArtifacts", "VerifierAgent", {"valid": result.get("valid")})
        checkpoint(state, tool_name)

    post = validate_post_writer(state)
    state["post_writer_validation"] = post
    append_trace(state, "PostWriterValidate", "VerifierAgent", post)

    from solodeck_v4.retrieval.evidence_validator import validate_retrieval_evidence

    retrieval_val = validate_retrieval_evidence(state)
    state["retrieval_validation"] = retrieval_val
    append_trace(state, "RetrievalValidate", "VerifierAgent", retrieval_val)

    rewards = assign_process_rewards(state["trace"], state.get("validation_report") or {"issues": post.get("issues", []), "checks": []})
    state["step_rewards"] = rewards

    artifact = state.get("user_artifact") or {}
    reply = _format_reply(artifact, state)
    finalize_industrial_runtime(state, reply)
    reply = state["final_answer"]
    _finalize_session(session_id, session, state, reply)
    return _package(state, reply)


def _format_reply(artifact: dict[str, Any], state: dict[str, Any]) -> str:
    if state.get("clarification"):
        return state["clarification"]
    llm_reply = _try_llm_reply(artifact, state)
    if llm_reply:
        return llm_reply
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


def _missing_estimand_fields(task_spec: dict[str, Any]) -> list[str]:
    if task_spec.get("task_type") not in {"causal_effect_estimation", "counterfactual_analysis"}:
        return []
    missing = []
    if not task_spec.get("candidate_treatments"): missing.append("要比较的策略")
    if not task_spec.get("candidate_outcomes"): missing.append("要观察的指标")
    if not task_spec.get("unit"): missing.append("分析单位")
    if not task_spec.get("time"): missing.append("观察时间")
    return missing


def _try_llm_reply(artifact: dict[str, Any], state: dict[str, Any]) -> str:
    try:
        from solo_creator_agent.src.llm_agent import call_llm, llm_configured

        if not llm_configured():
            return ""

        task_spec = state.get("task_spec") or {}
        validation = state.get("validation_report") or {}
        risk = state.get("risk_profile") or {}
        cards = artifact.get("action_cards") or state.get("action_cards") or []
        linked_entities = (state.get("entity_link") or {}).get("linked_entities") or []
        unresolved = (state.get("entity_link") or {}).get("unresolved") or []

        prompt = """
你是 SoloDeck 的经营分析助手。请把分析结果写成自然、简洁、像真人顾问在说话的回复。
要求：
1. 全程中文，避免机械模板口吻。
2. 优先回答用户刚刚的问题，不要泛泛而谈。
3. 结构最多 4 行：
   - 结论
   - 为什么这样判断
   - 下一步建议
   - 如果证据不够，再补一句需要补什么
4. 如果当前结果接近 0 或证据很弱，不要硬下结论，要明确说“现有数据还不足以判断”，并告诉用户补什么。
5. 不要出现“高风险因果路径”“工具链”“校验器”“artifact”“API”等内部词。
6. 如果有 action cards，把它们转成自然语言建议，不要原样复制键名。
7. 回复控制在 120 个中文字以内。
"""

        payload = {
            "user_question": state.get("message", ""),
            "objective": task_spec.get("objective", ""),
            "task_type": task_spec.get("task_type", ""),
            "candidate_treatments": task_spec.get("candidate_treatments", []),
            "candidate_outcomes": task_spec.get("candidate_outcomes", []),
            "linked_entities": linked_entities,
            "unresolved_entities": unresolved,
            "result": artifact.get("result", ""),
            "confidence": artifact.get("confidence", ""),
            "limitations": artifact.get("limitations", ""),
            "action_cards": cards[:2],
            "validation_issues": validation.get("issues", []),
            "validation_valid": validation.get("valid", False),
            "high_risk": risk.get("high_risk", False),
            "reuse_cache": bool(state.get("reuse_cache")),
        }
        reply = call_llm(prompt, payload, language="中文", temperature=0.25, profile="basic").strip()
        return reply[:220]
    except Exception:
        return ""


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
        "industrial_process_reward": state.get("industrial_process_reward"),
        "cost_spent": state.get("cost_spent"),
        "session_cost_total": session.get("cost_spent"),
        "compressed_context": state.get("compressed_context"),
        "evidence_pack": state.get("evidence_pack"),
        "retrieval_validation": state.get("retrieval_validation"),
        "governance_report": state.get("governance_report"),
        "evidence_level": state.get("evidence_level"),
        "failure_report": state.get("failure_report"),
        "memory_updates": state.get("memory_updates"),
        "skill_manifests": state.get("skill_manifests"),
        "trace": state.get("trace"),
        "version": "4.0.0",
    }


def create_session(dataset_id: str | None = None, cost_budget: float = 1.0) -> dict[str, Any]:
    from solodeck_v4.session.store import create_session as _create

    return _create(dataset_id=dataset_id, cost_budget=cost_budget)
