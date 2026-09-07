from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Callable

from .schemas import DecisionEpisode, MemoryQueryPlan
from .store import SQLiteDecisionMemoryStore


SimilarityFunction = Callable[[str, str], float]


def retrieve_decision_episodes(
    query: str,
    project_id: str,
    plan: MemoryQueryPlan,
    store: SQLiteDecisionMemoryStore,
    *,
    limit: int = 8,
    similarity_fn: SimilarityFunction | None = None,
) -> list[dict[str, Any]]:
    filters = {key: value for key, value in plan.filters.items() if key in {"platform", "topic", "content_format"}}
    candidates = store.list_episodes(project_id, limit=max(limit * 10, 50), **filters)
    similarity_fn = similarity_fn or lexical_similarity
    now = datetime.now(timezone.utc)
    ranked = []
    for episode in candidates:
        semantic = similarity_fn(query, _episode_text(episode))
        context = context_match(episode, plan.filters)
        recency = recency_score(episode.timestamp, now)
        outcome = outcome_relevance(episode, plan.filters.get("metric", ""))
        score = 0.35 * semantic + 0.30 * context + 0.15 * recency + 0.20 * outcome
        ranked.append((score, episode.timestamp, episode))
    return [
        {**episode.to_dict(), "retrieval_score": round(score, 4)}
        for score, _, episode in sorted(ranked, key=lambda row: (row[0], row[1]), reverse=True)[:limit]
    ]


def retrieve_strategy_evidence(
    project_id: str,
    plan: MemoryQueryPlan,
    store: SQLiteDecisionMemoryStore,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    filters = {key: value for key, value in plan.filters.items() if key in {"platform", "topic", "content_format"}}
    return [item.to_dict() for item in store.list_strategy_evidence(project_id, limit=limit, **filters)]


def lexical_similarity(left: str, right: str) -> float:
    left_terms, right_terms = _terms(left), _terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / math.sqrt(len(left_terms) * len(right_terms))


def context_match(episode: DecisionEpisode, filters: dict[str, str]) -> float:
    context = episode.decision_context.to_dict()
    keys = [key for key in ("platform", "topic", "account_stage", "content_format") if filters.get(key)]
    metric = filters.get("metric")
    scores = [1.0 if str(context.get(key, "")).lower() == str(filters[key]).lower() else 0.0 for key in keys]
    if metric:
        scores.append(1.0 if metric in episode.evidence.metrics else 0.0)
    return sum(scores) / len(scores) if scores else 0.5


def recency_score(timestamp: str, now: datetime | None = None, half_life_days: float = 90.0) -> float:
    now = now or datetime.now(timezone.utc)
    try:
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        age_days = max(0.0, (now - moment).total_seconds() / 86400)
    except (TypeError, ValueError):
        return 0.0
    return math.exp(-math.log(2) * age_days / half_life_days)


def outcome_relevance(episode: DecisionEpisode, metric: str) -> float:
    outcome = episode.outcome
    if not outcome.observed:
        return 0.1
    metric_match = 1.0 if metric and metric in outcome.metrics else 0.5
    return min(1.0, metric_match + (0.2 if outcome.success is not None else 0.0))


def _episode_text(episode: DecisionEpisode) -> str:
    context = " ".join(str(value) for value in episode.decision_context.to_dict().values() if value)
    metrics = " ".join(episode.evidence.metrics)
    return f"{context} {metrics} {episode.decision.strategy} {episode.decision.reason}"


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+|[一-鿿]", (value or "").lower()))
