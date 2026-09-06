from __future__ import annotations

import json
import sqlite3
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import MemoryItem


class MemoryBackend(ABC):
    @abstractmethod
    def write(self, item: MemoryItem) -> MemoryItem: ...

    @abstractmethod
    def get(self, memory_id: str) -> MemoryItem | None: ...

    @abstractmethod
    def query(self, filters: dict[str, Any], limit: int = 50) -> list[MemoryItem]: ...

    @abstractmethod
    def update(self, memory_id: str, changes: dict[str, Any]) -> MemoryItem | None: ...

    @abstractmethod
    def delete(self, memory_id: str) -> bool: ...


class SQLiteMemoryBackend(MemoryBackend):
    """Portable first backend; the MemoryBackend contract is storage-agnostic."""

    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.path = Path(path or root / "data" / "solodeck_runtime.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY, memory_type TEXT NOT NULL,
                project_id TEXT NOT NULL, session_id TEXT, task_id TEXT,
                source_type TEXT, source_id TEXT, created_at TEXT, updated_at TEXT,
                content_summary TEXT, structured_payload TEXT, lineage TEXT,
                privacy_level TEXT, quality_score REAL, warnings TEXT,
                version INTEGER, retention_policy TEXT)"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_scope ON memories(project_id, session_id, memory_type)")

    def write(self, item: MemoryItem) -> MemoryItem:
        data = item.to_dict()
        encoded = self._encode(data)
        columns = ",".join(encoded)
        marks = ",".join("?" for _ in encoded)
        with self._connect() as conn:
            conn.execute(f"INSERT OR REPLACE INTO memories ({columns}) VALUES ({marks})", tuple(encoded.values()))
        return item

    def get(self, memory_id: str) -> MemoryItem | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE memory_id = ?", (memory_id,)).fetchone()
        return self._decode(row) if row else None

    def query(self, filters: dict[str, Any], limit: int = 50) -> list[MemoryItem]:
        allowed = {"memory_type", "project_id", "session_id", "task_id", "source_type", "source_id", "privacy_level"}
        clauses, values = [], []
        for key, value in filters.items():
            if key in allowed and value is not None:
                clauses.append(f"{key} = ?")
                values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM memories{where} ORDER BY updated_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(sql, (*values, max(1, min(limit, 500)))).fetchall()
        return [self._decode(row) for row in rows]

    def update(self, memory_id: str, changes: dict[str, Any]) -> MemoryItem | None:
        current = self.get(memory_id)
        if current is None:
            return None
        immutable = {"memory_id", "created_at"}
        for key, value in changes.items():
            if key in current.__dataclass_fields__ and key not in immutable:
                setattr(current, key, value)
        current.updated_at = datetime.now(timezone.utc).isoformat()
        current.version += 1
        return self.write(current)

    def delete(self, memory_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _encode(data: dict[str, Any]) -> dict[str, Any]:
        encoded = dict(data)
        for key in ("structured_payload", "lineage", "warnings"):
            encoded[key] = json.dumps(encoded[key], ensure_ascii=False, default=str)
        return encoded

    @staticmethod
    def _decode(row: sqlite3.Row) -> MemoryItem:
        data = dict(row)
        for key in ("structured_payload", "lineage", "warnings"):
            try:
                data[key] = json.loads(data[key] or ("{}" if key == "structured_payload" else "[]"))
            except json.JSONDecodeError:
                data[key] = {} if key == "structured_payload" else []
        return MemoryItem.from_dict(data)


class UnifiedMemory:
    def __init__(self, backend: MemoryBackend | None = None) -> None:
        self.backend = backend or SQLiteMemoryBackend()

    def write_memory(self, item: MemoryItem | dict[str, Any]) -> MemoryItem:
        return self.backend.write(item if isinstance(item, MemoryItem) else MemoryItem.from_dict(item))

    def read_memory(self, memory_id: str) -> MemoryItem | None:
        return self.backend.get(memory_id)

    def retrieve_memory(self, *, query: str = "", limit: int = 20, **filters: Any) -> list[MemoryItem]:
        candidates = self.backend.query(filters, limit=max(limit * 5, 50))
        if not query.strip():
            return candidates[:limit]
        terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", query.lower()))
        now = datetime.now(timezone.utc)
        scored = []
        for item in candidates:
            haystack = f"{item.content_summary} {json.dumps(item.structured_payload, ensure_ascii=False)}".lower()
            document_terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", haystack))
            relevance = len(terms & document_terms) / max(1, len(terms))
            try:
                updated = datetime.fromisoformat(item.updated_at.replace("Z", "+00:00"))
                age_days = max(0.0, (now - updated).total_seconds() / 86400)
            except (ValueError, TypeError):
                age_days = 365.0
            recency = math.exp(-age_days / 30)
            importance = max(0.0, min(float(item.quality_score), 1.0))
            # Explicit engineering heuristic: relevance dominates, while recent,
            # high-quality episodes break ties. These weights are not learned.
            score = 0.65 * relevance + 0.20 * recency + 0.15 * importance
            scored.append((score, item.updated_at, item))
        return [item for _, _, item in sorted(scored, reverse=True)[:limit]]

    def update_memory(self, memory_id: str, changes: dict[str, Any]) -> MemoryItem | None:
        return self.backend.update(memory_id, changes)

    def delete_memory(self, memory_id: str) -> bool:
        return self.backend.delete(memory_id)

    def compact_memory(self, project_id: str, session_id: str, keep: int = 30) -> dict[str, Any]:
        items = self.backend.query({"project_id": project_id, "session_id": session_id}, limit=500)
        if len(items) <= keep:
            return {"compacted": 0, "kept": len(items)}
        old = items[keep:]
        summary = self.summarize_memory(old)
        compacted = MemoryItem(
            memory_type="session", project_id=project_id, session_id=session_id,
            task_id="compaction", source_type="memory_compaction", source_id=session_id,
            content_summary=summary["summary"], structured_payload=summary,
            lineage=[{"memory_id": item.memory_id, "version": item.version} for item in old],
            quality_score=0.7, retention_policy="session",
        )
        self.write_memory(compacted)
        for item in old:
            self.delete_memory(item.memory_id)
        return {"compacted": len(old), "kept": keep + 1, "summary_memory_id": compacted.memory_id}

    def summarize_memory(self, items: list[MemoryItem]) -> dict[str, Any]:
        types = Counter(item.memory_type for item in items)
        warnings = list(dict.fromkeys(w for item in items for w in item.warnings))[:10]
        snippets = [item.content_summary[:160] for item in items[:12] if item.content_summary]
        return {
            "summary": "；".join(snippets)[:1200],
            "item_count": len(items), "memory_types": dict(types), "warnings": warnings,
        }

    def export_memory_trace(self, project_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
        filters = {"project_id": project_id, "session_id": session_id}
        return [item.to_dict() for item in self.backend.query(filters, limit=500)]
