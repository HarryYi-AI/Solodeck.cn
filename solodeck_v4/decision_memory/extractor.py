from __future__ import annotations

from numbers import Real
from typing import Any

from .evidence import EvidenceLevel
from .schemas import (
    DecisionContext,
    DecisionEpisode,
    DecisionFact,
    DecisionOutcome,
    EpisodeDecision,
    EpisodeEvidence,
)


CAUSAL_SKILL_MARKERS = ("effect", "causal", "bootstrap", "regression", "iptw", "dml", "did")


def extract_decision_episode(
    analysis: dict[str, Any],
    *,
    user_id: str,
    project_id: str,
    data_source_ids: list[str] | None = None,
    outcome: DecisionOutcome | None = None,
) -> DecisionEpisode | None:
    """Extract from structured runtime state; never infer metrics from prose."""
    artifacts = analysis.get("artifacts") or []
    cards = analysis.get("action_cards") or (analysis.get("user_artifact") or {}).get("action_cards") or []
    task_spec = analysis.get("task_spec") or {}
    if not artifacts and not cards:
        return None

    frame = analysis.get("df")
    entity_link = analysis.get("entity_link") or {}
    linked = entity_link.get("linked_entities") or []
    context = DecisionContext(
        platform=_context_value("platform", linked, frame),
        topic=_context_value("topic", linked, frame),
        account_stage=_context_value("account_stage", linked, frame),
        follower_count=_single_numeric("follower_count", frame),
        content_format=_context_value("content_format", linked, frame),
        time_window=str(task_spec.get("time_window") or ""),
    )
    metrics = _artifact_metrics(artifacts)
    skills = list(dict.fromkeys(analysis.get("selected_skills") or []))
    causal_methods = [skill for skill in skills if any(marker in skill.lower() for marker in CAUSAL_SKILL_MARKERS)]
    evidence_level = _evidence_level(analysis, causal_methods)
    validation = analysis.get("validation_report") or {}
    sample_sizes = [int(value) for value in _find_values(artifacts, {"sample_size", "n", "n_total"}) if _positive_int(value)]
    card = cards[0] if cards else {}
    reason = str(card.get("evidence") or (analysis.get("user_artifact") or {}).get("result") or "")
    confidence = _confidence(analysis, evidence_level)
    strategy = str(card.get("strategy") or card.get("title") or card.get("action") or task_spec.get("objective") or "").strip()
    if not strategy:
        return None
    return DecisionEpisode(
        user_id=user_id,
        project_id=project_id,
        trace_id=str(analysis.get("trace_id") or ""),
        decision_context=context,
        evidence=EpisodeEvidence(
            data_source_ids=list(data_source_ids or []),
            metrics=metrics,
            sample_size=max(sample_sizes, default=len(frame) if frame is not None else 0),
            statistical_tests=skills,
            causal_methods=causal_methods,
            evidence_level=evidence_level,
            confounder_checked=bool(causal_methods and task_spec.get("candidate_confounders")),
            verifier_passed=bool(validation.get("valid", not validation.get("issues"))),
        ),
        decision=EpisodeDecision(strategy=strategy[:500], reason=reason[:800], confidence=confidence),
        outcome=outcome or DecisionOutcome(),
    )


def extract_atomic_facts(episode: DecisionEpisode) -> list[DecisionFact]:
    facts: list[DecisionFact] = []
    context = episode.decision_context.to_dict()
    for key, value in context.items():
        if value not in (None, ""):
            facts.append(DecisionFact(
                fact_id=f"fact_{episode.episode_id}_{key}",
                project_id=episode.project_id, source_episode_id=episode.episode_id,
                fact_key=key, fact_value=value, confidence=episode.decision.confidence,
                valid_from=episode.timestamp,
            ))
    for key, value in episode.evidence.metrics.items():
        facts.append(DecisionFact(
            fact_id=f"fact_{episode.episode_id}_{key}",
            project_id=episode.project_id, source_episode_id=episode.episode_id,
            fact_key=key, fact_value=value, confidence=episode.decision.confidence,
            valid_from=episode.timestamp,
        ))
    return facts


def _artifact_metrics(artifacts: list[dict[str, Any]]) -> dict[str, float]:
    preferred = {
        "effect_estimate", "adjusted_effect", "ate", "relative_lift", "ci_low", "ci_high",
        "conversion_rate", "consultation_rate", "favorite_rate", "save_rate", "ctr",
        "revenue", "conversions", "consultations", "views", "mean", "value",
    }
    metrics: dict[str, float] = {}
    for artifact in artifacts:
        content = artifact.get("content") or {}
        for key, value in _walk_numeric(content):
            if key in preferred and key not in metrics:
                metrics[key] = float(value)
    return dict(list(metrics.items())[:24])


def _walk_numeric(value: Any, key: str = ""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _walk_numeric(child, str(child_key))
    elif isinstance(value, list):
        for child in value[:20]:
            yield from _walk_numeric(child, key)
    elif isinstance(value, Real) and not isinstance(value, bool):
        yield key, value


def _find_values(value: Any, keys: set[str]) -> list[Any]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys:
                found.append(child)
            found.extend(_find_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_values(child, keys))
    return found


def _evidence_level(analysis: dict[str, Any], causal_methods: list[str]) -> str:
    task_type = (analysis.get("task_spec") or {}).get("task_type", "")
    if task_type in {"ab_test_analysis", "randomized_experiment"}:
        return EvidenceLevel.EXPERIMENTAL.value
    if causal_methods:
        return EvidenceLevel.ADJUSTED.value
    return EvidenceLevel.OBSERVATIONAL.value


def _confidence(analysis: dict[str, Any], evidence_level: str) -> float:
    validation = analysis.get("validation_report") or {}
    base = {"observational": 0.45, "adjusted": 0.65, "experimental": 0.8}[evidence_level]
    if validation.get("valid") is True:
        base += 0.1
    if validation.get("issues"):
        base -= min(0.25, len(validation["issues"]) * 0.05)
    return round(max(0.05, min(base, 0.95)), 3)


def _context_value(column: str, linked: list[dict[str, Any]], frame: Any) -> str:
    for item in linked:
        if item.get("column") == column and item.get("mention"):
            return str(item["mention"])
    if frame is not None and column in getattr(frame, "columns", []):
        values = frame[column].dropna().astype(str).unique().tolist()
        if len(values) == 1:
            return values[0]
    return ""


def _single_numeric(column: str, frame: Any) -> float | None:
    if frame is None or column not in getattr(frame, "columns", []):
        return None
    values = frame[column].dropna().unique().tolist()
    return float(values[0]) if len(values) == 1 and isinstance(values[0], Real) else None


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False
