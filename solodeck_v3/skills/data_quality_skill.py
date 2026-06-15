from __future__ import annotations

from .base import BaseSkill, SkillOutput


class DataQualitySkill(BaseSkill):
    name = "DataQualitySkill"

    def run(self, state: dict) -> SkillOutput:
        df = state["df"]
        missing = df.isna().mean().sort_values(ascending=False)
        report = {
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "missing_rate": {k: round(float(v), 3) for k, v in missing.head(15).items()},
            "warnings": [f"{k} 缺失率较高" for k, v in missing.items() if v > 0.35][:8],
        }
        state["data_quality_report"] = report
        return SkillOutput("data_quality_report", "quality_report", report, valid=True, warnings=report["warnings"])

