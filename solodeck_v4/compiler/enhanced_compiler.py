from __future__ import annotations

from typing import Any
from collections import Counter

from solodeck_v3.compiler.task_schema import TaskSpec
from solodeck_v3.compiler.task_compiler import compile_user_goal
from solodeck_v3.nlp.entity_linker import link_entities


TREATMENT_COLUMNS = {"title_style", "platform", "topic", "publish_time", "feature_tags", "production_hours"}
OUTCOME_COLUMNS = {"consultations", "conversions", "revenue", "favorites", "views"}
CAUSAL_COMPARE_MARKERS = ("是否", "是不是", "对比", "相比", "比", "更能", "更适合", "提升", "影响", "变化", "有没有")


def compile_with_session(
    message: str,
    df: Any,
    text: str = "",
    compressed_context: dict[str, Any] | None = None,
    prior_entities: dict[str, Any] | None = None,
) -> TaskSpec:
    """Enhanced compile: entity link + multi-turn context merge."""
    compressed_context = compressed_context or {}
    prior = dict(prior_entities or {})
    prior.update(compressed_context.get("linked_entities") or {})
    current_entity_link = link_entities(message, list(df.columns) if df is not None and not getattr(df, "empty", True) else [], prior)

    columns = list(df.columns) if df is not None and not getattr(df, "empty", True) else []
    merged_message = message
    last_objective = compressed_context.get("last_objective") or ""
    if _is_followup(message) and last_objective:
        merged_message = f"{last_objective}；追问：{message}"

    entity_link = link_entities(merged_message, columns, prior)
    spec = compile_user_goal(merged_message, df, text, previous_memory={"linked_entities": entity_link.get("linked_entities", [])})

    linked_entities = entity_link.get("linked_entities") or []
    current_linked_entities = current_entity_link.get("linked_entities") or []
    if linked_entities:
        treatments = _rank_linked_treatments(current_linked_entities, columns)
        outcomes = [e["column"] for e in current_linked_entities if e.get("column") in OUTCOME_COLUMNS and e.get("column") in columns]
        if not treatments:
            treatments = _rank_linked_treatments(linked_entities, columns)
        if not outcomes:
            outcomes = [e["column"] for e in linked_entities if e.get("column") in OUTCOME_COLUMNS and e.get("column") in columns]
        if treatments:
            spec.candidate_treatments = list(dict.fromkeys(treatments + spec.candidate_treatments))
        if outcomes:
            spec.candidate_outcomes = list(dict.fromkeys(outcomes + spec.candidate_outcomes))

    if _should_upgrade_to_causal(merged_message, spec, linked_entities):
        spec.task_type = "causal_effect_estimation"
        spec.budget_level = "deep_path"
        spec.candidate_treatments = _prioritize(spec.candidate_treatments, TREATMENT_COLUMNS)
        spec.candidate_outcomes = _prioritize(spec.candidate_outcomes, OUTCOME_COLUMNS)
        for artifact in ["kg_context", "causal_readiness", "bootstrap_ci"]:
            if artifact not in spec.expected_artifacts:
                spec.expected_artifacts.append(artifact)

    spec.constraints.append("entity_link_checked")
    return spec


def _is_followup(message: str) -> bool:
    markers = ("那个", "上次", "继续", "呢", "还是", "换成", "同样", "再算")
    return any(m in (message or "") for m in markers)


def _should_upgrade_to_causal(message: str, spec: TaskSpec, linked_entities: list[dict[str, Any]]) -> bool:
    if spec.task_type in {"causal_effect_estimation", "counterfactual_analysis", "experiment_design"}:
        return True
    if not any(marker in (message or "") for marker in CAUSAL_COMPARE_MARKERS):
        return False
    linked_columns = {item.get("column") for item in linked_entities if item.get("column")}
    has_treatment = bool(linked_columns & TREATMENT_COLUMNS) or bool(set(spec.candidate_treatments) & TREATMENT_COLUMNS)
    has_outcome = bool(linked_columns & OUTCOME_COLUMNS) or bool(set(spec.candidate_outcomes) & OUTCOME_COLUMNS)
    return has_treatment and has_outcome


def _prioritize(values: list[str], preferred: set[str]) -> list[str]:
    head = [value for value in values if value in preferred]
    tail = [value for value in values if value not in preferred]
    return list(dict.fromkeys(head + tail))


def _rank_linked_treatments(entities: list[dict[str, Any]], columns: list[str]) -> list[str]:
    linked = [item["column"] for item in entities if item.get("column") in TREATMENT_COLUMNS and item.get("column") in columns]
    counts = Counter(linked)
    first_seen = {column: linked.index(column) for column in counts}
    return sorted(counts, key=lambda column: (-counts[column], first_seen[column]))
