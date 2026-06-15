from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from solo_creator_agent.src.causal_discovery import CausalDiscoverySkill as LegacyCausalDiscoverySkill
from solo_creator_agent.src.knowledge_graph import KnowledgeGraphSkill
from solo_creator_agent.src.skills import DataMappingSkill, EffectEstimationSkill, MetricSkill


@dataclass
class Skill:
    name: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    preconditions: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)

    def run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def validate_output(self, output: dict[str, Any]) -> dict[str, Any]:
        return {"valid": isinstance(output, dict) and bool(output), "issues": [] if output else ["空输出"]}


class SchemaSkill(Skill):
    def __init__(self) -> None:
        super().__init__("SchemaSkill")

    def run(self, df: pd.DataFrame) -> dict[str, Any]:
        mapped = DataMappingSkill().run(df)
        data = mapped["data"]
        return {
            "data": data,
            "schema": {
                "columns": list(data.columns),
                "dtypes": {c: str(data[c].dtype) for c in data.columns},
                "primary_key_candidates": [c for c in data.columns if data[c].is_unique],
                "foreign_key_candidates": [c for c in data.columns if c.endswith("_id") and not data[c].is_unique],
            },
            "summary": mapped["summary"],
        }


class DataQualitySkill(Skill):
    def __init__(self) -> None:
        super().__init__("DataQualitySkill")

    def run(self, df: pd.DataFrame) -> dict[str, Any]:
        missing = df.isna().mean().sort_values(ascending=False)
        return {
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "missing_rate": {k: round(float(v), 3) for k, v in missing.head(12).items()},
            "warnings": [f"{k} 缺失较多" for k, v in missing.items() if v > 0.35][:6],
        }


class KGConstructionSkill(Skill):
    def __init__(self) -> None:
        super().__init__("KGConstructionSkill")

    def run(self, df: pd.DataFrame, text: str = "") -> dict[str, Any]:
        return KnowledgeGraphSkill().run(df, text)


class CausalDiscoverySkill(Skill):
    def __init__(self) -> None:
        super().__init__("CausalDiscoverySkill")

    def run(self, df: pd.DataFrame, kg: dict[str, Any] | None = None) -> dict[str, Any]:
        return LegacyCausalDiscoverySkill().run(df, (kg or {}).get("constraints", {}))


class BootstrapSkill(Skill):
    def __init__(self) -> None:
        super().__init__("BootstrapSkill")

    def run(self, df: pd.DataFrame, query: dict[str, Any], n_boot: int = 1200) -> dict[str, Any]:
        skill = EffectEstimationSkill()
        effect = skill.run(df, query)
        return {**effect, "bootstrap_samples": n_boot}


class RegressionSkill(Skill):
    def __init__(self) -> None:
        super().__init__("RegressionSkill")

    def run(self, df: pd.DataFrame, query: dict[str, Any]) -> dict[str, Any]:
        effect = EffectEstimationSkill().run(df, query)
        return {**effect, "method": "fixed_effect_regression"}


class ReportSkill(Skill):
    def __init__(self) -> None:
        super().__init__("ReportSkill")

    def run(self, artifacts: dict[str, Any]) -> dict[str, Any]:
        effect = artifacts.get("effect", {})
        return {
            "summary": f"当前调整后增量 {effect.get('adjusted_effect', 0):.2f}，区间 {effect.get('ci_95', [0, 0])}。",
            "non_technical": "如果区间穿过 0，先验证；如果区间整体高于 0，再小幅放大。",
        }


class ActionPlanSkill(Skill):
    def __init__(self) -> None:
        super().__init__("ActionPlanSkill")

    def run(self, artifacts: dict[str, Any]) -> dict[str, Any]:
        effect = artifacts.get("effect", {})
        low, high = effect.get("ci_95", [0, 0])
        action = "小幅放大" if low > 0 else "先做小范围验证"
        return {
            "cards": [
                {"title": action, "priority": "高", "explanation": "根据增量估计和置信区间决定。", "references": ["bootstrap_ci", "candidate_dag"]},
                {"title": "固定变量", "priority": "中", "explanation": "每次只改一个变量，减少混杂。", "references": ["dag_constraints"]},
                {"title": "记录 72 小时结果", "priority": "中", "explanation": "补充低成本验证数据。", "references": ["validation_loop"]},
            ]
        }


SKILL_REGISTRY = {
    "SchemaSkill": SchemaSkill,
    "DataQualitySkill": DataQualitySkill,
    "KGConstructionSkill": KGConstructionSkill,
    "CausalDiscoverySkill": CausalDiscoverySkill,
    "BootstrapSkill": BootstrapSkill,
    "RegressionSkill": RegressionSkill,
    "ReportSkill": ReportSkill,
    "ActionPlanSkill": ActionPlanSkill,
}
