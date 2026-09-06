from __future__ import annotations

from typing import Any

from .contracts import ToolContract, dispatch_tool


def _tool_retrieve_memory(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v4.retrieval.retrieval_router import retrieve_memory
    from solodeck_v4.session.store import get_session

    session = get_session(state.get("session_id", "")) or {}
    task_spec = state.get("task_spec") or session.get("last_task_spec") or {}
    pack = retrieve_memory(
        state.get("message", ""),
        task_spec,
        entity_link=state.get("entity_link"),
        session=session,
        artifact_cache=state.get("artifact_cache"),
    )
    state["evidence_pack"] = pack
    state["retrieved_memory"] = pack
    _apply_retrieval_hints(state, pack)
    return {"ok": True, "evidence_pack": pack, "cost": 0.02}


def _apply_retrieval_hints(state: dict[str, Any], pack: dict[str, Any]) -> None:
    schema_hits = [e for e in pack.get("evidence", []) if e.get("source_type") == "schema"]
    if schema_hits and not state.get("schema_summary"):
        cols = []
        for hit in schema_hits:
            col = (hit.get("meta") or {}).get("column")
            if col:
                cols.append(col)
        if cols:
            state["schema_summary"] = {"columns": list(dict.fromkeys(cols))}
    if pack.get("warnings"):
        state.setdefault("retrieval_warnings", []).extend(pack["warnings"])


def _tool_compile_task(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v4.compiler.enhanced_compiler import compile_with_session
    from solodeck_v4.routing import apply_route_to_spec, route_task_intent
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
    semantic_route = route_task_intent(
        state["message"],
        columns,
        baseline_task_type=spec.task_type,
    )
    spec = apply_route_to_spec(spec, semantic_route, columns)
    state["semantic_route"] = semantic_route.to_dict()
    state["task_spec"] = spec.to_dict()
    from solodeck_runtime.bridge import prepare_runtime_protocol

    prepare_runtime_protocol(state)
    from solodeck_v4.retrieval.retrieval_router import retrieve_memory
    from solodeck_v4.session.store import get_session

    session = get_session(state.get("session_id", "")) or {}
    pack = retrieve_memory(
        state["message"],
        state["task_spec"],
        entity_link=state.get("entity_link"),
        session=session,
        artifact_cache=state.get("artifact_cache"),
    )
    state["evidence_pack"] = pack
    state["retrieved_memory"] = pack
    _apply_retrieval_hints(state, pack)
    return {
        "ok": True,
        "task_spec": state["task_spec"],
        "task_spec_v2": state["task_spec_v2"],
        "data_grounding": state["data_grounding"],
        "analysis_workflow": state["analysis_workflow"],
        "workflow_validation": state["workflow_validation"],
        "entity_link": state["entity_link"],
        "semantic_route": state["semantic_route"],
        "evidence_pack": pack,
        "cost": 0.02 if semantic_route.layer != "L3" else 0.08,
    }


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
    from solodeck_v4.evolution import AdaptivePlanPolicy

    spec = state.get("task_spec") or {}
    state["task"] = spec.get("objective") or state.get("message", "")
    if state.get("force_causal_readiness") and "causal_readiness" not in spec.get("expected_artifacts", []):
        spec.setdefault("expected_artifacts", []).append("causal_readiness")
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
    candidate_plans = plans
    previous_plan_id = (state.get("selected_plan") or {}).get("plan_id")
    if state.get("critique", {}).get("needs_repair") and previous_plan_id and len(plans) > 1:
        alternatives = [item for item in plans if item.get("plan_id") != previous_plan_id]
        if alternatives:
            candidate_plans = alternatives
    plan, policy_decision = AdaptivePlanPolicy().select_plan(
        candidate_plans,
        task_type=spec.get("task_type", "descriptive_analysis"),
        project_id=state.get("project_id", "solodeck"),
    )
    state["selected_plan"] = plan
    state["plan_policy_decision"] = policy_decision
    execute_skill_sequence(state, plan.get("skills", []))
    cost = float(plan.get("estimated_cost", 0.1))
    return {"ok": True, "skills": plan.get("skills", []), "plan_policy": policy_decision, "cost": cost}


def _tool_validate(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from solodeck_v3.verification import validate_all
    from solodeck_v4.critics import evaluate_run

    bootstrap = next((artifact.get("content", {}) for artifact in state.get("artifacts", []) if artifact.get("id") == "bootstrap_ci"), {})
    interval = bootstrap.get("ci_95") or []
    if len(interval) == 2 and interval[0] is not None and interval[1] is not None and float(interval[0]) <= 0 <= float(interval[1]):
        state.setdefault("critique", {})["unstable_ci"] = True
        state["critique"]["downgraded_to_validation"] = True
    state["validation_report"] = validate_all(state)
    from solodeck_runtime.verifier import ActiveVerifier

    active_checks = []
    frame = state.get("df")
    if frame is not None and not getattr(frame, "empty", True):
        rate_specs = {
            "conversion_rate": ("conversions", next((name for name in ("visitors", "clicks", "consultations", "views") if name in frame.columns), "")),
            "consultation_rate": ("consultations", next((name for name in ("views", "impressions", "visitors") if name in frame.columns), "")),
        }
        outcome = ((state.get("task_spec") or {}).get("candidate_outcomes") or [None])[0]
        numerator, denominator = rate_specs.get(outcome, ("", ""))
        if numerator and denominator and numerator in frame.columns:
            reported = frame[outcome] if outcome in frame.columns else None
            active_checks.append(ActiveVerifier().inspect_rate(frame, numerator, denominator, reported))
    estimate_artifacts = [item for item in state.get("artifacts", []) if item.get("id") in {"bootstrap_ci", "regression_effect", "did_effect"}]
    if len(estimate_artifacts) > 1:
        active_checks.append(ActiveVerifier().compare_artifacts(
            estimate_artifacts, ("effect_estimate", "ate", "adjusted_effect", "did_effect")
        ))
    active_issues = [issue for check in active_checks for issue in check.get("issues", [])]
    state["active_verification"] = {"valid": not active_issues, "checks": active_checks, "issues": active_issues}
    if active_issues:
        state["validation_report"]["valid"] = False
        state["validation_report"].setdefault("issues", []).extend(active_issues)
    state["critic_report"] = evaluate_run(state, phase="prewrite").to_dict()
    return {
        "ok": True,
        "valid": state["validation_report"].get("valid") and state["critic_report"]["decision"] != "block",
        "critic_score": state["critic_report"]["overall_score"],
        "critic_decision": state["critic_report"]["decision"],
        "cost": 0.01,
    }


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
    if not state.get("action_cards"):
        comparison = next((a.get("content", {}) for a in state.get("artifacts", []) if a.get("id") == "descriptive_comparison"), {})
        if comparison.get("question_type") == "descriptive_comparison":
            state["action_cards"] = _descriptive_action_cards(comparison)
    state["user_artifact"] = build_user_artifact_view(state)
    state["user_artifact"] = WriterAgent().polish_user_artifact(state["user_artifact"])
    from solodeck_v4.evidence import build_claim_records
    state["claims"] = build_claim_records(state)
    from solodeck_v4.retrieval.evidence_validator import validate_retrieval_evidence

    state["retrieval_validation"] = validate_retrieval_evidence(state)
    state["developer_trace"] = build_developer_trace_panel(state)
    return {"ok": True, "cost": 0.04}


def _descriptive_action_cards(comparison: dict[str, Any]) -> list[dict[str, Any]]:
    if comparison.get("status") == "insufficient_comparison":
        raw_denominator = comparison.get("denominator") or "访客数或咨询数"
        denominator = {
            "visitors": "访客数",
            "clicks": "点击数",
            "sessions": "访问次数",
            "consultations": "咨询数",
            "views": "播放量",
            "impressions": "曝光量",
        }.get(raw_denominator, raw_denominator)
        return [
            {
                "title": "先补齐同口径分母",
                "action": f"为每个平台补充{denominator}和成交数；缺失值保持为空，不要填成 0。",
                "priority": "补数据",
                "evidence": "当前只有部分平台可以计算转化率，无法公平排名。",
            }
        ]
    if comparison.get("status") == "tie":
        return [
            {
                "title": "先核对全零与缺失值",
                "action": "确认各平台统计周期一致，并补齐访客、咨询和成交数据后重新比较。",
                "priority": "核对",
                "evidence": "当前各平台数值完全相同，无法区分优先级。",
            }
        ]
    best = comparison["best"]
    worst = comparison["worst"]
    metric = comparison.get("metric_label", "目标指标")
    group_label = comparison.get("group_label", "分组")
    if group_label == "标题风格":
        return [
            {
                "title": f"优先使用{best['group']}标题",
                "action": f"下一批同类内容优先采用{best['group']}写法，并继续记录每条内容的{metric}。",
                "priority": "采用",
                "evidence": f"当前数据中，{best['group']}的平均{metric}排名第一。",
            },
            {
                "title": "保留内容口径",
                "action": "比较标题时沿用相近主题和内容体量，避免把题材差异混进标题结果。",
                "priority": "记录",
                "evidence": "统一记录口径可以让后续排名更有参考价值。",
            },
        ]
    if group_label in {"内容", "产品"}:
        return [
            {
                "title": f"复盘高{metric}{group_label}",
                "action": f"先检查“{best['group']}”的主题、入口和发布时间，提炼一个可复用变量，不要整条照搬。",
                "priority": "复盘",
                "evidence": f"当前上传数据中，该{group_label}的{metric}合计最高。",
            },
            {
                "title": "核对收入归属",
                "action": "确认同一内容的收入是否被多条记录重复归集，并补充成本后再比较净收益。",
                "priority": "核对",
                "evidence": "当前排名使用数据中的收入合计，尚未扣除成本或重复归属。",
            },
        ]
    second_action = "补充成本、退款和订单来源，比较净收益而不只看收入。" if comparison.get("metric") == "revenue" else "补充曝光、点击、下单和支付数据，定位损失发生在哪一步。"
    return [
        {
            "title": f"保持 {best['group']} 的有效做法",
            "action": f"先维持当前投入，并继续记录{metric}；新增预算采用小步增加，避免仅凭一次排序全面转移。",
            "priority": "继续",
            "evidence": f"当前上传数据中，{best['group']} 的 {metric} 排名第一。",
        },
        {
            "title": f"排查 {worst['group']} 的转化漏斗",
            "action": second_action,
            "priority": "排查",
            "evidence": f"当前上传数据中，{worst['group']} 的 {metric} 排名末位。",
        },
        {
            "title": "验证平台差异的来源",
            "action": "选择相近商品、活动力度和观察周期做一次小范围配对测试，再决定是否调整预算。",
            "priority": "验证",
            "evidence": "当前结论是直接数值比较，尚未拆分平台、活动和流量结构的影响。",
        },
    ]


def _tool_clarify(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    unresolved = (state.get("entity_link") or {}).get("unresolved") or []
    msg = args.get("message") or "请说明您指的是哪个平台或指标？例如：小红书咨询数。"
    if unresolved:
        msg = f"我需要确认指代：{', '.join(unresolved)}。{msg}"
    state["clarification"] = msg
    return {"ok": True, "clarification": msg, "cost": 0.0}


TOOL_REGISTRY: dict[str, ToolContract] = {
    "retrieve_memory": ToolContract("retrieve_memory", _tool_retrieve_memory, "Retrieve schema/KG/artifact/session/text evidence", "memory:read", 5.0, 0.02, required_state=("message",)),
    "compile_task": ToolContract("compile_task", _tool_compile_task, "Compile a user goal into a schema-valid TaskSpec", "schema:read", 20.0, 0.02, required_state=("message", "df")),
    "plan_steps": ToolContract("plan_steps", _tool_plan_steps, "Decompose TaskSpec into executable steps", "plan:write", 3.0, 0.02, required_state=("task_spec",)),
    "execute_analysis": ToolContract("execute_analysis", _tool_execute_analysis, "Execute deterministic Python Skills", "analysis:execute", 45.0, 0.1, required_state=("task_spec", "df"), side_effects=("artifacts", "skill_manifests")),
    "validate_artifacts": ToolContract("validate_artifacts", _tool_validate, "Validate statistical, causal, privacy and trace claims", "artifact:validate", 10.0, 0.01, required_state=("artifacts",), side_effects=("validation_report", "critic_report")),
    "compose_response": ToolContract("compose_response", _tool_compose_response, "Compose claims and action cards from validated artifacts", "response:write", 20.0, 0.04, required_state=("artifacts",), side_effects=("user_artifact",)),
    "clarify": ToolContract("clarify", _tool_clarify, "Ask one bounded clarification question", "response:write", 3.0, 0.0, side_effects=("clarification",)),
}


def list_tools() -> list[dict[str, Any]]:
    return [contract.public_schema() for contract in TOOL_REGISTRY.values()]


def call_tool(name: str, state: dict[str, Any], args: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = TOOL_REGISTRY.get(name)
    if contract is None:
        return {"ok": False, "error": f"unknown tool: {name}", "cost": 0.0}
    return dispatch_tool(contract, state, args or {})
