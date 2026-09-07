from __future__ import annotations

from .retriever import retrieve_decision_episodes, retrieve_strategy_evidence
from .schemas import DecisionMemoryContext, MemoryQueryPlan
from .store import SQLiteDecisionMemoryStore
from .temporal_resolver import matching_active_regime


def build_decision_memory_context(
    query: str,
    project_id: str,
    plan: MemoryQueryPlan,
    store: SQLiteDecisionMemoryStore,
) -> DecisionMemoryContext:
    profile = store.get_profile(project_id) if plan.need_current_profile else None
    regime = matching_active_regime(store, project_id, plan.filters) if plan.need_active_regime else None
    episodes = retrieve_decision_episodes(query, project_id, plan, store) if plan.need_similar_decision_episodes else []
    evidence = retrieve_strategy_evidence(project_id, plan, store) if plan.need_strategy_evidence else []
    failures = [item for item in episodes if (item.get("outcome") or {}).get("success") is False] if plan.need_historical_failures else []
    warnings = []
    if plan.requires_live_data:
        warnings.append("历史记忆不能回答当前数值；必须由实时数据层查询。")
    if plan.need_similar_decision_episodes and not episodes:
        warnings.append("没有找到足够相似的历史决策。")
    return DecisionMemoryContext(
        query_plan=plan,
        profile=profile.to_dict() if profile else {},
        active_regime=regime.to_dict() if regime else {},
        similar_episodes=episodes,
        strategy_evidence=evidence,
        historical_failures=failures,
        warnings=warnings,
    )
