from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Serializable:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionContext(Serializable):
    platform: str = ""
    topic: str = ""
    account_stage: str = ""
    follower_count: float | None = None
    content_format: str = ""
    time_window: str = ""


@dataclass
class EpisodeEvidence(Serializable):
    data_source_ids: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    sample_size: int = 0
    statistical_tests: list[str] = field(default_factory=list)
    causal_methods: list[str] = field(default_factory=list)
    evidence_level: str = "observational"
    confounder_checked: bool = False
    verifier_passed: bool = False


@dataclass
class EpisodeDecision(Serializable):
    strategy: str = ""
    reason: str = ""
    confidence: float = 0.0


@dataclass
class DecisionOutcome(Serializable):
    observed: bool = False
    metrics: dict[str, float] = field(default_factory=dict)
    success: bool | None = None
    observed_at: str | None = None


@dataclass
class DecisionEpisode(Serializable):
    user_id: str
    project_id: str
    decision_context: DecisionContext
    evidence: EpisodeEvidence
    decision: EpisodeDecision
    outcome: DecisionOutcome = field(default_factory=DecisionOutcome)
    episode_id: str = field(default_factory=lambda: f"episode_{uuid4().hex}")
    timestamp: str = field(default_factory=utc_now)
    trace_id: str = ""


@dataclass
class DecisionFact(Serializable):
    project_id: str
    source_episode_id: str
    fact_key: str
    fact_value: Any
    confidence: float
    valid_from: str
    valid_to: str | None = None
    fact_id: str = field(default_factory=lambda: f"fact_{uuid4().hex}")


@dataclass
class BusinessRegime(Serializable):
    project_id: str
    scope: dict[str, str]
    description: str
    valid_from: str
    evidence_episode_ids: list[str]
    confidence: float
    valid_to: str | None = None
    status: str = "candidate"
    regime_id: str = field(default_factory=lambda: f"regime_{uuid4().hex}")


@dataclass
class CreatorProfile(Serializable):
    project_id: str
    strengths: list[str] = field(default_factory=list)
    effective_formats: list[str] = field(default_factory=list)
    effective_topics: list[str] = field(default_factory=list)
    weak_evidence_areas: list[str] = field(default_factory=list)
    risk_preferences: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    evidence_count: dict[str, int] = field(default_factory=dict)
    evidence_episode_ids: list[str] = field(default_factory=list)
    version: int = 1
    updated_at: str = field(default_factory=utc_now)


@dataclass
class StrategyEvidence(Serializable):
    project_id: str
    source_episode_id: str
    strategy: str
    context: dict[str, Any]
    metric_before: dict[str, float] = field(default_factory=dict)
    metric_after: dict[str, float] = field(default_factory=dict)
    success: bool | None = None
    confidence: float = 0.0
    evidence_level: str = "observational"
    causal_methods: list[str] = field(default_factory=list)
    confounder_checked: bool = False
    evidence_id: str = field(default_factory=lambda: f"strategy_evidence_{uuid4().hex}")
    created_at: str = field(default_factory=utc_now)


@dataclass
class StrategySkillCandidate(Serializable):
    project_id: str
    name: str
    applicability: dict[str, Any]
    procedure: list[str]
    evidence_episode_ids: list[str]
    success_count: int
    failure_count: int
    evidence_level: str
    confidence: float
    status: str = "candidate"
    verifier_passed: bool = False
    human_approved: bool = False
    candidate_id: str = field(default_factory=lambda: f"skill_candidate_{uuid4().hex}")
    created_at: str = field(default_factory=utc_now)


@dataclass
class MemoryQueryPlan(Serializable):
    need_current_profile: bool = False
    need_active_regime: bool = False
    need_similar_decision_episodes: bool = False
    need_strategy_evidence: bool = False
    need_historical_failures: bool = False
    requires_live_data: bool = False
    filters: dict[str, str] = field(default_factory=dict)
    live_data_requirements: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)


@dataclass
class DecisionMemoryContext(Serializable):
    query_plan: MemoryQueryPlan
    profile: dict[str, Any] = field(default_factory=dict)
    active_regime: dict[str, Any] = field(default_factory=dict)
    similar_episodes: list[dict[str, Any]] = field(default_factory=list)
    strategy_evidence: list[dict[str, Any]] = field(default_factory=list)
    historical_failures: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
