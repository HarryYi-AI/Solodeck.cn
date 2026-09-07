from __future__ import annotations

import re
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
from solodeck_v4.observability import agent_observation, record_agent_scores, update_observation


def run_v4_agent(
    message: str,
    df: Any,
    session_id: str,
    text: str = "",
) -> dict[str, Any]:
    trace_id = f"v4_{uuid.uuid4().hex[:12]}"
    with agent_observation(message, session_id, trace_id, df) as observation:
        result = _run_v4_agent(message, df, session_id, text=text, trace_id=trace_id)
        update_observation(
            observation,
            output={
                "status": "completed",
                "reply_length": len(result.get("reply") or ""),
                "evidence_level": result.get("evidence_level"),
            },
            metadata={
                "task_type": (result.get("task_spec") or {}).get("task_type"),
                "route_layer": (result.get("semantic_route") or {}).get("layer"),
                "critic_decision": (result.get("critic_report") or {}).get("decision"),
                "tool_count": len(result.get("tool_audit") or []),
                "cost_spent": result.get("cost_spent"),
            },
        )
        record_agent_scores(observation, result)
        try:
            from solodeck_eval.trajectory import log_agent_result

            rows = log_agent_result(result, message)
            result["trajectory_log"] = {"step_count": len(rows), "schema_version": "1.0"}
        except Exception as exc:
            result["trajectory_log"] = {"step_count": 0, "error": type(exc).__name__, "schema_version": "1.0"}
        return result


