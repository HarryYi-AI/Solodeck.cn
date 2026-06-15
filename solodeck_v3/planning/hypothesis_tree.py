from __future__ import annotations

from typing import Any


def generate_hypothesis_tree(task_spec: dict[str, Any], schema_summary: dict[str, Any], kg_context: dict[str, Any]) -> dict[str, Any]:
    target = (task_spec.get("candidate_outcomes") or ["revenue"])[0]
    treatments = task_spec.get("candidate_treatments", [])
    nodes = []
    for index, treatment in enumerate(treatments[:6]):
        nodes.append({
            "id": f"H{index + 1}",
            "hypothesis": f"{treatment} 可能影响 {target}",
            "required_data": [treatment, target],
            "candidate_method": "Bootstrap + fixed effects + KG constraints",
            "expected_artifact": "bootstrap_ci",
            "risk": "high" if task_spec.get("task_type", "").startswith("causal") else "medium",
            "fallback_method": "counterfactual validation plan",
        })
    if kg_context.get("summary", {}).get("node_count", 0):
        nodes.append({
            "id": f"H{len(nodes) + 1}",
            "hypothesis": "高连接 KG 实体可解释策略表现差异",
            "required_data": ["kg_context", target],
            "candidate_method": "GraphRAG evidence retrieval",
            "expected_artifact": "kg_evidence",
            "risk": "medium",
            "fallback_method": "top entity ranking",
        })
    return {"root": task_spec.get("objective", "经营问题"), "nodes": nodes}

