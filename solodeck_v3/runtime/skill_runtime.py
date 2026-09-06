from __future__ import annotations

from typing import Any

from solodeck_v3.skills.base import SkillOutput
from solodeck_v3.skills.bootstrap_skill import BootstrapSkill
from solodeck_v3.skills.auto_insights_skill import AutoInsightsSkill
from solodeck_v3.skills.causal_discovery_skill import CausalDiscoverySkill
from solodeck_v3.skills.causal_readiness_skill import CausalReadinessSkill
from solodeck_v3.skills.counterfactual_skill import CounterfactualSkill
from solodeck_v3.skills.data_quality_skill import DataQualitySkill
from solodeck_v3.skills.descriptive_comparison_skill import DescriptiveComparisonSkill
from solodeck_v3.skills.did_skill import DIDSkill
from solodeck_v3.skills.kg_construction_skill import KGConstructionSkill
from solodeck_v3.skills.regression_skill import RegressionSkill
from solodeck_v3.skills.report_skill import ReportSkill
from solodeck_v3.skills.schema_skill import SchemaSkill


SKILL_REGISTRY = {
    "SchemaSkill": SchemaSkill,
    "AutoInsightsSkill": AutoInsightsSkill,
    "DataQualitySkill": DataQualitySkill,
    "DescriptiveComparisonSkill": DescriptiveComparisonSkill,
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
        manifest = skill.manifest().to_dict()
        output: SkillOutput = skill.run(state)
        validation = skill.validate_output(output)
        artifact = {
            "id": output.artifact_id, "type": output.artifact_type,
            "content": output.content, "valid": validation["valid"],
            "warnings": output.warnings, "generated_by": skill_name,
            "source_type": "python", "skill_id": manifest["skill_id"],
            "skill_version": manifest["version"], "validator_id": "skill_output_validator",
            "dataset_version": state.get("dataset_version", state.get("trace_id")),
        }
        artifacts = state.setdefault("artifacts", [])
        existing = next((index for index, item in enumerate(artifacts) if item.get("id") == artifact["id"]), None)
        if existing is None:
            artifacts.append(artifact)
        else:
            artifacts[existing] = artifact
        outputs.append(artifact)
        state.setdefault("selected_skills", []).append(skill_name)
        state.setdefault("skill_manifests", {})[skill_name] = manifest
    return {"outputs": outputs, "state": state}
