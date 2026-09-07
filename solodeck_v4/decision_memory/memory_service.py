from __future__ import annotations

from typing import Any

from .consolidator import consolidate_decision_episodes
from .context_builder import build_decision_memory_context
from .extractor import extract_atomic_facts, extract_decision_episode
from .query_planner import plan_memory_query
from .schemas import BusinessRegime, DecisionEpisode, DecisionOutcome, StrategyEvidence, utc_now
from .store import SQLiteDecisionMemoryStore
from .temporal_resolver import activate_regime


class DecisionMemoryService:
    """Narrow integration boundary used by Router/Planner and the runtime finalizer."""

    def __init__(self, store: SQLiteDecisionMemoryStore | None = None) -> None:
        self.store = store or SQLiteDecisionMemoryStore()

    def record_decision(
        self,
        analysis: dict[str, Any] | DecisionEpisode,
        *,
        user_id: str = "anonymous",
        project_id: str = "solodeck",
        data_source_ids: list[str] | None = None,
        outcome: DecisionOutcome | None = None,
    ) -> dict[str, Any]:
        episode = analysis if isinstance(analysis, DecisionEpisode) else extract_decision_episode(
            analysis,
            user_id=user_id,
            project_id=project_id,
            data_source_ids=data_source_ids,
            outcome=outcome,
        )
        if episode is None:
            return {"recorded": False, "reason": "没有形成可执行决策，不写入长期决策记忆。"}
        self.store.save_episode(episode)
        facts = self.store.save_facts(extract_atomic_facts(episode))
        strategy_evidence = None
        if episode.outcome.observed:
            strategy_evidence = self._save_episode_strategy_evidence(episode)
        return {
            "recorded": True,
            "episode_id": episode.episode_id,
            "fact_count": len(facts),
            "strategy_evidence_id": strategy_evidence.evidence_id if strategy_evidence else None,
        }

    def record_outcome(
        self,
        episode_id: str,
        *,
        metrics: dict[str, float],
        success: bool | None,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        episode = self.store.get_episode(episode_id)
        if episode is None:
            return {"recorded": False, "reason": "decision episode not found"}
        outcome = DecisionOutcome(observed=True, metrics=metrics, success=success, observed_at=observed_at or utc_now())
        episode = self.store.update_outcome(episode_id, outcome)
        evidence = self._save_episode_strategy_evidence(episode)
        return {"recorded": True, "episode_id": episode_id, "strategy_evidence_id": evidence.evidence_id}

    def get_decision_context(
        self,
        query: str,
        *,
        project_id: str,
        task_spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = plan_memory_query(query, task_spec)
        return build_decision_memory_context(query, project_id, plan, self.store).to_dict()

    def run_consolidation(self, project_id: str, window_days: int = 365, *, persist: bool = True) -> dict[str, Any]:
        return consolidate_decision_episodes(project_id, window_days, self.store, persist=persist)

    def activate_business_regime(self, regime: BusinessRegime) -> dict[str, Any]:
        return activate_regime(self.store, regime)

    def _save_episode_strategy_evidence(self, episode: DecisionEpisode) -> StrategyEvidence:
        context = episode.decision_context.to_dict()
        evidence = StrategyEvidence(
            evidence_id=f"strategy_evidence_{episode.episode_id}",
            project_id=episode.project_id,
            source_episode_id=episode.episode_id,
            strategy=episode.decision.strategy,
            context=context,
            metric_before=episode.evidence.metrics,
            metric_after=episode.outcome.metrics,
            success=episode.outcome.success,
            confidence=episode.decision.confidence,
            evidence_level=episode.evidence.evidence_level,
            causal_methods=episode.evidence.causal_methods,
            confounder_checked=episode.evidence.confounder_checked,
        )
        return self.store.save_strategy_evidence(evidence)
