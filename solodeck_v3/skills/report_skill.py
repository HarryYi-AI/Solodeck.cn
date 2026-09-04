from __future__ import annotations

from .base import BaseSkill, SkillOutput


class ReportSkill(BaseSkill):
    name = "ReportSkill"
    role = "Report"

    def run(self, state: dict) -> SkillOutput:
        descriptive = next((a for a in state.get("artifacts", []) if a.get("id") == "descriptive_comparison"), {}).get("content", {})
        if descriptive and descriptive.get("question_type") == "descriptive_comparison":
            report = self._descriptive_report(state, descriptive)
            state["final_report"] = report
            return SkillOutput("final_report", "report", report)
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

    @staticmethod
    def _descriptive_report(state: dict, comparison: dict) -> dict:
        scale = float(comparison.get("display_scale", 1.0))
        metric_label = comparison.get("metric_label", "指标")
        ranking = comparison["ranking"]

        def display(row: dict) -> str:
            value = float(row["value"]) * scale
            if comparison.get("is_rate"):
                decimals = 3 if 0 < abs(value) < 0.1 else 2 if 0 < abs(value) < 1 else 1
                return f"{value:.{decimals}f}%"
            if comparison.get("metric") == "revenue":
                return f"¥{value:,.0f}"
            return f"{value:,.2f}".rstrip("0").rstrip(".")

        if comparison.get("status") == "insufficient_comparison":
            available = ranking[0] if ranking else None
            available_text = f"目前只有{available['group']}可计算，为 {display(available)}；" if available else ""
            missing = comparison.get("unavailable_groups", 0)
            raw_denominator = comparison.get("denominator") or "有效分母"
            denominator = {
                "visitors": "访客数",
                "clicks": "点击数",
                "sessions": "访问次数",
                "consultations": "咨询数",
                "views": "播放量",
                "impressions": "曝光量",
            }.get(raw_denominator, raw_denominator)
            return {
                "objective": state["task_spec"]["objective"],
                "method": f"按{comparison.get('group_label', '分组')}核对{metric_label}及其分母",
                "result": f"【描述性结论】{available_text}另有 {missing} 个平台缺少有效分母，当前不能进行可靠排名。",
                "confidence": "数据不完整",
                "limitation": f"缺失值不等于 0。请补充各平台的{denominator}，系统再计算同口径{metric_label}。",
                "data_source": f"用户上传数据，共 {comparison.get('sample_size', 0)} 条记录进入检查。",
            }

        best, runner_up, worst = comparison["best"], comparison["runner_up"], comparison["worst"]
        if comparison.get("status") == "tie":
            return {
                "objective": state["task_spec"]["objective"],
                "method": f"按{comparison.get('group_label', '分组')}汇总并直接比较{metric_label}",
                "result": f"【描述性结论】各平台的{metric_label}当前相同，均为 {display(best)}，暂时没有可区分的第一名。",
                "confidence": "直接观察",
                "limitation": "相同值可能是真实持平，也可能来自全零或缺失数据；请先核对分母与统计周期。",
                "data_source": f"用户上传数据，共 {comparison.get('sample_size', 0)} 条有效记录。",
            }
        ranking_text = "、".join(f"{row['group']} {display(row)}" for row in ranking[:6])
        ratio = comparison.get("best_to_worst_ratio")
        difference = f"，约为{worst['group']}的 {ratio:.1f} 倍" if ratio is not None else ""
        result = f"【描述性结论】{best['group']}的{metric_label}最高，为 {display(best)}{difference}。排序：{ranking_text}。"
        return {
            "objective": state["task_spec"]["objective"],
            "method": f"按{comparison.get('group_label', '分组')}汇总并直接比较{metric_label}",
            "result": result,
            "confidence": "直接观察",
            "limitation": "该排序回答当前数据中谁更高；若要判断差异由平台本身还是活动、流量结构等因素造成，再做归因分析。",
            "data_source": f"用户上传数据，共 {comparison.get('sample_size', 0)} 条有效记录。",
        }
