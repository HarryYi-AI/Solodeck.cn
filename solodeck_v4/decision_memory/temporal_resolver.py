from __future__ import annotations

from .schemas import BusinessRegime
from .store import SQLiteDecisionMemoryStore


def activate_regime(store: SQLiteDecisionMemoryStore, regime: BusinessRegime) -> dict:
    """Historize conflicting active regimes in the same scope before activation."""
    closed = store.close_active_regimes(regime.project_id, regime.scope, regime.valid_from)
    regime.status = "active"
    store.save_regime(regime)
    return {"active_regime": regime.to_dict(), "historized_regime_ids": closed}


def matching_active_regime(
    store: SQLiteDecisionMemoryStore,
    project_id: str,
    filters: dict[str, str],
) -> BusinessRegime | None:
    regimes = store.list_regimes(project_id, status="active")
    ranked = []
    for regime in regimes:
        relevant = [key for key in ("platform", "topic", "content_format") if filters.get(key)]
        score = sum(regime.scope.get(key) == filters[key] for key in relevant)
        if not relevant or score:
            ranked.append((score, regime.valid_from, regime))
    return max(ranked, key=lambda row: (row[0], row[1]))[2] if ranked else None
