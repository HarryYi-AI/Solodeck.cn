from __future__ import annotations

from enum import Enum
from typing import Iterable


class EvidenceLevel(str, Enum):
    OBSERVATIONAL = "observational"
    ADJUSTED = "adjusted"
    EXPERIMENTAL = "experimental"


LEVEL_RANK = {
    EvidenceLevel.OBSERVATIONAL.value: 0,
    EvidenceLevel.ADJUSTED.value: 1,
    EvidenceLevel.EXPERIMENTAL.value: 2,
}


def strongest_level(levels: Iterable[str]) -> str:
    values = list(levels)
    return max(values, key=lambda item: LEVEL_RANK.get(item, -1), default=EvidenceLevel.OBSERVATIONAL.value)


def can_promote_to_strategy_candidate(
    evidence_count: int,
    *,
    contradiction_count: int = 0,
    minimum_repetitions: int = 3,
) -> bool:
    return evidence_count >= minimum_repetitions and contradiction_count < evidence_count


def can_promote_to_skill(
    evidence_level: str,
    *,
    verifier_passed: bool,
    human_approved: bool,
    evidence_count: int,
) -> bool:
    return (
        LEVEL_RANK.get(evidence_level, -1) >= LEVEL_RANK[EvidenceLevel.ADJUSTED.value]
        and verifier_passed
        and human_approved
        and evidence_count >= 3
    )


def causal_wording_allowed(evidence_level: str, confounder_checked: bool) -> bool:
    return evidence_level == EvidenceLevel.EXPERIMENTAL.value or (
        evidence_level == EvidenceLevel.ADJUSTED.value and confounder_checked
    )
