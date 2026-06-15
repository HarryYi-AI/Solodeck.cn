from __future__ import annotations

from .base import BaseSkill, SkillOutput


class ReportSkill(BaseSkill):
    name = "ReportSkill"
    role = "Report"

    def run(self, state: dict) -> SkillOutput:
        bootstrap = next((a for a in state.get("artifacts", []) if a.get("id") == "bootstrap_ci"), {}).get("content", {})
        low, high = bootstrap.get("ci_95", [0, 0])
        confidence = "需要验证" if low <= 0 <= high else "较稳定"
        report = {
            "objective": state["task_spec"]["objective"],
            "method": "知识图谱约束 + 候选因果图 + 重采样区间/回归验证",
            "result": f"当前调整后增量 {bootstrap.get('adjusted_effect', 0):.2f}，95% 区间 [{low:.2f}, {high:.2f}]。",
            "confidence": confidence,
            "limitation": "候选因果图是探索性假设；最终放大前仍需要小范围验证。",
            "data_source": "用户上传数据的结构化摘要，不展示原始私有数据。",
        }
        state["final_report"] = report
        return SkillOutput("final_report", "report", report)
