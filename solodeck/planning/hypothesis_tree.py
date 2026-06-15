from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class HypothesisNode:
    hypothesis: str
    required_data: list[str]
    candidate_method: str
    expected_artifact: str
    risk: str
    fallback_method: str


@dataclass
class HypothesisTree:
    root_goal: str
    nodes: list[HypothesisNode]

    def to_dict(self) -> dict[str, Any]:
        return {"root_goal": self.root_goal, "nodes": [asdict(node) for node in self.nodes]}


def generate_hypothesis_tree(task_spec: Any, schema_summary: dict[str, Any], kg_context: dict[str, Any]) -> HypothesisTree:
    spec = task_spec.to_dict() if hasattr(task_spec, "to_dict") else dict(task_spec)
    target = spec.get("target_metric", "revenue")
    variables = spec.get("candidate_variables", [])
    nodes: list[HypothesisNode] = []
    for variable in variables[:5]:
        nodes.append(HypothesisNode(
            hypothesis=f"{variable} 可能影响 {target}",
            required_data=[variable, target],
            candidate_method="Bootstrap + fixed effects" if spec.get("task_type") == "causal_strategy" else "grouped comparison",
            expected_artifact="bootstrap_ci" if spec.get("task_type") == "causal_strategy" else "ranked_insight",
            risk="high" if variable in {"platform", "topic"} else "medium",
            fallback_method="small-sample validation plan",
        ))
    if kg_context.get("summary", {}).get("node_count", 0):
        nodes.append(HypothesisNode(
            hypothesis="知识图谱中的高连接实体可能解释当前策略表现",
            required_data=["knowledge_graph", target],
            candidate_method="GraphRAG retrieval",
            expected_artifact="kg_evidence",
            risk="medium",
            fallback_method="top entity summary",
        ))
    return HypothesisTree(root_goal=spec.get("user_goal", "经营决策"), nodes=nodes)

