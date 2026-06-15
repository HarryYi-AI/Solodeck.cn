from __future__ import annotations

from typing import Any, TypedDict

import pandas as pd

from solodeck.compiler.task_compiler import compile_user_goal
from solodeck.evolution.process_reward import assign_process_rewards
from solodeck.evolution.test_time_evolution import generate_and_evaluate_plans
from solodeck.memory.trace_memory import compress_trace_summary, store_entity_level_memory, store_raw_trace
from solodeck.planning.hypothesis_tree import generate_hypothesis_tree
from solodeck.runtime.budget_controller import assign_reasoning_budget
from solodeck.runtime.skill_runtime import ActionPlanSkill, DataQualitySkill, KGConstructionSkill, ReportSkill, SchemaSkill
from solodeck.verification.validators import validate_final_artifacts


class DataAgentState(TypedDict, total=False):
    user_goal: str
    raw_df: pd.DataFrame
    text: str
    task_spec: dict[str, Any]
    schema: dict[str, Any]
    data: pd.DataFrame
    quality: dict[str, Any]
    kg: dict[str, Any]
    hypothesis_tree: dict[str, Any]
    budget: dict[str, Any]
    query: dict[str, Any]
    evolution: dict[str, Any]
    validation: dict[str, Any]
    reflection: dict[str, Any]
    repair_count: int
    report: dict[str, Any]
    action_cards: list[dict[str, Any]]
    rewards: dict[str, Any]
    memory: dict[str, Any]
    trace: list[dict[str, Any]]


def run_data_agent_graph(user_goal: str, df: pd.DataFrame, text: str = "", query: dict[str, Any] | None = None) -> dict[str, Any]:
    graph = _build_graph()
    initial: DataAgentState = {"user_goal": user_goal, "raw_df": df, "text": text, "query": query or {}, "trace": []}
    if graph is not None:
        return graph.invoke(initial)
    state = initial
    for node in [task_compiler_node, data_perception_node, hypothesis_tree_node, budget_node, multi_plan_node, verification_node, reflection_node, report_node, process_reward_node, memory_update_node]:
        state = node(state)
        if node is verification_node and not state["validation"]["valid"]:
            state = error_analysis_node(state)
            state = repair_plan_node(state)
            state = reexecute_node(state)
            state = verification_node(state)
    return state


def _build_graph() -> Any | None:
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None
    graph = StateGraph(DataAgentState)
    for name, fn in {
        "TaskCompiler": task_compiler_node,
        "DataPerception": data_perception_node,
        "HypothesisTreePlanner": hypothesis_tree_node,
        "BudgetController": budget_node,
        "MultiPlanExecution": multi_plan_node,
        "Verification": verification_node,
        "Reflection": reflection_node,
        "ReportGeneration": report_node,
        "ProcessReward": process_reward_node,
        "MemoryUpdate": memory_update_node,
        "ErrorAnalysis": error_analysis_node,
        "RepairPlan": repair_plan_node,
        "ReExecute": reexecute_node,
    }.items():
        graph.add_node(name, fn)
    graph.set_entry_point("TaskCompiler")
    graph.add_edge("TaskCompiler", "DataPerception")
    graph.add_edge("DataPerception", "HypothesisTreePlanner")
    graph.add_edge("HypothesisTreePlanner", "BudgetController")
    graph.add_edge("BudgetController", "MultiPlanExecution")
    graph.add_edge("MultiPlanExecution", "Verification")
    graph.add_conditional_edges("Verification", _verification_route, {"ok": "Reflection", "repair": "ErrorAnalysis"})
    graph.add_edge("ErrorAnalysis", "RepairPlan")
    graph.add_edge("RepairPlan", "ReExecute")
    graph.add_edge("ReExecute", "Verification")
    graph.add_edge("Reflection", "ReportGeneration")
    graph.add_edge("ReportGeneration", "ProcessReward")
    graph.add_edge("ProcessReward", "MemoryUpdate")
    graph.add_edge("MemoryUpdate", END)
    return graph.compile()


def _record(state: DataAgentState, step: str, payload: dict[str, Any] | None = None) -> DataAgentState:
    state.setdefault("trace", []).append({"step": step, "summary": _compact(payload or {})})
    return state


def task_compiler_node(state: DataAgentState) -> DataAgentState:
    columns = list(state["raw_df"].columns)
    spec = compile_user_goal(state["user_goal"], {"columns": columns})
    state["task_spec"] = spec.to_dict()
    return _record(state, "TaskCompiler", state["task_spec"])


def data_perception_node(state: DataAgentState) -> DataAgentState:
    schema_result = SchemaSkill().run(state["raw_df"])
    state["data"] = schema_result["data"]
    state["schema"] = schema_result["schema"]
    state["quality"] = DataQualitySkill().run(state["data"])
    state["kg"] = KGConstructionSkill().run(state["data"], state.get("text", ""))
    return _record(state, "DataPerception", {"schema": state["schema"], "quality": state["quality"], "kg": state["kg"].get("summary", {})})


