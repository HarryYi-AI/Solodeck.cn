from __future__ import annotations

from .base import BaseSkill, SkillOutput


class CausalReadinessSkill(BaseSkill):
    name = "CausalReadinessSkill"
    role = "Critic"

    def run(self, state: dict) -> SkillOutput:
        spec = state["task_spec"]
        treatment = (spec.get("candidate_treatments") or [""])[0]
        outcome = (spec.get("candidate_outcomes") or ["revenue"])[0]
        df = state["df"]
        warnings = []
        score = 0
        if treatment in df.columns and df[treatment].nunique(dropna=True) >= 2:
            score += 30
        else:
            warnings.append("缺少可比较的处理变量。")
        if outcome in df.columns:
            score += 25
        else:
            warnings.append("缺少结果指标。")
        if len(df) >= 30:
            score += 20
        else:
            warnings.append("样本量较小。")
        confounders = state.get("causal_context", {}).get("candidate_confounders", [])
        if confounders:
            score += 25
        else:
            warnings.append("候选混杂变量不足。")
        overlap = False
        if treatment in df.columns:
            counts = df[treatment].dropna().astype(str).value_counts()
            overlap = len(counts) >= 2 and counts.iloc[:2].min() >= 5
            if overlap:
                score += 10
            else:
                warnings.append("处理组和对照组重叠不足。")
        time_ordering = any(col in df.columns for col in ["publish_time", "date", "created_at"])
        if time_ordering:
            score += 10
        else:
            warnings.append("缺少可用于判断前后顺序的时间字段。")
        score = min(score, 100)
        readiness = {
            "treatment": treatment,
            "outcome": outcome,
            "candidate_confounders": confounders,
            "score": score,
            "overlap_ok": overlap,
            "time_ordering_ok": time_ordering,
            "causal_claim_allowed": score >= 80,
            "warnings": warnings,
        }
        state["critique"] = {**state.get("critique", {}), "causal_readiness": readiness, "unsupported_causal_claim": score < 70}
        return SkillOutput("causal_readiness", "causal_readiness", readiness, valid=score >= 50, warnings=warnings)
