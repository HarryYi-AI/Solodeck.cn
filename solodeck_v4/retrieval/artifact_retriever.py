from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from solodeck_v4.retrieval.memory_store import MemoryStore

ARTIFACT_TYPES = {
    "analysis": 1.0,
    "bootstrap_ci": 0.95,
    "causal_readiness": 0.95,
    "dag_summary": 0.9,
    "validation_report": 0.85,
    "action_card": 0.8,
    "report": 0.75,
}


def retrieve_artifacts(
    query: str,
    task_spec: dict[str, Any],
    session_artifacts: dict[str, Any] | None = None,
    store: MemoryStore | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    store = store or MemoryStore()
    pool: list[dict[str, Any]] = []

    for art in store.artifacts():
        pool.append(_normalize_artifact(art, source="memory"))

    for art_id, art in (session_artifacts or {}).items():
        normalized = _normalize_artifact(art, source="session")
        normalized["source_id"] = art_id
        pool.append(normalized)

    q = query or ""
    task_type = task_spec.get("task_type") or ""
    treatments = set(task_spec.get("candidate_treatments") or [])
    outcomes = set(task_spec.get("candidate_outcomes") or [])

    hits: list[dict[str, Any]] = []
    for art in pool:
        score = _rank_artifact(art, q, task_type, treatments, outcomes)
        if score <= 0.05:
            continue
        used_for = _used_for(art.get("artifact_type", ""))
        hits.append(
            {
                "source_type": "artifact",
                "source_id": art.get("source_id") or art.get("id") or "artifact:unknown",
                "content": _artifact_content(art),
                "score": score,
                "used_for": used_for,
                "meta": {
                    "artifact_type": art.get("artifact_type"),
                    "task_type": art.get("task_type"),
                    "recency": art.get("time") or art.get("created_at"),
                    "generated_by": art.get("generated_by"),
                    "skill_id": art.get("skill_id"),
                    "validator_id": art.get("validator_id"),
                    "dataset_version": art.get("dataset_version"),
                },
                "artifact_id": art.get("source_id") or art.get("id"),
                "skill_id": art.get("skill_id"),
                "validator_id": art.get("validator_id"),
                "dataset_version": art.get("dataset_version"),
            }
        )

    return sorted(hits, key=lambda x: x["score"], reverse=True)[:limit]


def retrieve_session_turns(
    query: str,
    session_history: list[dict[str, Any]] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    q = (query or "").lower()
    for idx, turn in enumerate(reversed(session_history or [])):
        role = turn.get("role", "")
        content = turn.get("content") or ""
        score = 0.3
        if any(tok in content.lower() for tok in re.findall(r"[\u4e00-\u9fff]{2,}", q)):
            score += 0.4
        if role == "assistant" and any(m in (query or "") for m in ("上次", "之前", "继续", "那个")):
            score += 0.35
        score += max(0, 0.2 - idx * 0.04)
        hits.append(
            {
                "source_type": "session",
                "source_id": turn.get("turn_id") or f"session:turn:{len(session_history) - idx}",
                "content": content[:400],
                "score": min(score, 1.0),
                "used_for": "context",
                "meta": {"role": role},
            }
        )
    return sorted(hits, key=lambda x: x["score"], reverse=True)[:limit]


def _normalize_artifact(art: dict[str, Any], source: str) -> dict[str, Any]:
    content = art.get("content")
    if isinstance(content, dict):
        text = " ".join(str(v) for v in content.values())
    else:
        text = str(content or art.get("summary") or "")
    return {
        "source_id": art.get("id") or art.get("artifact_id"),
        "artifact_type": art.get("type") or art.get("artifact_type") or "analysis",
        "task_type": art.get("task_type") or art.get("generated_by", ""),
        "variables": art.get("variables") or art.get("metrics") or [],
        "text": text,
        "time": art.get("time") or art.get("created_at"),
        "origin": source,
        **art,
    }


def _rank_artifact(
    art: dict[str, Any],
    query: str,
    task_type: str,
    treatments: set[str],
    outcomes: set[str],
) -> float:
    score = ARTIFACT_TYPES.get(art.get("artifact_type", ""), 0.4)
    text = (art.get("text") or "").lower()
    q = query.lower()

    if art.get("task_type") and task_type and art.get("task_type") == task_type:
        score += 0.25

    variables = set(art.get("variables") or [])
    if variables & (treatments | outcomes):
        score += 0.3

    for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z_]+", q):
        if len(token) >= 2 and token.lower() in text:
            score += 0.08

    recency = art.get("time") or art.get("created_at")
    if recency:
        try:
            ts = datetime.fromisoformat(str(recency).replace("Z", "+00:00"))
            age_days = (datetime.now(ts.tzinfo) - ts).days if ts.tzinfo else 0
            score += max(0, 0.15 - age_days * 0.01)
        except ValueError:
            pass
    return min(score, 1.0)


def _artifact_content(art: dict[str, Any]) -> str:
    prefix = art.get("artifact_type") or "artifact"
    text = art.get("text") or ""
    return f"[{prefix}] {text[:360]}"


def _used_for(artifact_type: str) -> str:
    if artifact_type in {"bootstrap_ci", "causal_readiness", "dag_summary"}:
        return "causal_check"
    if artifact_type in {"validation_report"}:
        return "report"
    if artifact_type in {"analysis", "report"}:
        return "calculation"
    return "context"