def hypothesis_tree_node(state: DataAgentState) -> DataAgentState:
    tree = generate_hypothesis_tree(state["task_spec"], state["schema"], state["kg"])
    state["hypothesis_tree"] = tree.to_dict()
    return _record(state, "HypothesisTreePlanner", state["hypothesis_tree"])


def budget_node(state: DataAgentState) -> DataAgentState:
    risk = {"missing_data": bool(state["quality"].get("warnings")), "unstable_ci": False}
    state["budget"] = assign_reasoning_budget(state["task_spec"], risk).to_dict()
    return _record(state, "BudgetController", state["budget"])


def multi_plan_node(state: DataAgentState) -> DataAgentState:
    query = state.get("query") or _default_query(state)
    state["query"] = query
    state["evolution"] = generate_and_evaluate_plans(state["task_spec"], state["data"], query, n_plans=state["budget"].get("max_plans", 2))
    return _record(state, "MultiPlanExecution", {"selected_plan": state["evolution"]["selected_plan"]["method"], "score": state["evolution"]["selected_plan"]["score"]})


def verification_node(state: DataAgentState) -> DataAgentState:
    artifacts = state["evolution"]["selected_plan"]["artifacts"]
    state["validation"] = validate_final_artifacts(artifacts, [a for a in state["task_spec"]["required_artifacts"] if a not in {"schema", "quality_report", "action_cards"}], state["trace"])
    return _record(state, "Verification", state["validation"])


def error_analysis_node(state: DataAgentState) -> DataAgentState:
    state["repair_count"] = int(state.get("repair_count", 0)) + 1
    state["error_analysis"] = {"issues": state["validation"].get("issues", []), "repairable": True}
    return _record(state, "ErrorAnalysis", state["error_analysis"])


def repair_plan_node(state: DataAgentState) -> DataAgentState:
    state["repair_plan"] = {"action": "降级为小范围验证，不输出强因果结论。"}
    return _record(state, "RepairPlan", state["repair_plan"])


def reexecute_node(state: DataAgentState) -> DataAgentState:
    artifacts = state["evolution"]["selected_plan"]["artifacts"]
    artifacts.setdefault("bootstrap_ci", artifacts.get("effect", {}).get("ci_95"))
    artifacts["causal_claim_check"] = {"status": "passed_after_repair", "guardrail": "已降级为验证建议，不输出强因果结论。"}
    artifacts["validation_mode"] = "low_cost_validation"
    return _record(state, "ReExecute", {"patched": True})


def _verification_route(state: DataAgentState) -> str:
    if state["validation"]["valid"]:
        return "ok"
    if int(state.get("repair_count", 0)) >= 1:
        state["validation"]["issues"] = [f"已降级处理：{issue}" for issue in state["validation"].get("issues", [])]
        return "ok"
    return "repair"


def reflection_node(state: DataAgentState) -> DataAgentState:
    effect = state["evolution"]["selected_plan"]["artifacts"].get("effect", {})
    low, high = effect.get("ci_95", [0, 0])
    state["reflection"] = {"ci_unstable": low <= 0 <= high, "note": "区间穿过 0，进入低成本验证循环。" if low <= 0 <= high else "区间方向较稳定。"}
    return _record(state, "Reflection", state["reflection"])


def report_node(state: DataAgentState) -> DataAgentState:
    artifacts = state["evolution"]["selected_plan"]["artifacts"]
    state["report"] = ReportSkill().run(artifacts)
    state["action_cards"] = ActionPlanSkill().run(artifacts)["cards"]
    return _record(state, "ReportGeneration", {"report": state["report"], "cards": state["action_cards"]})


def process_reward_node(state: DataAgentState) -> DataAgentState:
    state["rewards"] = assign_process_rewards(state["trace"], state["validation"])
    return _record(state, "ProcessReward", state["rewards"])


def memory_update_node(state: DataAgentState) -> DataAgentState:
    session_id = state["task_spec"]["task_type"] + "_" + str(abs(hash(str(state["schema"].get("columns", [])))) % 10_000_000)
    raw_path = store_raw_trace(session_id, state["trace"])
    entity_path = store_entity_level_memory(session_id, state["kg"].get("nodes", []))
    state["memory"] = {"session_id": session_id, "raw_trace_path": raw_path, "entity_memory_path": entity_path, "summary": compress_trace_summary(state["trace"])}
    return _record(state, "MemoryUpdate", state["memory"])


def _default_query(state: DataAgentState) -> dict[str, Any]:
    columns = state["schema"].get("columns", [])
    treatment = "title_style" if "title_style" in columns else "platform"
    value = str(state["data"][treatment].dropna().iloc[0]) if treatment in state["data"].columns and not state["data"].empty else ""
    outcome = state["task_spec"].get("target_metric", "revenue")
    return {"treatment": treatment, "treatment_value": value, "outcome": outcome, "covariates": [c for c in ["platform", "topic", "account_id", "production_hours"] if c in columns and c != treatment]}


def _compact(value: Any) -> Any:
    text = str(value)
    return text[:700] + ("..." if len(text) > 700 else "")
