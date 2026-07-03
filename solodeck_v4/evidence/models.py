from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from uuid import uuid4


EvidenceSource = Literal["schema", "kg", "artifact", "session", "text", "python", "sql", "validator"]


@dataclass
class EvidenceObject:
    source_type: EvidenceSource
    source_id: str
    content: str
    used_for: str
    structured_payload: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    supports_claims: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    privacy_level: str = "internal"
    artifact_id: str | None = None
    skill_id: str | None = None
    validator_id: str | None = None
    dataset_version: str | None = None
    evidence_id: str = field(default_factory=lambda: f"ev_{uuid4().hex}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidencePack:
    query: str
    intent: str
    evidence: list[EvidenceObject]
    missing_info: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query, "retrieval_plan": self.intent,
            "evidence": [item.to_dict() for item in self.evidence],
            "missing_info": self.missing_info, "warnings": self.warnings,
        }
