from __future__ import annotations

from .base import BaseSkill, SkillOutput


class CounterfactualSkill(BaseSkill):
    name = "CounterfactualSkill"

    def run(self, state: dict) -> SkillOutput:
        effect_artifact = next((a for a in state.get("artifacts", []) if a.get("id") == "bootstrap_ci"), {})
        effect = effect_artifact.get("content", {})
        adjusted = float(effect.get("adjusted_effect", effect.get("ate", 0)) or 0)
        outcome = effect.get("query", {}).get("outcome", "目标指标")
        simulation = {
            "question": f"如果把当前策略小幅放大，{outcome} 可能如何变化？",
            "estimated_delta": adjusted,
            "safe_interpretation": "这是基于当前样本的反事实模拟，不是承诺结果。",
            "requires_validation": effect.get("ci_95", [0, 0])[0] <= 0 <= effect.get("ci_95", [0, 0])[1],
        }
        return SkillOutput("counterfactual_simulation", "counterfactual", simulation)
