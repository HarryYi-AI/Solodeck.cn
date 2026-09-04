from __future__ import annotations

from typing import Any

import pandas as pd

from .base import BaseSkill, SkillOutput


RATE_DENOMINATORS = {
    "conversion_rate": ("visitors", "clicks", "sessions", "consultations", "views"),
    "consultation_rate": ("visitors", "clicks", "views"),
    "favorite_rate": ("views", "impressions"),
    "follow_rate": ("views", "impressions"),
}

RATE_NUMERATORS = {
    "conversion_rate": "conversions",
    "consultation_rate": "consultations",
    "favorite_rate": "favorites",
    "follow_rate": "new_followers",
}

DISPLAY_NAMES = {
    "platform": "平台",
    "conversion_rate": "转化率",
    "consultation_rate": "咨询率",
    "favorite_rate": "收藏率",
    "follow_rate": "转粉率",
    "conversions": "成交数",
    "consultations": "咨询数",
    "revenue": "收入",
    "views": "播放量",
}

PLATFORM_NAMES = {
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "douyin": "抖音",
    "wechat": "公众号/视频号",
    "kuaishou": "快手",
    "meituan": "美团",
    "taobao": "淘宝",
    "tmall": "天猫",
    "pinduoduo": "拼多多",
    "jingdong": "京东",
    "jd": "京东",
    "youtube": "YouTube",
    "tiktok": "TikTok",
}


class DescriptiveComparisonSkill(BaseSkill):
    """Compare observed business metrics without turning ranking into a causal claim."""

    name = "DescriptiveComparisonSkill"
    role = "Executor"
    input_schema = {"df": "DataFrame", "task_spec": "TaskSpec"}
    output_schema = {"ranking": "list", "status": "str", "sample_size": "int"}
    failure_modes = ["缺少分组字段", "缺少可计算指标"]

    def run(self, state: dict[str, Any]) -> SkillOutput:
        df = state.get("df")
        spec = state.get("task_spec") or {}
        if df is None or getattr(df, "empty", True):
            return SkillOutput("descriptive_comparison", "descriptive_result", {}, valid=False, warnings=["没有可比较的数据"])

        data = df.copy()
        group_col = self._pick_group(data, spec)
        metric, is_rate, numerator, denominator = self._pick_metric(data, spec)
        if not group_col or not metric:
            return SkillOutput(
                "descriptive_comparison",
                "descriptive_result",
                {},
                valid=False,
                warnings=["缺少分组字段或可计算指标"],
            )

        if numerator and denominator:
            grouped, usable = self._aggregate_derived_rate(data, group_col, numerator, denominator)
        else:
            data[metric] = pd.to_numeric(data[metric], errors="coerce")
            usable = data.dropna(subset=[group_col, metric]).copy()
            grouped = usable.groupby(group_col, dropna=False)[metric].agg(["mean", "count"]).sort_values("mean", ascending=False)

        ranking = [
            {
                "rank": index + 1,
                "group": self._display_group(group),
                "raw_group": str(group),
                "value": float(row["mean"]),
                "sample_size": int(row["count"]),
            }
            for index, (group, row) in enumerate(grouped.iterrows())
        ]
        total_groups = int(data[group_col].nunique(dropna=True))
        unavailable_groups = max(total_groups - len(ranking), 0)
        scale = self._rate_scale([row["value"] for row in ranking]) if is_rate else 1.0
        common = {
            "question_type": "descriptive_comparison",
            "evidence_label": "直接观察",
            "group_by": group_col,
            "group_label": DISPLAY_NAMES.get(group_col, group_col),
            "metric": metric,
            "metric_label": DISPLAY_NAMES.get(metric, metric),
            "is_rate": is_rate,
            "display_scale": scale,
            "ranking": ranking,
            "unavailable_groups": unavailable_groups,
            "denominator": denominator,
            "sample_size": int(len(usable)),
        }

        if len(ranking) < 2:
            return SkillOutput(
                "descriptive_comparison",
                "descriptive_result",
                {**common, "status": "insufficient_comparison"},
                warnings=["只有一个或没有分组具备有效分母，暂时不能跨平台排名"],
            )

        best, runner_up, worst = ranking[0], ranking[1], ranking[-1]
        ratio = best["value"] / worst["value"] if worst["value"] != 0 else None
        tied = all(abs(row["value"] - best["value"]) < 1e-12 for row in ranking)
        content = {
            **common,
            "status": "tie" if tied else "comparable",
            "best": best,
            "runner_up": runner_up,
            "worst": worst,
            "absolute_gap": float(best["value"] - runner_up["value"]),
            "best_to_worst_ratio": float(ratio) if ratio is not None else None,
            "interpretation": "这是对已上传数据的直接比较，可以回答当前谁更高；它不用于证明平台本身造成了差异。",
        }
        return SkillOutput("descriptive_comparison", "descriptive_result", content)

    @staticmethod
    def _aggregate_derived_rate(
        data: pd.DataFrame,
        group_col: str,
        numerator: str,
        denominator: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        data[numerator] = pd.to_numeric(data[numerator], errors="coerce")
        data[denominator] = pd.to_numeric(data[denominator], errors="coerce")
        usable = data.dropna(subset=[group_col, numerator, denominator]).copy()
        totals = usable.groupby(group_col, dropna=False)[[numerator, denominator]].sum()
        totals = totals[totals[denominator] > 0]
        counts = usable.groupby(group_col, dropna=False).size().reindex(totals.index)
        grouped = pd.DataFrame({"mean": totals[numerator] / totals[denominator], "count": counts})
        return grouped.sort_values("mean", ascending=False), usable

    @staticmethod
    def _pick_group(df: pd.DataFrame, spec: dict[str, Any]) -> str | None:
        candidates = list(spec.get("candidate_treatments") or []) + ["platform", "topic", "title_style"]
        for column in candidates:
            if column in df.columns and df[column].nunique(dropna=True) >= 2:
                return column
        return None

    @staticmethod
    def _pick_metric(df: pd.DataFrame, spec: dict[str, Any]) -> tuple[str | None, bool, str | None, str | None]:
        requested = list(spec.get("candidate_outcomes") or [])
        preferred = ["conversion_rate", "consultation_rate", "favorite_rate", "follow_rate"]
        candidates = list(dict.fromkeys(preferred + requested + ["revenue", "conversions", "consultations", "views"]))
        for metric in candidates:
            if metric in df.columns and pd.to_numeric(df[metric], errors="coerce").notna().any():
                return metric, metric.endswith("_rate"), None, None
            numerator = RATE_NUMERATORS.get(metric)
            if numerator and numerator in df.columns:
                denominator = next(
                    (
                        name
                        for name in RATE_DENOMINATORS[metric]
                        if name in df.columns and pd.to_numeric(df[name], errors="coerce").fillna(0).gt(0).any()
                    ),
                    None,
                )
                if denominator:
                    return metric, True, numerator, denominator
        return None, False, None, None

    @staticmethod
    def _rate_scale(values: list[float]) -> float:
        return 1.0 if max((abs(v) for v in values), default=0.0) > 1 else 100.0

    @staticmethod
    def _display_group(value: Any) -> str:
        raw = str(value)
        return PLATFORM_NAMES.get(raw.lower(), raw)