def _run_v4_agent(
    message: str,
    df: Any,
    session_id: str,
    *,
    text: str,
    trace_id: str,
) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"session not found: {session_id}")

    append_turn(session_id, "user", message)
    session = get_session(session_id) or session

    state_command = execute_state_command(message, session)
    if state_command is not None:
        append_turn(session_id, "assistant", state_command["reply"], {
            "operation": "analytical_state_restore",
            "state_id": state_command["state_id"],
        })
        update_session(
            session_id,
            last_state_id=state_command["state_id"],
            state_history=(session.get("state_history") or []) + [{
                "state_id": state_command["state_id"],
                "task_id": (state_command.get("analytical_state") or {}).get("task_id"),
                "trace_id": trace_id,
                "summary": state_command["reply"][:120],
            }],
        )
        return {"session_id": session_id, "trace_id": trace_id, **state_command, "version": "4.0.0"}

    state: dict[str, Any] = {
        "message": message,
        "df": df,
        "text": text,
        "session_id": session_id,
        "trace_id": trace_id,
        "trace": [],
        "artifacts": [],
        "tool_calls": [],
        "cost_spent": 0.0,
        "project_id": session.get("project_id", "solodeck"),
        "parent_state_id": session.get("last_state_id"),
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

    from solodeck_v4.critics import evaluate_run

    state["critic_report"] = evaluate_run(state, phase="postwrite").to_dict()
    while (
        state["critic_report"].get("decision") == "repair"
        and int(state.get("revision_number", 0)) < min(2, int(state.get("max_revisions", 2)))
    ):
        state["revision_number"] = int(state.get("revision_number", 0)) + 1
        state.setdefault("critique", {})["needs_repair"] = True
        state["critique"]["repair_directives"] = state["critic_report"].get("repair_directives", [])
        append_trace(state, "ReflectRepair", "VerifierAgent", {
            "revision": state["revision_number"],
            "critic_score": state["critic_report"].get("overall_score"),
            "directives": state["critique"]["repair_directives"],
        })
        for tool_name in ("execute_analysis", "validate_artifacts", "compose_response"):
            result = call_tool(tool_name, state, {"repair": True})
            state["cost_spent"] += float(result.get("cost", 0))
            state["tool_calls"].append(result)
            append_trace(state, "ToolCall", "ExecutorAgent", {"tool": tool_name, "repair": True, "ok": result.get("ok")})
        state["post_writer_validation"] = validate_post_writer(state)
        state["critic_report"] = evaluate_run(state, phase="postwrite").to_dict()
        if state["critic_report"].get("decision") == "block":
            break

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
    descriptive_reply = _format_descriptive_reply(artifact, state)
    if descriptive_reply:
        return descriptive_reply
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
    return "\n".join(parts)


def execute_state_command(message: str, session: dict[str, Any], store: Any | None = None) -> dict[str, Any] | None:
    """Execute explicit state operations from persisted snapshots, never chat replay."""
    normalized = (message or "").lower()
    restore_requested = any(term in normalized for term in ("回到", "恢复", "rollback", "退回"))
    compare_requested = any(term in normalized for term in ("比较", "对比", "diff"))
    if not restore_requested and not (compare_requested and "之前" in normalized):
        return None

    from solodeck_runtime.persistence import StateStore

    store = store or StateStore()
    history = [item.get("state_id") for item in session.get("state_history") or [] if item.get("state_id")]
    current_id = session.get("last_state_id") or (history[-1] if history else None)
    match = re.search(r"\bstate_[A-Za-z0-9_-]{8,128}\b", message)
    explicit = match.group(0) if match else None
    target_id = explicit or (history[-2] if len(history) >= 2 else None)
    if not current_id or not target_id:
        return {
            "reply": "还没有可恢复的历史分析状态。请先完成至少两轮分析。",
            "state_id": current_id,
            "analytical_state": None,
            "state_diff": {},
        }

    differences = store.diff(target_id, current_id)
    restored = store.rollback(current_id, target_id) if restore_requested else store.restore(current_id)
    changed = "、".join(list(differences)[:5]) or "没有实质变化"
    action = "已恢复到指定分析状态" if restore_requested else "已比较两个分析状态"
    return {
        "reply": f"{action}。变化项：{changed}。后续分析将从该状态继续。",
        "state_id": restored.state_id,
        "analytical_state": restored.to_dict(),
        "state_diff": differences,
    }


def _format_descriptive_reply(artifact: dict[str, Any], state: dict[str, Any]) -> str:
    comparison = next((a.get("content", {}) for a in state.get("artifacts", []) if a.get("id") == "descriptive_comparison"), {})
    if not comparison.get("ranking"):
        return ""
    result = artifact.get("result") or ""
    cards = artifact.get("action_cards") or state.get("action_cards") or []
    lines = [result]
    if cards:
        lines.append(f"下一步：{cards[0].get('action', cards[0].get('title', ''))}")
        if len(cards) > 1:
            lines.append(f"同时：{cards[1].get('action', cards[1].get('title', ''))}")
    lines.append(artifact.get("limitations") or "")
    return "\n".join(line for line in lines if line)


def _missing_estimand_fields(task_spec: dict[str, Any]) -> list[str]:
    if task_spec.get("task_type") not in {"causal_effect_estimation", "counterfactual_analysis"}:
        return []
    missing = []
    if not task_spec.get("candidate_treatments"): missing.append("要比较的策略")
    if not task_spec.get("candidate_outcomes"): missing.append("要观察的指标")
    if not task_spec.get("unit"): missing.append("分析单位")
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
4. 回答前先使用 Python Skills 已生成的结构化计算工件。只要能比较指标大小，就必须先给出排序、差值或倍数，不能用因果限制代替描述性回答。
5. 明确区分三层：数值足够时给【描述性结论】；可能原因写成【待验证解释】；只有用户询问导致、归因或增量时才讨论【因果验证】。
6. 证据弱只限制归因强度，不得抹掉已经算出的描述性事实。
7. 不要出现“高风险因果路径”“工具链”“校验器”“artifact”“API”等内部词。
8. 如果有 action cards，把它们转成自然语言建议，不要原样复制键名。
9. 回复控制在 180 个中文字以内。
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
            "descriptive_comparison": next((a.get("content", {}) for a in state.get("artifacts", []) if a.get("id") == "descriptive_comparison"), {}),
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
    from solodeck_runtime.bridge import finalize_runtime_protocol

    finalize_runtime_protocol(state, reply)
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
    updated_session = update_session(
        session_id,
        linked_entities={**session.get("linked_entities", {}), **linked},
        last_task_spec=state.get("task_spec"),
        last_trace_id=state.get("trace_id"),
        artifact_cache=cache,
        compressed_summary=summary,
        cost_spent=float(session.get("cost_spent", 0)) + float(state.get("cost_spent", 0)),
        plan_history=(session.get("plan_history") or []) + [{"trace_id": state.get("trace_id"), "steps": state.get("plan_steps", [])}],
        last_state_id=state.get("state_id"),
        state_history=(session.get("state_history") or []) + [{
            "state_id": state.get("state_id"),
            "task_id": state.get("task_id"),
            "trace_id": state.get("trace_id"),
            "summary": reply[:120],
        }],
    )
    try:
        from solodeck_v4.decision_memory import DecisionMemoryService

        state["decision_memory_update"] = DecisionMemoryService().record_decision(
            state,
            user_id=str(updated_session.get("user_id") or "anonymous"),
            project_id=str(updated_session.get("project_id") or "solodeck"),
            data_source_ids=[str(updated_session.get("dataset_id"))] if updated_session.get("dataset_id") else [],
        )
    except Exception as exc:
        state["decision_memory_update"] = {"recorded": False, "error": type(exc).__name__}


def _package(state: dict[str, Any], reply: str) -> dict[str, Any]:
    session = get_session(state["session_id"]) or {}
    from solodeck_runtime.result_view import build_result_view

    return {
        "session_id": state["session_id"],
        "trace_id": state.get("trace_id"),
        "reply": reply,
        "user_artifact": state.get("user_artifact"),
        "developer_trace": state.get("developer_trace"),
        "task_spec": state.get("task_spec"),
        "task_spec_v2": state.get("task_spec_v2"),
        "data_grounding": state.get("data_grounding"),
        "analysis_workflow": state.get("analysis_workflow"),
        "workflow_validation": state.get("workflow_validation"),
        "analytical_state": state.get("analytical_state"),
        "state_id": state.get("state_id"),
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
        "critic_report": state.get("critic_report"),
        "semantic_route": state.get("semantic_route"),
        "plan_policy_decision": state.get("plan_policy_decision"),
        "plan_utility_update": state.get("plan_utility_update"),
        "claims": state.get("claims"),
        "tool_audit": state.get("tool_audit"),
        "evidence_level": state.get("evidence_level"),
        "failure_report": state.get("failure_report"),
        "memory_updates": state.get("memory_updates"),
        "decision_memory_update": state.get("decision_memory_update"),
        "skill_manifests": state.get("skill_manifests"),
        "selected_skills": list(dict.fromkeys(state.get("selected_skills") or [])),
        "trace": state.get("trace"),
        "result_view": build_result_view(state),
        "version": "4.0.0",
    }


def create_session(dataset_id: str | None = None, cost_budget: float = 1.0) -> dict[str, Any]:
    from solodeck_v4.session.store import create_session as _create

    return _create(dataset_id=dataset_id, cost_budget=cost_budget)
