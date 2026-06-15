from __future__ import annotations

from typing import Any

import pandas as pd

from .base import BaseSkill, SkillOutput
from .bootstrap_skill import _infer_treatment_value


class DIDSkill(BaseSkill):
    name = "DIDSkill"

    def run(self, state: dict) -> SkillOutput:
        spec = state["task_spec"]
        df = state["df"].copy()
        treatment = (spec.get("candidate_treatments") or ["title_style"])[0]
        outcome = (spec.get("candidate_outcomes") or ["revenue"])[0]
        time_col = _time_column(df)
        value = _infer_treatment_value(str(state.get("task", "")), treatment, df)
        warnings: list[str] = []
        result: dict[str, Any] = {
            "method": "difference_in_differences",
            "treatment": treatment,
            "treatment_value": value,
            "outcome": outcome,
            "time_col": time_col,
            "effect": None,
            "sample_size": int(len(df)),
            "claim_level": "exploratory",
            "warnings": warnings,
        }
        if not time_col or treatment not in df.columns or outcome not in df.columns:
            warnings.append("缺少时间、处理变量或结果指标，DID 已降级为不可估计。")
            return _record(state, result, warnings)
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        data = df.dropna(subset=[time_col, treatment, outcome]).copy()
        if len(data) < 8 or data[treatment].nunique(dropna=True) < 2:
            warnings.append("样本或对照组不足，DID 仅保留为探索性检查。")
            return _record(state, result, warnings)
        cutoff = data[time_col].median()
        data["_post"] = (data[time_col] >= cutoff).astype(int)
        data["_treated"] = data[treatment].astype(str).eq(str(value)).astype(int)
        cells = data.groupby(["_treated", "_post"])[outcome].mean()
        required = {(0, 0), (0, 1), (1, 0), (1, 1)}
        if not required.issubset(set(cells.index)):
            warnings.append("缺少 DID 四个基本单元，无法稳定估计。")
            return _record(state, result, warnings)
        effect = float((cells.loc[(1, 1)] - cells.loc[(1, 0)]) - (cells.loc[(0, 1)] - cells.loc[(0, 0)]))
        result.update({
            "effect": effect,
            "cutoff": cutoff.isoformat() if hasattr(cutoff, "isoformat") else str(cutoff),
            "cell_means": {f"treated={k[0]},post={k[1]}": float(v) for k, v in cells.items()},
            "claim_level": "quasi_experimental_estimate",
        })
        if len(data) < 30:
            warnings.append("样本少于 30，DID 结果需要继续验证。")
        return _record(state, result, warnings)


def _time_column(df) -> str | None:
    for col in ["publish_time", "date", "time", "created_at"]:
        if col in df.columns:
            return col
    return None


def _record(state: dict, result: dict, warnings: list[str]) -> SkillOutput:
    state.setdefault("artifacts", []).append({"id": "did_effect", "type": "did_effect", "content": result, "warnings": warnings, "generated_by": "DIDSkill"})
    return SkillOutput("did_effect", "did_effect", result, valid=True, warnings=warnings)

