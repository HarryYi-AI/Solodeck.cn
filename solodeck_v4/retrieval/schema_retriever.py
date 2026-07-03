from __future__ import annotations

import re
from typing import Any

from solodeck_v4.retrieval.memory_store import MemoryStore


def retrieve_schema(
    query: str,
    task_spec: dict[str, Any],
    store: MemoryStore | None = None,
) -> list[dict[str, Any]]:
    store = store or MemoryStore()
    summary = store.schema_summary()
    hits: list[dict[str, Any]] = []

    columns = summary.get("columns") or summary.get("mapped_fields") or []
    mapped = summary.get("mapped_fields") or columns
    missing = summary.get("missing_fields") or []
    q = (query or "").lower()

    for col in mapped:
        score = _column_score(col, q, task_spec)
        if score <= 0 and not _mentions_column(col, q):
            continue
        hits.append(
            {
                "source_type": "schema",
                "source_id": f"schema:{col}",
                "content": f"字段 {col} 已映射到标准 schema",
                "score": score,
                "used_for": "context",
                "meta": {"column": col},
            }
        )

    if missing:
        hits.append(
            {
                "source_type": "schema",
                "source_id": "schema:missing_fields",
                "content": f"缺失字段: {', '.join(missing)}",
                "score": 0.55 if any(m.lower() in q for m in missing) else 0.35,
                "used_for": "context",
                "meta": {"missing_fields": missing},
            }
        )

    hits.append(
        {
            "source_type": "schema",
            "source_id": "schema:summary",
            "content": (
                f"共 {len(columns)} 列，映射置信度 {summary.get('mapping_confidence', 0):.2f}。"
                f" 关键列: {', '.join(mapped[:8])}"
            ),
            "score": 0.5,
            "used_for": "context",
            "meta": {"mapping_confidence": summary.get("mapping_confidence")},
        }
    )
    return sorted(hits, key=lambda x: x["score"], reverse=True)[:12]


def _column_score(col: str, query: str, task_spec: dict[str, Any]) -> float:
    score = 0.0
    if _mentions_column(col, query):
        score += 0.8
    for key in ("candidate_treatments", "candidate_outcomes"):
        if col in (task_spec.get(key) or []):
            score += 0.6
    return score


def _mentions_column(col: str, query: str) -> bool:
    aliases = {
        "consultations": ("咨询", "私信", "线索"),
        "conversions": ("成交", "转化"),
        "revenue": ("收入", "营收"),
        "platform": ("平台", "小红书", "抖音", "b站"),
        "title_style": ("标题", "痛点", "教程"),
        "topic": ("主题", "选题"),
        "views": ("播放", "阅读", "曝光"),
    }
    if col.lower() in query:
        return True
    for alias in aliases.get(col, ()):
        if alias in query:
            return True
    return False
