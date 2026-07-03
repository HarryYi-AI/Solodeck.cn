from __future__ import annotations

from typing import Any


def pack_evidence(
    query: str,
    retrieval_plan: str,
    evidence: list[dict[str, Any]],
    missing_info: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    dedup: dict[str, dict[str, Any]] = {}
    for item in evidence:
        sid = item.get("source_id")
        if not sid:
            continue
        if sid not in dedup or float(item.get("score", 0)) > float(dedup[sid].get("score", 0)):
            dedup[sid] = {
                "evidence_id": item.get("evidence_id") or f"ev_{item.get('source_type', 'unknown')}_{sid}",
                "source_type": item.get("source_type"),
                "source_id": sid,
                "content": item.get("content", ""),
                "structured_payload": item.get("structured_payload") or item.get("meta") or {},
                "score": round(float(item.get("score", 0)), 4),
                "used_for": item.get("used_for", "context"),
                "supports_claims": item.get("supports_claims", []),
                "warnings": item.get("warnings", []),
                "privacy_level": item.get("privacy_level", "internal"),
                "artifact_id": item.get("artifact_id"),
                "skill_id": item.get("skill_id"),
                "validator_id": item.get("validator_id"),
                "dataset_version": item.get("dataset_version"),
            }

    ranked = sorted(dedup.values(), key=lambda x: x["score"], reverse=True)
    return {
        "query": query,
        "retrieval_plan": retrieval_plan,
        "evidence": ranked,
        "missing_info": list(missing_info or []),
        "warnings": list(warnings or []),
    }
