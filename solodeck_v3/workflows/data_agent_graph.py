from __future__ import annotations

import time
import uuid
from typing import Any

import pandas as pd

from solodeck_v3.compiler.task_compiler import compile_user_goal
from solodeck_v3.compiler.task_schema import DataAgentState
from solodeck_v3.agents.causal_analyst_agent import CausalAnalystAgent
from solodeck_v3.agents.explorer_agent import ExplorerAgent
from solodeck_v3.agents.planner_agent import PlannerAgent
from solodeck_v3.agents.retriever_agent import RetrieverAgent
from solodeck_v3.agents.verifier_agent import VerifierAgent
from solodeck_v3.agents.writer_agent import WriterAgent
from solodeck_v3.evolution.error_analyzer import classify_failure
from solodeck_v3.evolution.regression_task_generator import generate_regression_task
from solodeck_v3.evolution.scheduler_update import update_scheduler_policy
from solodeck_v3.frontend.developer_trace_panel import build_developer_trace_panel
from solodeck_v3.frontend.user_artifact_view import build_user_artifact_view
from solodeck_v3.graph.causal_graph_store import store_causal_graph
from solodeck_v3.graph.kg_builder import build_kg_context
from solodeck_v3.memory.dataset_memory import store_dataset_memory
from solodeck_v3.memory.failure_memory import store_failure_memory
from solodeck_v3.memory.graph_memory import store_graph_memory
from solodeck_v3.memory.schema_memory import store_schema_memory
from solodeck_v3.memory.trace_memory import store_trace_memory
from solodeck_v3.planning.hypothesis_tree import generate_hypothesis_tree
from solodeck_v3.planning.method_planner import generate_candidate_plans
from solodeck_v3.reward.agent_wise_normalization import normalize_agent_rewards
from solodeck_v3.reward.process_reward import assign_process_rewards
from solodeck_v3.router.router import route_task
from solodeck_v3.runtime.scheduler import schedule_skills
from solodeck_v3.runtime.skill_runtime import execute_skill_sequence
from solodeck_v3.runtime.snapshot import save_snapshot
from solodeck_v3.runtime.trace_logger import append_trace
from solodeck_v3.skills.report_skill import ReportSkill
from solodeck_v3.verification import validate_all


def run_v3_data_agent(task: str, df: pd.DataFrame, text: str = "", max_revisions: int = 2) -> dict[str, Any]:
    state: DataAgentState = {
        "task": task,
        "df": df,
        "text": text,
        "trace_id": f"v3_{uuid.uuid4().hex[:12]}",
        "revision_number": 0,
        "max_revisions": max_revisions,
        "trace": [],
        "artifacts": [],
        "memory_updates": [],
        "selected_skills": [],
    }
    graph = _build_graph()
    if graph is not None:
        return graph.invoke(state, config={"configurable": {"thread_id": state["trace_id"]}, "recursion_limit": 40})
    for node in [compile_task_node, load_memory_node, build_or_retrieve_kg_node, generate_hypothesis_tree_node, route_tools_node, plan_workflow_node, execute_skills_node, validate_artifacts_node, assign_rewards_node, reflect_node]:
        state = node(state)
    while _should_continue(state):
        state = repair_or_explore_node(state)
        state = route_tools_node(state)
        state = plan_workflow_node(state)
        state = execute_skills_node(state)
        state = validate_artifacts_node(state)
        state = assign_rewards_node(state)
        state = reflect_or_repair_node(state)
    state = generate_final_artifact_node(state)
    state = update_memory_node(state)
    return state


