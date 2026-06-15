from __future__ import annotations

from solodeck_v3.graph.kg_builder import build_kg_context

from .base import BaseSkill, SkillOutput


class KGConstructionSkill(BaseSkill):
    name = "KGConstructionSkill"
    role = "Retriever"

    def run(self, state: dict) -> SkillOutput:
        kg = build_kg_context(state["df"], state.get("text", ""), state.get("trace_id", ""))
        state["kg_context"] = kg
        return SkillOutput("kg_context", "knowledge_graph", kg)

