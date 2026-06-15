from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillOutput:
    artifact_id: str
    artifact_type: str
    content: dict[str, Any]
    valid: bool = True
    warnings: list[str] = field(default_factory=list)


class BaseSkill:
    name = "BaseSkill"
    role = "Executor"
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    preconditions: list[str] = []
    failure_modes: list[str] = []

    def run(self, state: dict[str, Any]) -> SkillOutput:
        raise NotImplementedError

    def validate_output(self, output: SkillOutput) -> dict[str, Any]:
        return {"valid": output.valid and bool(output.content), "issues": output.warnings}

