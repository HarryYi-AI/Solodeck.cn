from __future__ import annotations


class RetrieverAgent:
    name = "RetrieverAgent"

    def summarize_context(self, kg_context: dict, memory_updates: list[dict]) -> dict:
        return {
            "kg_nodes": kg_context.get("summary", {}).get("node_count", 0),
            "kg_edges": kg_context.get("summary", {}).get("edge_count", 0),
            "memory_items": len(memory_updates or []),
        }

