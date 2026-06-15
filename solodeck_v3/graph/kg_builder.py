from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd


NODE_COLUMNS = {
    "platform": "Entity",
    "topic": "Entity",
    "title_style": "Treatment",
    "revenue": "Outcome",
    "conversions": "Outcome",
    "consultations": "Outcome",
    "views": "Metric",
    "favorites": "Metric",
    "production_hours": "Confounder",
    "account_id": "Confounder",
}


def build_kg_context(df: pd.DataFrame, text: str = "", trace_id: str = "") -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def node(node_id: str, label: str, kind: str, **props: Any) -> None:
        item = nodes.setdefault(node_id, {"id": node_id, "label": label, "type": kind, "properties": {}, "count": 0})
        item["count"] += 1
        item["properties"].update({k: v for k, v in props.items() if v not in [None, ""]})

    def edge(source: str, target: str, rel: str, **props: Any) -> None:
        if source in nodes and target in nodes:
            edges.append({"source": source, "target": target, "type": rel, "properties": props})

    dataset_id = f"Dataset:{trace_id or 'current'}"
    node(dataset_id, "当前数据集", "Dataset", rows=int(len(df)), columns=len(df.columns))
    table_id = f"Table:contents"
    node(table_id, "内容经营表", "Table")
    edge(dataset_id, table_id, "contains")
    for column in df.columns:
        kind = NODE_COLUMNS.get(column, "Column")
        col_id = f"Column:{column}"
        node(col_id, column, kind, dtype=str(df[column].dtype))
        edge(table_id, col_id, "contains")
        if kind in {"Treatment", "Outcome", "Metric", "Confounder"}:
            edge(col_id, f"Skill:{kind}", "requires")
            node(f"Skill:{kind}", kind, "Skill")
    for treatment in [c for c, kind in NODE_COLUMNS.items() if kind == "Treatment" and c in df.columns]:
        for outcome in [c for c, kind in NODE_COLUMNS.items() if kind == "Outcome" and c in df.columns]:
            edge(f"Column:{treatment}", f"Column:{outcome}", "may_affect")
    for confounder in [c for c, kind in NODE_COLUMNS.items() if kind == "Confounder" and c in df.columns]:
        for outcome in [c for c, kind in NODE_COLUMNS.items() if kind == "Outcome" and c in df.columns]:
            edge(f"Column:{confounder}", f"Column:{outcome}", "may_confound")
    for keyword, count in _entities_from_text(text).items():
        ent_id = f"Entity:{keyword}"
        node(ent_id, keyword, "Entity", mentions=count)
        edge(dataset_id, ent_id, "contains")
    return {
        "nodes": list(nodes.values()),
        "edges": edges[:260],
        "summary": {"node_count": len(nodes), "edge_count": len(edges), "explanation": "KG 用于上下文检索、候选混杂选择、禁止方向约束和产物溯源，不作为因果真相。"},
    }


def _entities_from_text(text: str) -> Counter:
    tokens = re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}", text or "")
    stop = {"用户", "内容", "数据", "我们", "这个", "一个", "the", "and"}
    return Counter(t for t in tokens if t.lower() not in stop)

