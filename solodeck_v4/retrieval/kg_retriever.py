from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

from solodeck_v4.retrieval.memory_store import MemoryStore

RELATION_TYPES = {
    "contains", "belongs_to", "derived_from", "may_affect", "may_confound",
    "forbidden_direction", "measured_by", "generated_by", "validated_by",
    "failed_because", "supports", "contradicts", "related_to",
}


def retrieve_kg(
    query: str,
    task_spec: dict[str, Any],
    entity_link: dict[str, Any] | None = None,
    store: MemoryStore | None = None,
    max_hops: int = 2,
) -> list[dict[str, Any]]:
    store = store or MemoryStore()
    edges = store.kg_edges()
    if not edges:
        return []

    seeds = _seed_entities(query, task_spec, entity_link or {})
    if not seeds:
        seeds = _infer_seeds_from_query(query, edges)

    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        src = edge.get("source_id") or edge.get("source")
        tgt = edge.get("target_id") or edge.get("target")
        if src:
            adjacency[src].append({**edge, "neighbor": tgt, "direction": "out"})
        if tgt:
            adjacency[tgt].append({**edge, "neighbor": src, "direction": "in"})

    visited: set[str] = set()
    frontier = [(seed, 0) for seed in seeds]
    hits: list[dict[str, Any]] = []

    while frontier:
        node, hop = frontier.pop(0)
        if node in visited or hop > max_hops:
            continue
        visited.add(node)

        for edge in adjacency.get(node, []):
            rel = edge.get("relation") or edge.get("type") or "related_to"
            neighbor = edge.get("neighbor")
            score = _edge_score(edge, query, task_spec, hop)
            hits.append(
                {
                    "source_type": "kg",
                    "source_id": f"kg:{edge.get('source_id', node)}->{edge.get('target_id', neighbor)}:{rel}",
                    "content": _format_edge(edge, rel),
                    "score": score,
                    "used_for": "causal_check" if rel in {"may_confound", "may_affect"} else "context",
                    "meta": {"hop": hop, "relation": rel, "seed": node},
                }
            )
            if neighbor and neighbor not in visited and hop + 1 <= max_hops:
                frontier.append((neighbor, hop + 1))

    dedup: dict[str, dict[str, Any]] = {}
    for hit in hits:
        sid = hit["source_id"]
        if sid not in dedup or hit["score"] > dedup[sid]["score"]:
            dedup[sid] = hit
    return sorted(dedup.values(), key=lambda x: x["score"], reverse=True)[:15]


def _seed_entities(query: str, task_spec: dict[str, Any], entity_link: dict[str, Any]) -> list[str]:
    seeds: list[str] = []
    for item in entity_link.get("linked_entities") or []:
        col = item.get("column")
        canonical = item.get("canonical") or col
        if col:
            seeds.append(f"Column:{col}")
        if canonical:
            seeds.append(str(canonical))
    for col in (task_spec.get("candidate_treatments") or []) + (task_spec.get("candidate_outcomes") or []):
        seeds.append(f"Column:{col}")
    return list(dict.fromkeys(seeds))


def _infer_seeds_from_query(query: str, edges: list[dict[str, Any]]) -> list[str]:
    q = query or ""
    seeds: list[str] = []
    labels = set()
    for edge in edges:
        for key in ("source_label", "target_label", "source_id", "target_id"):
            val = edge.get(key)
            if val:
                labels.add(str(val))
    for label in labels:
        token = label.split(":")[-1] if ":" in label else label
        if len(token) >= 2 and token.lower() in q.lower():
            seeds.append(label if label.startswith("Column:") else f"Column:{token}")
    return seeds[:5]


def _edge_score(edge: dict[str, Any], query: str, task_spec: dict[str, Any], hop: int) -> float:
    rel = edge.get("relation") or edge.get("type") or "related_to"
    score = max(0.2, 1.0 - 0.25 * hop)
    if rel in {"may_confound", "may_affect"}:
        score += 0.25
    if task_spec.get("task_type") in {"causal_effect_estimation", "counterfactual_analysis"}:
        score += 0.15
    text = _format_edge(edge, rel).lower()
    for token in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z_]+", query or ""):
        if len(token) >= 2 and token.lower() in text:
            score += 0.1
    return min(score, 1.0)


def _format_edge(edge: dict[str, Any], rel: str) -> str:
    src = edge.get("source_label") or edge.get("source_id") or "?"
    tgt = edge.get("target_label") or edge.get("target_id") or "?"
    return f"{src} --[{rel}]--> {tgt}"
