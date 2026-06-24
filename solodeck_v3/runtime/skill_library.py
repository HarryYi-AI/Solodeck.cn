"""Voyager-shaped skill library adapter over existing SoloDeck v3 Skills.

Wraps SKILL_REGISTRY without changing execute_skill_sequence behavior.
Lesson 10 pattern: register, search, topo compose, version on refine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from solodeck_v3.runtime.skill_runtime import SKILL_REGISTRY, execute_skill_sequence


SKILL_DESCRIPTIONS: dict[str, str] = {
    "SchemaSkill": "map columns to standard schema and validate dtypes",
    "DataQualitySkill": "check missing values outliers and data quality issues",
    "KGConstructionSkill": "build knowledge graph context from table and text",
    "CausalDiscoverySkill": "generate candidate causal DAG from data and KG",
    "CausalReadinessSkill": "assess whether causal effect estimation is justified",
    "BootstrapSkill": "bootstrap confidence interval for treatment effect",
    "RegressionSkill": "regression adjustment with confounders fixed effects",
    "DIDSkill": "difference in differences panel causal estimate",
    "CounterfactualSkill": "simulate counterfactual what-if scenarios",
    "ReportSkill": "generate validated report and action cards for user",
}

SKILL_TAGS: dict[str, tuple[str, ...]] = {
    "SchemaSkill": ("schema", "ingest"),
    "DataQualitySkill": ("quality", "repair"),
    "KGConstructionSkill": ("kg", "retrieval"),
    "CausalDiscoverySkill": ("causal", "graph"),
    "CausalReadinessSkill": ("causal", "verify"),
    "BootstrapSkill": ("causal", "statistics"),
    "RegressionSkill": ("causal", "statistics"),
    "DIDSkill": ("causal", "statistics"),
    "CounterfactualSkill": ("causal", "explore"),
    "ReportSkill": ("report", "writer"),
}

SKILL_DEPENDS: dict[str, tuple[str, ...]] = {
    "KGConstructionSkill": ("SchemaSkill", "DataQualitySkill"),
    "CausalDiscoverySkill": ("KGConstructionSkill",),
    "CausalReadinessSkill": ("KGConstructionSkill",),
    "BootstrapSkill": ("CausalReadinessSkill",),
    "RegressionSkill": ("CausalReadinessSkill",),
    "ReportSkill": ("BootstrapSkill", "RegressionSkill"),
}


@dataclass
class SkillMeta:
    name: str
    description: str
    version: int = 1
    tags: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    history: list[str] = field(default_factory=list)


class SoloDeckSkillLibrary:
    """Read-only Voyager adapter; execution delegates to skill_runtime."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillMeta] = {}
        self._bootstrap_from_registry()

    def _bootstrap_from_registry(self) -> None:
        for name in SKILL_REGISTRY:
            self._skills[name] = SkillMeta(
                name=name,
                description=SKILL_DESCRIPTIONS.get(name, name),
                tags=SKILL_TAGS.get(name, ()),
                depends_on=SKILL_DEPENDS.get(name, ()),
            )

    def search(self, query: str, top_k: int = 5, tag_filter: str | None = None) -> list[tuple[float, SkillMeta]]:
        q_tokens = set(query.lower().split())
        scored: list[tuple[float, SkillMeta]] = []
        for skill in self._skills.values():
            if tag_filter and tag_filter not in skill.tags:
                continue
            d_tokens = set(skill.description.lower().split()) | {skill.name.lower()}
            overlap = len(q_tokens & d_tokens)
            if overlap == 0:
                continue
            score = overlap / len(q_tokens | d_tokens)
            scored.append((score, skill))
        scored.sort(key=lambda x: -x[0])
        return scored[:top_k]

    def topo_order(self, names: list[str]) -> list[str]:
        visited: set[str] = set()
        order: list[str] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            meta = self._skills.get(name)
            if meta:
                for dep in meta.depends_on:
                    if dep in self._skills:
                        visit(dep)
            order.append(name)

        for name in names:
            visit(name)
        return order

    def suggest_skills(self, task: str, task_type: str = "") -> list[str]:
        query = f"{task} {task_type}".strip()
        hits = self.search(query, top_k=8)
        names = [skill.name for _, skill in hits]
        if task_type.startswith("causal"):
            for required in ("SchemaSkill", "DataQualitySkill", "KGConstructionSkill", "CausalReadinessSkill", "ReportSkill"):
                if required not in names:
                    names.append(required)
        return self.topo_order(names)

    def refine_from_failure(self, skill_name: str, error: str) -> str:
        """Record failure context; bump version metadata (no code mutation)."""
        meta = self._skills.get(skill_name)
        if meta is None:
            return f"unknown skill: {skill_name}"
        meta.history.append(error[:200])
        meta.version += 1
        return f"refined {skill_name} -> v{meta.version}"

    def execute(self, state: dict[str, Any], skills: list[str] | None = None, task: str = "") -> dict[str, Any]:
        ordered = self.topo_order(skills or self.suggest_skills(task, (state.get("task_spec") or {}).get("task_type", "")))
        ordered = [s for s in ordered if s in SKILL_REGISTRY]
        return execute_skill_sequence(state, ordered)

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {"name": s.name, "version": s.version, "tags": s.tags, "depends_on": s.depends_on, "description": s.description}
            for s in self._skills.values()
        ]


def build_skill_library() -> SoloDeckSkillLibrary:
    return SoloDeckSkillLibrary()
