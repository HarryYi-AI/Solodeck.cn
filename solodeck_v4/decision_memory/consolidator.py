from __future__ import annotations

import re
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .evidence import can_promote_to_strategy_candidate, strongest_level
from .schemas import BusinessRegime, CreatorProfile, StrategyEvidence, StrategySkillCandidate, utc_now
from .store import SQLiteDecisionMemoryStore


def consolidate_decision_episodes(
    project_id: str,
    window_days: int,
    store: SQLiteDecisionMemoryStore,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, window_days))
    episodes = [episode for episode in store.list_episodes(project_id, limit=500) if _moment(episode.timestamp) >= cutoff]
    evidence = [item for item in store.list_strategy_evidence(project_id, limit=500) if _moment(item.created_at) >= cutoff]
    grouped: dict[tuple[str, str, str, str], list[StrategyEvidence]] = defaultdict(list)
    for item in evidence:
        key = (
            item.strategy,
            str(item.context.get("platform", "")),
            str(item.context.get("topic", "")),
            str(item.context.get("content_format", "")),
        )
        grouped[key].append(item)

    candidates, contradictions, insufficient = [], [], []
    successful_topics, successful_formats, strengths = set(), set(), set()
    regime_candidates = []
    for (strategy, platform, topic, content_format), items in grouped.items():
        successes = sum(item.success is True for item in items)
        failures = sum(item.success is False for item in items)
        observed = successes + failures
        if successes and failures:
            contradictions.append({
                "strategy": strategy, "scope": {"platform": platform, "topic": topic, "content_format": content_format},
                "success_count": successes, "failure_count": failures,
            })
        if not can_promote_to_strategy_candidate(len(items), contradiction_count=min(successes, failures)):
            insufficient.append({"strategy": strategy, "evidence_count": len(items), "reason": "证据不足，至少需要 3 次同场景记录。"})
            continue
        level = strongest_level(item.evidence_level for item in items)
        confidence = min(0.9, 0.35 + 0.08 * len(items) + 0.12 * (successes / max(1, observed)))
        candidate = StrategySkillCandidate(
            candidate_id=_candidate_id(project_id, strategy, platform, topic, content_format),
            project_id=project_id,
            name=_candidate_name(strategy, platform, topic, content_format),
            applicability={key: value for key, value in {"platform": platform, "topic": topic, "content_format": content_format}.items() if value},
            procedure=[strategy, "记录执行前指标", "按相同口径记录执行后指标", "交由校验器复核"],
            evidence_episode_ids=list(dict.fromkeys(item.source_episode_id for item in items)),
            success_count=successes,
            failure_count=failures,
            evidence_level=level,
            confidence=round(confidence, 3),
            verifier_passed=False,
            human_approved=False,
        )
        candidates.append(candidate)
        if persist:
            store.save_candidate(candidate)
        if successes >= 3 and successes > failures:
            if topic:
                successful_topics.add(topic)
            if content_format:
                successful_formats.add(content_format)
            strengths.add(strategy)
            regime_candidates.append(BusinessRegime(
                project_id=project_id,
                scope={key: value for key, value in {"platform": platform, "topic": topic, "content_format": content_format}.items() if value},
                description=f"在当前场景中，策略“{strategy}”重复表现较好。",
                valid_from=min(item.created_at for item in items),
                evidence_episode_ids=candidate.evidence_episode_ids,
                confidence=candidate.confidence,
                status="candidate",
            ))

    profile_update = None
    if len(episodes) >= 3 and (strengths or successful_topics or successful_formats):
        previous = store.get_profile(project_id)
        profile_update = CreatorProfile(
            project_id=project_id,
            strengths=sorted(strengths),
            effective_formats=sorted(successful_formats),
            effective_topics=sorted(successful_topics),
            weak_evidence_areas=sorted({item["strategy"] for item in insufficient}),
            risk_preferences=(previous.risk_preferences if previous else {}),
            confidence={"overall": round(min(0.9, 0.4 + 0.05 * len(episodes)), 3)},
            evidence_count={"episodes": len(episodes), "strategy_evidence": len(evidence)},
            evidence_episode_ids=[episode.episode_id for episode in episodes],
            version=(previous.version + 1 if previous else 1),
            updated_at=utc_now(),
        )
        if persist:
            store.save_profile(profile_update)

    return {
        "profile_updates": profile_update.to_dict() if profile_update else {},
        "regime_candidates": [item.to_dict() for item in regime_candidates],
        "strategy_skill_candidates": [item.to_dict() for item in candidates],
        "contradictions": contradictions,
        "temporal_drift": _detect_temporal_drift(evidence),
        "insufficient_evidence": insufficient,
        "episode_count": len(episodes),
    }


def _candidate_name(strategy: str, platform: str, topic: str, content_format: str) -> str:
    raw = "_".join(value for value in (strategy, platform, topic, content_format) if value)
    words = re.findall(r"[A-Za-z0-9]+|[一-鿿]+", raw)
    return "Strategy_" + "_".join(words)[:100]


def _candidate_id(project_id: str, strategy: str, platform: str, topic: str, content_format: str) -> str:
    raw = "|".join((project_id, strategy, platform, topic, content_format))
    return f"skill_candidate_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _detect_temporal_drift(evidence: list[StrategyEvidence]) -> list[dict[str, Any]]:
    by_scope: dict[tuple[str, str, str], list[StrategyEvidence]] = defaultdict(list)
    for item in evidence:
        by_scope[(
            str(item.context.get("platform", "")),
            str(item.context.get("topic", "")),
            str(item.context.get("content_format", "")),
        )].append(item)
    drift = []
    for scope, items in by_scope.items():
        ordered = sorted(items, key=lambda item: item.created_at)
        if len(ordered) < 6:
            continue
        midpoint = len(ordered) // 2
        old_best = _best_observed_strategy(ordered[:midpoint])
        new_best = _best_observed_strategy(ordered[midpoint:])
        if old_best and new_best and old_best != new_best:
            drift.append({
                "scope": {key: value for key, value in zip(("platform", "topic", "content_format"), scope) if value},
                "historical_strategy": old_best,
                "recent_strategy": new_best,
                "status": "candidate",
                "reason": "前后时间段中表现最好的策略发生变化，需要实时数据复核后再切换业务阶段。",
            })
    return drift


def _best_observed_strategy(items: list[StrategyEvidence]) -> str:
    scores: dict[str, list[bool]] = defaultdict(list)
    for item in items:
        if item.success is not None:
            scores[item.strategy].append(item.success)
    if not scores:
        return ""
    return max(scores, key=lambda strategy: (sum(scores[strategy]) / len(scores[strategy]), len(scores[strategy])))


def _moment(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
