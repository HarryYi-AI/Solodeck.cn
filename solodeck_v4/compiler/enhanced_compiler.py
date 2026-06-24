from __future__ import annotations

from typing import Any

from solodeck_v3.compiler.task_schema import TaskSpec
from solodeck_v3.compiler.task_compiler import compile_user_goal
from solodeck_v3.nlp.entity_linker import link_entities


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

    columns = list(df.columns) if df is not None and not getattr(df, "empty", True) else []
    merged_message = message
    last_objective = compressed_context.get("last_objective") or ""
    if _is_followup(message) and last_objective:
        merged_message = f"{last_objective}；追问：{message}"

    entity_link = link_entities(merged_message, columns, prior)
    spec = compile_user_goal(merged_message, df, text, previous_memory={"linked_entities": entity_link.get("linked_entities", [])})

    if entity_link.get("linked_entities"):
        treatments = [e["column"] for e in entity_link["linked_entities"] if e.get("column") in columns]
        outcomes = [e["column"] for e in entity_link["linked_entities"] if e.get("canonical") in {"consultations", "conversions", "revenue", "views"} and e.get("column") in columns]
        if treatments:
            spec.candidate_treatments = list(dict.fromkeys(treatments + spec.candidate_treatments))
        if outcomes:
            spec.candidate_outcomes = list(dict.fromkeys(outcomes + spec.candidate_outcomes))

    spec.constraints.append("entity_link_checked")
    return spec


def _is_followup(message: str) -> bool:
    markers = ("那个", "上次", "继续", "呢", "还是", "换成", "同样", "再算")
    return any(m in (message or "") for m in markers)
