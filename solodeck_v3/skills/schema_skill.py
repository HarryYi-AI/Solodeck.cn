from __future__ import annotations

import pandas as pd

from solo_creator_agent.src.skills import DataMappingSkill

from .base import BaseSkill, SkillOutput


class SchemaSkill(BaseSkill):
    name = "SchemaSkill"

    def run(self, state: dict) -> SkillOutput:
        mapped = DataMappingSkill().run(state["df"])
        data = mapped["data"]
        state["df"] = data
        summary = {
            **mapped["summary"],
            "dtypes": {c: str(data[c].dtype) for c in data.columns},
            "primary_keys": [c for c in data.columns if data[c].is_unique][:8],
            "foreign_key_candidates": [c for c in data.columns if c.endswith("_id") and not data[c].is_unique],
        }
        state["schema_summary"] = summary
        return SkillOutput("schema_summary", "schema", summary)

