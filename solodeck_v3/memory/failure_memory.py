from __future__ import annotations

from .memory_store import JsonMemoryStore


def store_failure_memory(trace_id: str, failure_report: dict) -> dict:
    return JsonMemoryStore("failure_memory").append({"trace_id": trace_id, "failure": failure_report})

