from __future__ import annotations

from typing import Any, TypedDict

import pandas as pd

from .audit_log import append_audit
from .causal_discovery import CausalDiscoverySkill
from .knowledge_graph import KnowledgeGraphSkill
from .skills import (
    ActionTestSkill,
    CausalReadinessSkill,
    DataMappingSkill,
    DecisionQuestionSkill,
    EffectEstimationSkill,
    MetricSkill,
    ReportSkill,
    SimilaritySkill,
    dataset_fingerprint,
)


class SoloDeckState(TypedDict, total=False):
    dataset_id: str
    question_id: str
    raw_df: pd.DataFrame
    data: pd.DataFrame
    unstructured_text: str
    mapping: dict[str, Any]
    kpis: dict[str, Any]
    kg: dict[str, Any]
    dag: dict[str, Any]
    query: dict[str, Any]
    readiness: dict[str, Any]
    effect: dict[str, Any]
    validation_loop: dict[str, Any]
    action_plan: dict[str, Any]
    action_cards: list[dict[str, Any]]
    audit: list[dict[str, Any]]
    trace: list[str]


class SoloDeckAgentWorkflow:
    """LangGraph-compatible workflow with a deterministic fallback runner."""

    def run(self, df: pd.DataFrame, question_id: str = "pain_point_title", unstructured_text: str = "") -> dict[str, Any]:
        initial: SoloDeckState = {
            "raw_df": df,
            "question_id": question_id,
            "unstructured_text": unstructured_text,
            "dataset_id": dataset_fingerprint(df),
            "trace": [],
            "audit": [],
        }
        graph = self._build_langgraph()
        if graph is not None:
            return graph.invoke(initial)
        state = initial
        for node in [
            self.data_ingestion_node,
            self.kg_node,
            self.causal_discovery_node,
            self.decision_node,
            self.estimation_node,
            self.reflection_node,
            self.evaluation_node,
            self.action_plan_node,
        ]:
            state = node(state)
        return state

    def _build_langgraph(self) -> Any | None:
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            return None
        graph = StateGraph(SoloDeckState)
        graph.add_node("DataIngestion", self.data_ingestion_node)
        graph.add_node("KnowledgeGraph", self.kg_node)
        graph.add_node("CausalDiscovery", self.causal_discovery_node)
        graph.add_node("DecisionQuestion", self.decision_node)
        graph.add_node("EffectEstimation", self.estimation_node)
        graph.add_node("Reflection", self.reflection_node)
        graph.add_node("Evaluation", self.evaluation_node)
        graph.add_node("ActionPlan", self.action_plan_node)
        graph.set_entry_point("DataIngestion")
        graph.add_edge("DataIngestion", "KnowledgeGraph")
        graph.add_edge("KnowledgeGraph", "CausalDiscovery")
        graph.add_edge("CausalDiscovery", "DecisionQuestion")
        graph.add_edge("DecisionQuestion", "EffectEstimation")
        graph.add_edge("EffectEstimation", "Reflection")
        graph.add_edge("Reflection", "Evaluation")
        graph.add_edge("Evaluation", "ActionPlan")
        graph.add_edge("ActionPlan", END)
        return graph.compile()

    def data_ingestion_node(self, state: SoloDeckState) -> SoloDeckState:
        mapped = DataMappingSkill().run(state["raw_df"])
        data = mapped["data"]
        metric = MetricSkill().run(data)
        scored = metric["scored"]
        state.update({"data": scored, "mapping": mapped["summary"], "kpis": metric["kpis"], "dataset_id": mapped["summary"]["dataset_id"]})
        return self._record(state, "DataIngestion", {"mapping": mapped["summary"], "kpis": metric["kpis"]})

    def kg_node(self, state: SoloDeckState) -> SoloDeckState:
        kg = KnowledgeGraphSkill().run(state["data"], state.get("unstructured_text", ""))
        state["kg"] = kg
        return self._record(state, "KnowledgeGraph", kg["summary"])

    def causal_discovery_node(self, state: SoloDeckState) -> SoloDeckState:
        dag = CausalDiscoverySkill().run(state["data"], state["kg"].get("constraints", {}))
        state["dag"] = dag
        return self._record(state, "CausalDiscovery", {"method": dag["method"], "edge_count": len(dag["edges"])})

    def decision_node(self, state: SoloDeckState) -> SoloDeckState:
        query = DecisionQuestionSkill().run(state.get("question_id", "pain_point_title"), state["data"])
        readiness = CausalReadinessSkill().run(state["data"], query)
        state.update({"query": query, "readiness": readiness})
        return self._record(state, "DecisionQuestion", {"query": query, "readiness": readiness})

    def estimation_node(self, state: SoloDeckState) -> SoloDeckState:
        effect = EffectEstimationSkill().run(state["data"], state["query"])
        state["effect"] = effect
        return self._record(state, "EffectEstimation", {"effect": effect})

    def reflection_node(self, state: SoloDeckState) -> SoloDeckState:
        effect = state["effect"]
        low, high = effect["ci_95"]
        unstable = low <= 0 <= high
        reflection = {
            "ci_unstable": unstable,
            "message": "当前区间穿过 0，需要低成本验证。" if unstable else "区间方向较稳定，可以谨慎进入下一步。",
        }
        state["validation_loop"] = reflection
        return self._record(state, "Reflection", reflection)

    def evaluation_node(self, state: SoloDeckState) -> SoloDeckState:
        readiness = state["readiness"]
        loop = state["validation_loop"]
        evaluation = {
            "confidence": "高" if readiness["readiness_score"] >= 75 and not loop["ci_unstable"] else "中" if readiness["readiness_score"] >= 55 else "低",
            "constraint_check": "已使用知识图谱约束过滤不合理方向。",
            "needs_validation_loop": bool(loop["ci_unstable"] or readiness["readiness_score"] < 75),
        }
        state["evaluation"] = evaluation
        return self._record(state, "Evaluation", evaluation)

    def action_plan_node(self, state: SoloDeckState) -> SoloDeckState:
        similarity = SimilaritySkill().run(state["data"])
        observations = _workflow_observations(state["data"], similarity)
        plan = ActionTestSkill().run(state["query"], state["effect"])
        if state["evaluation"]["needs_validation_loop"]:
            plan["decision"] = "先做小范围验证"
            plan["steps"] = [
                "连续 10-14 天，只在同一平台测试一个变量。",
                "每组至少 6 条内容，记录 24h、72h、7d 结果。",
                "若区间仍穿过 0，暂停放大并更换变量。",
            ]
        cards = ReportSkill().run(observations, state["effect"], plan)
        state.update({"action_plan": plan, "action_cards": cards})
        return self._record(state, "ActionPlan", {"plan": plan, "cards": cards})

    def _record(self, state: SoloDeckState, step: str, payload: dict[str, Any]) -> SoloDeckState:
        state.setdefault("trace", []).append(step)
        event = append_audit(state["dataset_id"], step, payload)
        state.setdefault("audit", []).append(event)
        return state


def _workflow_observations(data: pd.DataFrame, similarity: dict[str, Any]) -> list[dict[str, str]]:
    observations = []
    if "platform" in data.columns and not data.empty:
        top = data.groupby("platform").agg(revenue=("revenue", "sum"), conversions=("conversions", "sum")).reset_index().sort_values(["revenue", "conversions"], ascending=False).iloc[0]
        observations.append({"title": f"{top['platform']} 是当前更强的商业渠道", "detail": f"收入 {top['revenue']:.0f}，成交 {top['conversions']:.0f}。"})
    if similarity.get("warning"):
        observations.append({"title": "内容可能出现疲劳", "detail": similarity["warning"]})
    observations.append({"title": "优先验证最小变量", "detail": "每次只改标题、平台、发布时间或入口位置中的一个。"})
    return observations[:3]
