from __future__ import annotations

from solo_creator_agent.src.skills import EffectEstimationSkill

from .base import BaseSkill, SkillOutput


class BootstrapSkill(BaseSkill):
    name = "BootstrapSkill"

    def run(self, state: dict) -> SkillOutput:
        spec = state["task_spec"]
        treatment = (spec.get("candidate_treatments") or ["title_style"])[0]
        outcome = (spec.get("candidate_outcomes") or ["revenue"])[0]
        value = _infer_treatment_value(str(state.get("task", "")), treatment, state["df"])
        query = {"treatment": treatment, "treatment_value": value, "outcome": outcome, "covariates": [c for c in ["platform", "topic", "account_id", "production_hours"] if c in state["df"].columns and c != treatment]}
        effect = EffectEstimationSkill().run(state["df"], query)
        effect["query"] = query
        low, high = effect.get("ci_95", [0, 0])
        if low <= 0 <= high:
            state["critique"] = {**state.get("critique", {}), "unstable_ci": True}
        return SkillOutput("bootstrap_ci", "bootstrap_ci", effect, warnings=effect.get("warnings", []))


def _infer_treatment_value(task: str, treatment: str, df) -> str:
    task_lower = task.lower()
    value_hints = {
        "title_style": [
            ("pain_point", ["痛点", "pain"]),
            ("tutorial", ["教程", "方法", "tutorial"]),
            ("number", ["数字", "清单", "number"]),
            ("story", ["故事", "案例", "story"]),
            ("contrast", ["对比", "contrast"]),
            ("result_oriented", ["结果", "收益", "result"]),
            ("question", ["提问", "问题", "question"]),
        ],
        "platform": [
            ("xiaohongshu", ["小红书", "rednote"]),
            ("douyin", ["抖音", "douyin"]),
            ("bilibili", ["b站", "bilibili"]),
            ("wechat", ["公众号", "视频号", "wechat"]),
            ("youtube", ["youtube"]),
            ("tiktok", ["tiktok"]),
        ],
    }
    for value, keywords in value_hints.get(treatment, []):
        if any(k in task_lower for k in keywords):
            return value
    if treatment in df.columns and not df.empty:
        counts = df[treatment].dropna().astype(str).value_counts()
        if not counts.empty:
            return str(counts.index[0])
    return ""