def _build_graph() -> Any | None:
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None
    graph = StateGraph(DataAgentState)
    nodes = {
        "CompileTask": compile_task_node,
        "LoadMemory": load_memory_node,
        "BuildOrRetrieveKG": build_or_retrieve_kg_node,
        "GenerateHypothesisTree": generate_hypothesis_tree_node,
        "RouteTools": route_tools_node,
        "PlanWorkflow": plan_workflow_node,
        "ExecuteSkills": execute_skills_node,
        "ValidateArtifacts": validate_artifacts_node,
        "AssignProcessRewards": assign_rewards_node,
        "Reflect": reflect_node,
        "RepairOrExplore": repair_or_explore_node,
        "GenerateFinalArtifact": generate_final_artifact_node,
        "UpdateMemory": update_memory_node,
    }
    for name, fn in nodes.items():
        graph.add_node(name, fn)
    graph.set_entry_point("CompileTask")
    graph.add_edge("CompileTask", "LoadMemory")
    graph.add_edge("LoadMemory", "BuildOrRetrieveKG")
    graph.add_edge("BuildOrRetrieveKG", "GenerateHypothesisTree")
    graph.add_edge("GenerateHypothesisTree", "RouteTools")
    graph.add_edge("RouteTools", "PlanWorkflow")
    graph.add_edge("PlanWorkflow", "ExecuteSkills")
    graph.add_edge("ExecuteSkills", "ValidateArtifacts")
    graph.add_edge("ValidateArtifacts", "AssignProcessRewards")
    graph.add_edge("AssignProcessRewards", "Reflect")
    graph.add_conditional_edges("Reflect", lambda s: "continue" if _should_continue(s) else "finish", {"continue": "RepairOrExplore", "finish": "GenerateFinalArtifact"})
    graph.add_edge("RepairOrExplore", "RouteTools")
    graph.add_edge("GenerateFinalArtifact", "UpdateMemory")
    graph.add_edge("UpdateMemory", END)
    return graph.compile()


def compile_task_node(state: DataAgentState) -> DataAgentState:
    spec = compile_user_goal(state["task"], state["df"], state.get("text", ""))
    state["task_spec"] = spec.to_dict()
    append_trace(state, "CompileTask", "PlannerAgent", {"task_type": spec.task_type, "budget": spec.budget_level})
    save_snapshot(state["trace_id"], state, "compile_task")
    return state


def load_memory_node(state: DataAgentState) -> DataAgentState:
    memory = store_dataset_memory(state["trace_id"], state["df"])
    state.setdefault("memory_updates", []).append({"type": "DatasetMemory", "summary": memory})
    append_trace(state, "LoadMemory", "RetrieverAgent", {"dataset_rows": len(state["df"])})
    return state


def build_or_retrieve_kg_node(state: DataAgentState) -> DataAgentState:
    kg = build_kg_context(state["df"], state.get("text", ""), state["trace_id"])
    state["kg_context"] = kg
    state.setdefault("artifacts", []).append({"id": "kg_context", "type": "knowledge_graph", "content": kg, "generated_by": "KGConstructionSkill"})
    context = RetrieverAgent().summarize_context(kg, state.get("memory_updates", []))
    append_trace(state, "BuildOrRetrieveKG", "RetrieverAgent", {**kg.get("summary", {}), "context": context}, ["kg_context"])
    return state


def generate_hypothesis_tree_node(state: DataAgentState) -> DataAgentState:
    tree = generate_hypothesis_tree(state["task_spec"], state.get("schema_summary", {"columns": list(state["df"].columns)}), state["kg_context"])
    state["hypothesis_tree"] = tree
    append_trace(state, "GenerateHypothesisTree", "PlannerAgent", {"hypotheses": len(tree.get("nodes", []))})
    return state


def route_tools_node(state: DataAgentState) -> DataAgentState:
    route = route_task(state["task_spec"], state.get("data_quality_report"), state.get("critique"), state.get("kg_context"))
    state["route_decision"] = route
    state["budget"] = route["budget"]
    append_trace(state, "RouteTools", "PlannerAgent", {"route_id": route["route_id"], "tools": route["selected_tools"], "reason": route["tool_policy"]["policy_reason"]})
    return state


def plan_workflow_node(state: DataAgentState) -> DataAgentState:
    budget = state.get("budget") or route_task(state["task_spec"], state.get("data_quality_report"), state.get("critique"), state.get("kg_context"))["budget"]
    state["budget"] = budget
    plans = generate_candidate_plans(state["task_spec"], state["hypothesis_tree"], budget)
    state["plan_candidates"] = plans
    if state.get("repair_plan"):
        plan = dict(state["selected_plan"])
        plan["skills"] = list(dict.fromkeys(plan.get("skills", []) + ["BootstrapSkill", "CounterfactualSkill", "ReportSkill"]))
    else:
        plan = PlannerAgent().plan(state["task_spec"], state.get("route_decision", {}), plans)
    scheduled = schedule_skills(state["task_spec"], state.get("budget", {}), history=[])
    plan["method_entropy"] = scheduled["method_entropy"]
    plan["route_id"] = state.get("route_decision", {}).get("route_id")
    state["selected_plan"] = plan
    append_trace(state, "PlanWorkflow", "PlannerAgent", {"plans": [p["plan_id"] for p in plans], "method": plan["method"], "skills": plan["skills"], "budget": budget, "entropy": plan.get("method_entropy")})
    return state


