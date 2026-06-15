from __future__ import annotations

from .memory_store import JsonMemoryStore


def store_graph_memory(trace_id: str, kg_context: dict) -> dict:
    nodes = kg_context.get("nodes", [])
    edges = kg_context.get("edges", [])
    safe_nodes = [{"id": n.get("id"), "label": n.get("label"), "type": n.get("type")} for n in nodes[:120]]
    safe_edges = [{"source": e.get("source"), "target": e.get("target"), "type": e.get("type") or e.get("relation")} for e in edges[:220]]
    return JsonMemoryStore("graph_memory").append({"trace_id": trace_id, "nodes": safe_nodes, "edges": safe_edges})

