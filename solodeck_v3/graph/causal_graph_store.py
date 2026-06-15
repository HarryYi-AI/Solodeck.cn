from __future__ import annotations

from solodeck_v3.memory.memory_store import JsonMemoryStore


def store_causal_graph(trace_id: str, causal_context: dict) -> dict:
    safe = {
        "trace_id": trace_id,
        "method": causal_context.get("method"),
        "stability_score": causal_context.get("stability_score"),
        "edges": causal_context.get("exploratory_causal_graph", {}).get("edges", [])[:80],
        "warnings": causal_context.get("warnings", []),
    }
    return JsonMemoryStore("causal_graph_memory").append(safe)

