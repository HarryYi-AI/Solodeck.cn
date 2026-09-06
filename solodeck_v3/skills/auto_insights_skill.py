from __future__ import annotations

from typing import Any

import pandas as pd

from .base import BaseSkill, SkillOutput


class AutoInsightsSkill(BaseSkill):
    """Deterministic first-pass profiling for broad data-agent questions."""

    name = "AutoInsightsSkill"
    role = "Executor"
    input_schema = {"df": "DataFrame"}
    output_schema = {"observations": "list", "metrics": "list"}

    def run(self, state: dict[str, Any]) -> SkillOutput:
        frame = state.get("df")
        if frame is None or getattr(frame, "empty", True):
            return SkillOutput("auto_insights", "profile_insights", {}, valid=False, warnings=["没有可分析的数据"])

        observations: list[str] = []
        metrics: list[dict[str, Any]] = []
        missing = frame.isna().mean().sort_values(ascending=False)
        if len(missing) and float(missing.iloc[0]) > 0:
            observations.append(f"{missing.index[0]} 缺失最多，占 {float(missing.iloc[0]) * 100:.1f}%")
        else:
            observations.append("主要字段未发现缺失值")

        numeric = frame.select_dtypes(include="number").apply(pd.to_numeric, errors="coerce")
        for column in ("revenue", "conversions", "consultations", "views"):
            if column in numeric.columns:
                value = float(numeric[column].sum(skipna=True))
                metrics.append({"metric": column, "value": value})

        if "platform" in frame.columns and "revenue" in numeric.columns:
            grouped = frame.assign(revenue=pd.to_numeric(frame["revenue"], errors="coerce")).groupby("platform", dropna=True)["revenue"].sum().sort_values(ascending=False)
            if len(grouped):
                observations.append(f"{grouped.index[0]} 的收入合计最高，为 {float(grouped.iloc[0]):,.0f}")

        useful = numeric.loc[:, numeric.nunique(dropna=True) > 1]
        if useful.shape[1] >= 2 and len(useful) >= 3:
            corr = useful.corr().abs()
            pairs = [
                (float(corr.loc[left, right]), left, right)
                for index, left in enumerate(corr.columns)
                for right in corr.columns[index + 1:]
                if pd.notna(corr.loc[left, right])
            ]
            if pairs:
                score, left, right = max(pairs)
                observations.append(f"{left} 与 {right} 的线性相关最明显，相关系数绝对值为 {score:.2f}")

        if len(observations) < 3:
            categorical = [name for name in frame.columns if name not in numeric.columns and frame[name].nunique(dropna=True) > 1]
            if categorical:
                column = categorical[0]
                counts = frame[column].value_counts(dropna=True)
                observations.append(f"{column} 中记录最多的是 {counts.index[0]}，共 {int(counts.iloc[0])} 条")

        content = {
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "observations": observations[:3],
            "metrics": metrics,
        }
        return SkillOutput("auto_insights", "profile_insights", content)
