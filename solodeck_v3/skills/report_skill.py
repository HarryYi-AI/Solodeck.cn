from __future__ import annotations

from .base import BaseSkill, SkillOutput


class ReportSkill(BaseSkill):
    name = "ReportSkill"
    role = "Report"

    def run(self, state: dict) -> SkillOutput:
        bootstrap = next((a for a in state.get("artifacts", []) if a.get("id") == "bootstrap_ci"), {}).get("content", {})
        has_estimate = bool(bootstrap and bootstrap.get("ci_95") is not None)
        low, high = bootstrap.get("ci_95", [None, None]) if has_estimate else [None, None]
        confidence = "需要验证" if not has_estimate or low <= 0 <= high else "较稳定"
        result = (
            f"当前调整后增量 {bootstrap.get('adjusted_effect', bootstrap.get('ate', 0)):.2f}，95% 区间 [{low:.2f}, {high:.2f}]。"
            if has_estimate
            else "当前任务尚未生成可复核的增量估计，仅提供描述性分析。"
        )
        causal_task = state["task_spec"].get("task_type") in {"causal_effect_estimation", "counterfactual_analysis", "causal_hypothesis_generation"}
        limitation = (
            "候选因果图是探索性假设；最终放大前仍需要小范围验证。"
            if causal_task
            else "这是描述性汇总，不代表某项策略产生了因果效果。"
        )
        report = {
            "objective": state["task_spec"]["objective"],
            "method": "知识图谱约束 + 候选因果图 + 重采样区间/回归验证",
            "result": result,
            "confidence": confidence,
            "limitation": limitation,
            "data_source": "用户上传数据的结构化摘要，不展示原始私有数据。",
        }
        state["final_report"] = report
        warnings = [] if has_estimate else ["缺少统计估计工件，报告已降级为描述性分析"]
        return SkillOutput("final_report", "report", report, warnings=warnings)
