from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = ROOT / "data" / "memory"
V3_MEMORY_DIR = ROOT / "data" / "solodeck_v3_memory"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _read_jsonl(path: Path, limit: int = 500) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


class MemoryStore:
    """Read-only access to SoloDeck data-agent memory files."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or MEMORY_DIR
        self.use_seed_files = root is not None or os.getenv("SOLODECK_USE_DEMO_MEMORY", "").lower() in {"1", "true", "yes"}
        self.root.mkdir(parents=True, exist_ok=True)

    def schema_summary(self) -> dict[str, Any]:
        data = _read_json(self.root / "schema_summary.json", {}) if self.use_seed_files else {}
        if data:
            return data
        return _bootstrap_schema_from_v3()

    def kg_edges(self) -> list[dict[str, Any]]:
        edges = _read_json(self.root / "kg_edges.json", []) if self.use_seed_files else []
        if edges:
            return edges if isinstance(edges, list) else edges.get("edges", [])
        return _bootstrap_kg_from_v3()

    def artifacts(self) -> list[dict[str, Any]]:
        data = _read_json(self.root / "artifacts.json", []) if self.use_seed_files else []
        return data if isinstance(data, list) else data.get("artifacts", [])

    def session_history(self) -> list[dict[str, Any]]:
        data = _read_json(self.root / "session_history.json", []) if self.use_seed_files else []
        return data if isinstance(data, list) else data.get("sessions", [])

    def text_chunks(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.root / "text_chunks.jsonl") if self.use_seed_files else []


def _bootstrap_schema_from_v3() -> dict[str, Any]:
    path = V3_MEMORY_DIR / "schema_memory.jsonl"
    rows = _read_jsonl(path, limit=5)
    if not rows:
        return {"columns": [], "mapped_fields": [], "missing_fields": [], "mapping_confidence": 0.0}
    latest = rows[-1]
    return {
        "columns": latest.get("columns") or latest.get("mapped_fields") or [],
        "mapped_fields": latest.get("mapped_fields") or [],
        "missing_fields": latest.get("missing_fields") or [],
        "mapping_confidence": latest.get("mapping_confidence", 0.0),
        "trace_id": latest.get("trace_id"),
        "source": "solodeck_v3_memory.schema_memory",
    }


def _bootstrap_kg_from_v3() -> list[dict[str, Any]]:
    path = V3_MEMORY_DIR / "graph_memory.jsonl"
    rows = _read_jsonl(path, limit=3)
    if not rows:
        return []
    latest = rows[-1]
    nodes = {n.get("id"): n for n in latest.get("nodes") or [] if n.get("id")}
    edges: list[dict[str, Any]] = []
    for edge in latest.get("edges") or []:
        src = edge.get("source") or edge.get("from")
        tgt = edge.get("target") or edge.get("to")
        rel = edge.get("relation") or edge.get("type") or "related_to"
        edges.append(
            {
                "source_id": src,
                "target_id": tgt,
                "relation": rel,
                "source_label": (nodes.get(src) or {}).get("label", src),
                "target_label": (nodes.get(tgt) or {}).get("label", tgt),
                "trace_id": latest.get("trace_id"),
            }
        )
    return edges
