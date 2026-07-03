from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from solodeck_v4.memory import MemoryItem, UnifiedMemory


ALLOWED_TARGETS = {
    "retrieval_routing", "evidence_packing", "causal_readiness",
    "estimator_selection", "uncertainty_reporting", "report_gating", "action_safety",
}


@dataclass
class SkillPatch:
    target: str
    description: str
    changes: dict[str, Any]
    source_failures: list[str]
    patch_id: str = field(default_factory=lambda: f"patch_{uuid4().hex[:16]}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "proposed"
    baseline_score: float | None = None
    candidate_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SkillOptLite:
    """Validation-gated external skill evolution; never updates model weights."""

    def __init__(self, memory: UnifiedMemory | None = None) -> None:
        self.memory = memory or UnifiedMemory()

    def propose(self, failures: list[dict[str, Any]]) -> list[SkillPatch]:
        grouped: dict[str, list[str]] = {}
        mapping = {
            "retrieval_error": "retrieval_routing", "missing_source": "evidence_packing",
            "estimator_misuse": "estimator_selection", "causal_overclaim": "report_gating",
            "uncertainty_ignored": "uncertainty_reporting", "unsafe_action": "action_safety",
        }
        for failure in failures:
            kind = failure.get("failure_type", "")
            target = mapping.get(kind)
            if target:
                grouped.setdefault(target, []).append(failure.get("failure_id") or kind)
        return [
            SkillPatch(target=target, description=f"针对 {len(ids)} 个失败样本收紧 {target} 规则", changes={"strict_mode": True, "failure_count": len(ids)}, source_failures=ids)
            for target, ids in grouped.items()
        ]

    def validate_patch(
        self,
        patch: SkillPatch,
        held_out_tasks: list[dict[str, Any]],
        scorer: Callable[[list[dict[str, Any]], SkillPatch | None], float],
        *, project_id: str = "solodeck",
    ) -> dict[str, Any]:
        if patch.target not in ALLOWED_TARGETS:
            raise ValueError(f"unsupported patch target: {patch.target}")
        baseline = float(scorer(held_out_tasks, None))
        candidate = float(scorer(held_out_tasks, patch))
        patch.baseline_score, patch.candidate_score = baseline, candidate
        patch.status = "accepted" if candidate > baseline else "rejected"
        self.memory.write_memory(MemoryItem(
            memory_type="skill", project_id=project_id, session_id="skillopt",
            task_id=patch.patch_id, source_type="skill_patch", source_id=patch.target,
            content_summary=f"{patch.status}: {patch.description}",
            structured_payload=patch.to_dict(), quality_score=max(0.0, min(1.0, candidate)),
            warnings=[] if patch.status == "accepted" else ["候选修改未提升留出集得分，已拒绝"],
            retention_policy="permanent",
        ))
        return patch.to_dict()
