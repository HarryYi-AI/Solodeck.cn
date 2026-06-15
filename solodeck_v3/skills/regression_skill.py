from __future__ import annotations

from solo_creator_agent.src.skills import EffectEstimationSkill

from .base import BaseSkill, SkillOutput
from .bootstrap_skill import _infer_treatment_value


class RegressionSkill(BaseSkill):
    name = "RegressionSkill"

    def run(self, state: dict) -> SkillOutput:
        spec = state["task_spec"]
        treatment = (spec.get("candidate_treatments") or ["title_style"])[0]
        outcome = (spec.get("candidate_outcomes") or ["revenue"])[0]
        value = _infer_treatment_value(str(state.get("task", "")), treatment, state["df"])
        query = {"treatment": treatment, "treatment_value": value, "outcome": outcome, "covariates": [c for c in ["platform", "topic", "account_id", "production_hours"] if c in state["df"].columns and c != treatment]}
        effect = EffectEstimationSkill().run(state["df"], query)
        result = {"adjusted_effect": effect["adjusted_effect"], "iptw_effect": effect.get("iptw_effect"), "query": query, "ci_95": effect.get("ci_95"), "sample_size": effect.get("sample_size")}
        state.setdefault("artifacts", []).append({"id": "regression_effect", "type": "regression_effect", "content": result})
        return SkillOutput("regression_effect", "regression_effect", result, warnings=effect.get("warnings", []))
