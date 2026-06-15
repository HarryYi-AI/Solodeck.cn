from __future__ import annotations

from .memory_store import JsonMemoryStore, compact_payload


def store_trace_memory(trace_id: str, trace: list[dict]) -> dict:
    safe = [{"step": t.get("step"), "role": t.get("role"), "summary": compact_payload(t.get("summary", ""))} for t in trace]
    return JsonMemoryStore("trace_memory").append({"trace_id": trace_id, "trace": safe})

