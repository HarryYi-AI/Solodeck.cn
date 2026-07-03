from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


MemoryType = Literal[
    "working", "session", "dataset", "schema", "artifact", "graph",
    "text", "failure", "skill", "evaluation",
]


@dataclass
class MemoryItem:
    memory_type: MemoryType
    project_id: str
    session_id: str
    task_id: str
    source_type: str
    source_id: str
    content_summary: str
    structured_payload: dict[str, Any] = field(default_factory=dict)
    lineage: list[dict[str, Any]] = field(default_factory=list)
    privacy_level: str = "internal"
    quality_score: float = 0.5
    warnings: list[str] = field(default_factory=list)
    version: int = 1
    retention_policy: str = "project"
    memory_id: str = field(default_factory=lambda: f"mem_{uuid4().hex}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MemoryItem":
        fields = cls.__dataclass_fields__
        return cls(**{key: value[key] for key in fields if key in value})
