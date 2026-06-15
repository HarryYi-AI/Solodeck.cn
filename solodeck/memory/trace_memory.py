from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = ROOT / "data" / "solodeck_memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def store_raw_trace(session_id: str, trace: list[dict[str, Any]]) -> str:
    path = MEMORY_DIR / f"{session_id}.raw.json"
    path.write_text(json.dumps({"time": _now(), "trace": trace}, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def compress_trace_summary(trace: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "step_count": len(trace),
        "steps": [item.get("step", "unknown") for item in trace],
        "warnings": [item.get("warning") for item in trace if item.get("warning")],
    }


def store_entity_level_memory(session_id: str, entities: list[dict[str, Any]]) -> str:
    path = MEMORY_DIR / f"{session_id}.entities.json"
    safe = [{"id": e.get("id"), "label": e.get("label"), "type": e.get("type"), "count": e.get("count")} for e in entities[:120]]
    path.write_text(json.dumps({"time": _now(), "entities": safe}, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def retrieve_trace(session_id: str) -> dict[str, Any]:
    path = MEMORY_DIR / f"{session_id}.raw.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def reconstruct_context(session_id: str) -> dict[str, Any]:
    raw = retrieve_trace(session_id)
    return {"session_id": session_id, "summary": compress_trace_summary(raw.get("trace", [])), "raw_available": bool(raw)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