def execute_skills_node(state: DataAgentState) -> DataAgentState:
    started = time.time()
    result = execute_skill_sequence(state, state["selected_plan"].get("skills", []))
    state["selected_plan"]["latency"] = round(time.time() - started, 4)
    append_trace(state, "ExecuteSkills", "ExecutorAgent", {"skills": state["selected_plan"].get("skills", []), "outputs": [o["id"] for o in result["outputs"]]}, [o["id"] for o in result["outputs"]])
    return state


def validate_artifacts_node(state: DataAgentState) -> DataAgentState:
    report_artifact = next((a for a in state.get("artifacts", []) if a["id"] == "final_report"), None)
    if report_artifact:
        state["final_report"] = report_artifact["content"]
    append_trace(state, "ValidateArtifacts", "VerifierAgent", {"status": "started"})
    state["validation_report"] = validate_all(state)
    state["trace"][-1]["summary"] = state["validation_report"]
    return state


def assign_rewards_node(state: DataAgentState) -> DataAgentState:
    step_rewards = assign_process_rewards(state["trace"], state.get("validation_report", {}))
    state["step_rewards"] = step_rewards
    state["process_rewards"] = step_rewards
    state["agent_rewards"] = normalize_agent_rewards(step_rewards)
    append_trace(state, "AssignProcessRewards", "VerifierAgent", {"total": step_rewards.get("total"), "agent_rewards": state["agent_rewards"]})
    return state


def reflect_node(state: DataAgentState) -> DataAgentState:
    validation = state.get("validation_report", {})
    critique = state.setdefault("critique", {})
    if validation.get("block_output"):
        critique["privacy_block"] = True
    if not validation.get("valid"):
        failure = classify_failure(validation)
        state["failure_report"] = failure
        if failure["repairable"]:
            critique["needs_repair"] = True
    state["claim_review"] = CausalAnalystAgent().downgrade_if_needed(validation, critique)
    state["validation_summary"] = VerifierAgent().summarize_validation(validation)
    append_trace(state, "Reflect", "VerifierAgent", {"needs_repair": critique.get("needs_repair", False), "revision": state.get("revision_number", 0), "claim_review": state["claim_review"]})
    return state


def repair_or_explore_node(state: DataAgentState) -> DataAgentState:
    state["revision_number"] = int(state.get("revision_number", 0)) + 1
    state["repair_plan"] = {
        "action": "降级为低成本验证；补充 Bootstrap 和反事实模拟；禁止强因果表述。",
        "failure_type": state.get("failure_report", {}).get("failure_type"),
        "options": ExplorerAgent().repair_options(state.get("critique", {})),
    }
    state.setdefault("critique", {})["downgraded_to_validation"] = True
    if state.get("failure_report"):
        state["regression_task"] = generate_regression_task(state["failure_report"], state["trace_id"])
        store_failure_memory(state["trace_id"], state["failure_report"])
    append_trace(state, "RepairOrExplore", "ExplorerAgent", state["repair_plan"])
    return state


def generate_final_artifact_node(state: DataAgentState) -> DataAgentState:
    if not state.get("final_report"):
        output = ReportSkill().run(state)
        state["final_report"] = output.content
        state.setdefault("artifacts", []).append({"id": output.artifact_id, "type": output.artifact_type, "content": output.content, "generated_by": "ReportSkill"})
    state["action_cards"] = _action_cards(state)
    state["user_artifact"] = __import__("solodeck_v3.frontend.user_artifact_view", fromlist=["build_user_artifact_view"]).build_user_artifact_view(state)
    state["user_artifact"] = WriterAgent().polish_user_artifact(state["user_artifact"])
    state["developer_trace"] = __import__("solodeck_v3.frontend.developer_trace_panel", fromlist=["build_developer_trace_panel"]).build_developer_trace_panel(state)
    append_trace(state, "GenerateFinalArtifact", "WriterAgent", {"validation": state.get("validation_report", {}).get("valid"), "cards": len(state["action_cards"])})
    return state


