from __future__ import annotations

from .memory_store import JsonMemoryStore


def store_schema_memory(trace_id: str, schema_summary: dict) -> dict:
    payload = {
        "trace_id": trace_id,
        "columns": schema_summary.get("columns", []),
        "mapped_fields": schema_summary.get("mapped_fields", []),
        "missing_fields": schema_summary.get("missing_fields", []),
        "mapping_confidence": schema_summary.get("mapping_confidence"),
    }
    path = JsonMemoryStore("schema_memory").append(payload)
    return {"path": str(path), "columns": len(payload["columns"]), "mapping_confidence": payload["mapping_confidence"]}

