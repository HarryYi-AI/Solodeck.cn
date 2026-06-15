from __future__ import annotations

from solo_creator_agent.src.causal_discovery import CausalDiscoverySkill as LegacyCausalDiscovery
from solodeck_v3.graph.constraint_graph import derive_constraints_from_kg

from .base import BaseSkill, SkillOutput


class CausalDiscoverySkill(BaseSkill):
    name = "CausalDiscoverySkill"

    def run(self, state: dict) -> SkillOutput:
        constraints = derive_constraints_from_kg(state.get("kg_context", {}))
        graph = LegacyCausalDiscovery().run(state["df"], constraints)
        sample_size = len(state["df"])
        warnings = list(graph.get("warnings", []))
        if sample_size < 50:
            warnings.append("样本量偏小，候选因果图稳定性较低。")
        causal_context = {
            "exploratory_causal_graph": {"nodes": graph.get("nodes", []), "edges": graph.get("edges", [])},
            "candidate_confounders": constraints.get("candidate_confounders", []),
            "forbidden_edge_violations": [],
            "stability_score": min(1.0, sample_size / 120),
            "method": graph.get("method", "fallback"),
            "warnings": warnings,
            "note": "候选因果图只用于提出可验证假设，不作为最终因果真相。",
        }
        state["causal_context"] = causal_context
        return SkillOutput("causal_context", "exploratory_causal_graph", causal_context, warnings=warnings)