def update_memory_node(state: DataAgentState) -> DataAgentState:
    updates = state.setdefault("memory_updates", [])
    updates.append({"type": "TraceMemory", "summary": store_trace_memory(state["trace_id"], state["trace"])})
    if state.get("schema_summary"):
        updates.append({"type": "SchemaMemory", "summary": store_schema_memory(state["trace_id"], state["schema_summary"])})
    updates.append({"type": "GraphMemory", "summary": store_graph_memory(state["trace_id"], state.get("kg_context", {}))})
    if state.get("causal_context"):
        updates.append({"type": "CausalGraphMemory", "summary": store_causal_graph(state["trace_id"], state["causal_context"])})
    updates.append({"type": "SkillUtilityMemory", "summary": update_scheduler_policy(state["trace_id"], state.get("selected_plan", {}), state.get("agent_rewards", {}))})
    append_trace(state, "UpdateMemory", "RetrieverAgent", {"updates": len(updates)})
    return state


def _should_continue(state: DataAgentState) -> bool:
    if state.get("critique", {}).get("privacy_block"):
        return False
    if int(state.get("revision_number", 0)) >= int(state.get("max_revisions", 2)):
        return False
    return bool(state.get("critique", {}).get("needs_repair")) and not state.get("validation_report", {}).get("valid")


def _action_cards(state: DataAgentState) -> list[dict[str, Any]]:
    bootstrap = next((a.get("content", {}) for a in state.get("artifacts", []) if a.get("id") == "bootstrap_ci"), {})
    low, high = bootstrap.get("ci_95", [0, 0])
    query = bootstrap.get("query", {})
    treatment = _display_name(query.get("treatment", "策略"))
    value = _display_name(query.get("treatment_value", "当前方案"))
    outcome = _display_name(query.get("outcome", "结果指标"))
    impact = bootstrap.get("adjusted_effect", bootstrap.get("ate", 0))
    if low > 0:
        title = f"继续放大：{value}"
        confidence = "方向较稳"
        explanation = f"观察到 {value} 对 {outcome} 的提升区间大多高于 0，可小幅增加投入。"
        next_step = f"在同一平台、同一主题下继续使用 {value}，并记录 24 小时、72 小时和 7 天后的 {outcome}。"
    elif high < 0:
        title = f"减少投入：{value}"
        confidence = "负向较稳"
        explanation = f"观察到 {value} 对 {outcome} 的区间大多低于 0，继续放大风险较高。"
        next_step = f"暂停扩大 {value}，换一个 {treatment} 方案做小样本对照。"
    else:
        title = f"先验证：{value}"
        confidence = "仍需验证"
        explanation = "置信区间穿过 0，当前结果不够稳定，不能直接判断有效或无效。"
        next_step = f"连续 7 天做小样本对照，每次只改变{treatment}，再看{outcome}。"
    return [
        {"title": title, "priority": "高", "estimated_impact": impact, "confidence": confidence, "explanation": explanation, "next_step": next_step, "references": ["bootstrap_ci", "causal_readiness"]},
        {"title": "固定同一平台和主题", "priority": "中", "estimated_impact": 0, "confidence": "控制混杂", "explanation": "每次只改一个变量，减少平台和主题差异干扰。", "next_step": "选择一个平台和一个主题连续发布，不要同时更换标题、发布时间和内容方向。", "references": ["kg_context", "causal_context"]},
        {"title": "记录三个时间点", "priority": "中", "estimated_impact": 0, "confidence": "补充证据", "explanation": "每条内容记录 24 小时、72 小时和 7 天后的结果，下一轮建议会更稳。", "next_step": "每条内容发布后记录播放、收藏、咨询、成交四项指标，统一填回同一张表。", "references": ["trace_memory", "skill_utility_memory"]},
    ]


def _display_name(value: Any) -> str:
    names = {
        "platform": "平台",
        "topic": "主题",
        "title_style": "标题风格",
        "publish_time": "发布时间",
        "feature_tags": "产品功能",
        "production_hours": "制作时长",
        "revenue": "收入",
        "conversions": "成交数",
        "consultations": "咨询数",
        "favorites": "收藏数",
        "views": "播放量",
        "pain_point": "痛点标题",
        "tutorial": "教程标题",
        "number": "数字清单标题",
        "story": "故事标题",
        "contrast": "对比标题",
        "result_oriented": "结果导向标题",
        "question": "提问标题",
        "xiaohongshu": "小红书",
        "douyin": "抖音",
        "bilibili": "B站",
        "wechat": "公众号/视频号",
    }
    return names.get(str(value), str(value))
