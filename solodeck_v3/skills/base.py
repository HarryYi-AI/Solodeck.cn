from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SkillOutput:
    artifact_id: str
    artifact_type: str
    content: dict[str, Any]
    valid: bool = True
    warnings: list[str] = field(default_factory=list)


@dataclass
class SkillManifest:
    skill_id: str
    skill_name: str
    purpose: str
    activation_condition: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_memory: list[str]
    tool_dependencies: list[str]
    execution_steps: list[str]
    validators: list[str]
    failure_modes: list[str]
    termination_condition: str
    examples: list[dict[str, Any]]
    version: str = "1.0.0"
    success_rate: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseSkill:
    name = "BaseSkill"
    role = "Executor"
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    preconditions: list[str] = []
    failure_modes: list[str] = []

    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id=self.name.lower(), skill_name=self.name,
            purpose=(self.__doc__ or self.name).strip().split("\n")[0],
            activation_condition="由 TaskSpec、Router 与因果声明治理共同选择",
            input_schema=dict(self.input_schema), output_schema=dict(self.output_schema),
            required_memory=[], tool_dependencies=["python"],
            execution_steps=["验证输入", "执行确定性计算", "生成结构化工件", "校验输出"],
            validators=["artifact_validator", "claim_validator"],
            failure_modes=list(self.failure_modes),
            termination_condition="输出通过技能级校验或返回明确失败原因", examples=[],
        )

    def run(self, state: dict[str, Any]) -> SkillOutput:
        raise NotImplementedError

    def validate_output(self, output: SkillOutput) -> dict[str, Any]:
        return {"valid": output.valid and bool(output.content), "issues": output.warnings}
