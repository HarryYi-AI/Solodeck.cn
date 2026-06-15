from __future__ import annotations

from typing import Any

from solodeck_v3.skills.base import SkillOutput
from solodeck_v3.skills.bootstrap_skill import BootstrapSkill
from solodeck_v3.skills.causal_discovery_skill import CausalDiscoverySkill
from solodeck_v3.skills.causal_readiness_skill import CausalReadinessSkill
from solodeck_v3.skills.counterfactual_skill import CounterfactualSkill
from solodeck_v3.skills.data_quality_skill import DataQualitySkill
from solodeck_v3.skills.did_skill import DIDSkill
from solodeck_v3.skills.kg_construction_skill import KGConstructionSkill
from solodeck_v3.skills.regression_skill import RegressionSkill
from solodeck_v3.skills.report_skill import ReportSkill
from solodeck_v3.skills.schema_skill import SchemaSkill


SKILL_REGISTRY = {
    "SchemaSkill": SchemaSkill,
    "DataQualitySkill": DataQualitySkill,
    "DIDSkill": DIDSkill,
    "KGConstructionSkill": KGConstructionSkill,
    "CausalDiscoverySkill": CausalDiscoverySkill,
    "CausalReadinessSkill": CausalReadinessSkill,
    "BootstrapSkill": BootstrapSkill,
    "RegressionSkill": RegressionSkill,
    "CounterfactualSkill": CounterfactualSkill,
    "ReportSkill": ReportSkill,
}


def execute_skill_sequence(state: dict[str, Any], skills: list[str]) -> dict[str, Any]:
    outputs = []
    for skill_name in skills:
        skill_cls = SKILL_REGISTRY[skill_name]
        skill = skill_cls()
        output: SkillOutput = skill.run(state)
        validation = skill.validate_output(output)
        artifact = {"id": output.artifact_id, "type": output.artifact_type, "content": output.content, "valid": validation["valid"], "warnings": output.warnings, "generated_by": skill_name}
        if artifact["id"] not in {a.get("id") for a in state.setdefault("artifacts", [])}:
            state["artifacts"].append(artifact)
        outputs.append(artifact)
        state.setdefault("selected_skills", []).append(skill_name)
    return {"outputs": outputs, "state": state}
