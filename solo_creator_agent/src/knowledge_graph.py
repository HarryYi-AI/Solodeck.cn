from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

import pandas as pd


ENTITY_COLUMNS = {
    "content_id": "内容",
    "platform": "平台",
    "topic": "主题",
    "title_style": "标题风格",
    "account_id": "账号",
    "series_id": "内容系列",
}


def _node_id(kind: str, value: Any) -> str:
    return f"{kind}:{str(value).strip()}"


class KnowledgeGraphSkill:
    """Build a lightweight creator knowledge graph from structured rows and text."""

    def run(self, df: pd.DataFrame, unstructured_text: str = "") -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[tuple[str, str, str], dict[str, Any]] = {}

        def add_node(node_id: str, label: str, kind: str, **props: Any) -> None:
            if not label or label == "nan":
                return
            item = nodes.setdefault(node_id, {"id": node_id, "label": label, "type": kind, "count": 0})
            item["count"] += 1
            item.update({k: v for k, v in props.items() if v not in [None, ""]})

        def add_edge(source: str, target: str, relation: str, weight: float = 1.0) -> None:
            if source not in nodes or target not in nodes:
                return
            key = (source, target, relation)
            edge = edges.setdefault(key, {"source": source, "target": target, "relation": relation, "weight": 0.0})
            edge["weight"] += float(weight)

        for _, row in df.head(600).iterrows():
            content_id = str(row.get("content_id") or row.name)
            content_node = _node_id("内容", content_id)
            add_node(
                content_node,
                str(row.get("title") or content_id)[:36],
                "内容",
                revenue=float(row.get("revenue", 0) or 0),
                conversions=float(row.get("conversions", 0) or 0),
            )
            for column, kind in ENTITY_COLUMNS.items():
                value = row.get(column)
                if column == "content_id" or pd.isna(value) or str(value).strip() == "":
                    continue
                node = _node_id(kind, value)
                add_node(node, str(value), kind)
                add_edge(content_node, node, f"属于{kind}")
            for feature in _extract_features(row):
                node = _node_id("特征", feature)
                add_node(node, feature, "特征")
                add_edge(content_node, node, "包含特征")

        for keyword, count in _text_keywords(unstructured_text).items():
            node = _node_id("反馈关键词", keyword)
            add_node(node, keyword, "反馈关键词", mentions=count)

        topic_revenue = defaultdict(float)
        for _, row in df.iterrows():
            topic = str(row.get("topic") or "").strip()
            if topic:
                topic_revenue[topic] += float(row.get("revenue", 0) or 0)
        for topic, revenue in topic_revenue.items():
            node = _node_id("主题", topic)
            if node in nodes:
                nodes[node]["revenue"] = round(revenue, 2)

        top_nodes = sorted(nodes.values(), key=lambda x: (x.get("revenue", 0), x["count"]), reverse=True)[:90]
        keep = {n["id"] for n in top_nodes}
        top_edges = [e for e in edges.values() if e["source"] in keep and e["target"] in keep]
        summary = self._summarize(top_nodes, top_edges)
        constraints = self.constraints_from_graph(top_nodes, top_edges)
        return {"nodes": top_nodes, "edges": top_edges[:180], "summary": summary, "constraints": constraints}

    def constraints_from_graph(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
        node_types = {node["id"]: node["type"] for node in nodes}
        required_edges = []
        forbidden_edges = []
        for edge in edges:
            source_type = node_types.get(edge["source"], "")
            target_type = node_types.get(edge["target"], "")
            if source_type in {"平台", "主题", "标题风格", "特征"} and target_type == "内容":
                forbidden_edges.append([edge["source"], edge["target"], "内容不会反向决定已发生策略变量"])
            if source_type == "内容" and target_type in {"平台", "主题", "标题风格"}:
                required_edges.append([edge["target"], "结果指标", "策略变量可影响结果指标"])
        return {"required_edges": required_edges[:12], "forbidden_edges": forbidden_edges[:12]}

    def _summarize(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
        types = Counter(node["type"] for node in nodes)
        top_topics = [n for n in nodes if n["type"] == "主题"][:5]
        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": dict(types),
            "top_topics": [{"label": n["label"], "revenue": n.get("revenue", 0)} for n in top_topics],
            "explanation": "知识图谱用于解释内容、平台、主题和反馈之间的关系；最终经营建议仍以实验结果和增量估计为准。",
        }


def _extract_features(row: pd.Series) -> list[str]:
    features = []
    title = str(row.get("title") or "")
    if re.search(r"\d", title):
        features.append("标题含数字")
    if "?" in title or "？" in title:
        features.append("标题是问题句")
    if len(title) >= 24:
        features.append("标题较长")
    if float(row.get("revenue", 0) or 0) > 0:
        features.append("产生收入")
    return features


def _text_keywords(text: str) -> Counter:
    if not text:
        return Counter()
    tokens = re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}", text)
    stop = {"这个", "一个", "我们", "用户", "内容", "数据", "the", "and", "for"}
    return Counter(t for t in tokens if t.lower() not in stop)


def build_knowledge_graph(
    contents: pd.DataFrame,
    products: pd.DataFrame | None = None,
    feedback: pd.DataFrame | None = None,
    revenues: pd.DataFrame | None = None,
    campaigns: pd.DataFrame | None = None,
    ab_tests: pd.DataFrame | None = None,
    beta_tests: pd.DataFrame | None = None,
    lang: str = "中文",
) -> dict[str, Any]:
    """Backward-compatible graph builder used by the original agent suite."""
    frames = [contents if contents is not None else pd.DataFrame()]
    text_parts: list[str] = []
    if feedback is not None and not feedback.empty:
        text_cols = [c for c in ["feedback_text", "content", "comment", "issue", "note"] if c in feedback.columns]
        if text_cols:
            text_parts.extend(feedback[text_cols].astype(str).agg(" ".join, axis=1).head(80).tolist())
    graph = KnowledgeGraphSkill().run(pd.concat(frames, ignore_index=True, sort=False), "\n".join(text_parts))
    if products is not None and not products.empty:
        for _, row in products.head(80).iterrows():
            product_id = f"产品:{row.get('product_id', row.name)}"
            graph["nodes"].append({
                "id": product_id,
                "label": str(row.get("product_name") or row.get("name") or row.get("feature_tags") or product_id)[:36],
                "type": "产品",
                "count": 1,
                "revenue": float(row.get("revenue", 0) or 0) if "revenue" in row else 0,
            })
    return graph


def feature_combination_query(products: pd.DataFrame, lang: str = "中文") -> dict[str, Any]:
    if products is None or products.empty:
        return {"summary": "暂无产品功能数据", "items": []}
    column = "feature_tags" if "feature_tags" in products.columns else products.columns[0]
    items = products[column].fillna("").astype(str).value_counts().head(5)
    return {"summary": "高频功能组合", "items": [{"feature": k, "count": int(v)} for k, v in items.items()]}


def series_exploration_query(contents: pd.DataFrame, lang: str = "中文") -> dict[str, Any]:
    if contents is None or contents.empty or "series_id" not in contents.columns:
        return {"summary": "暂无系列数据", "items": []}
    table = contents.groupby("series_id").agg(count=("series_id", "size"), revenue=("revenue", "sum") if "revenue" in contents.columns else ("series_id", "size")).reset_index()
    table = table.sort_values(["revenue", "count"], ascending=False).head(5)
    return {"summary": "重点内容系列", "items": table.to_dict("records")}


def platform_topic_query(contents: pd.DataFrame, revenues: pd.DataFrame | None = None, lang: str = "中文") -> dict[str, Any]:
    if contents is None or contents.empty:
        return {"summary": "暂无平台主题数据", "items": []}
    group_cols = [c for c in ["platform", "topic"] if c in contents.columns]
    if not group_cols:
        return {"summary": "暂无平台主题数据", "items": []}
    value_col = "revenue" if "revenue" in contents.columns else "views"
    table = contents.groupby(group_cols).agg(value=(value_col, "sum"), count=(group_cols[0], "size")).reset_index().sort_values("value", ascending=False).head(8)
    return {"summary": "平台与主题组合", "items": table.to_dict("records")}


def global_graph_query(contents: pd.DataFrame, products: pd.DataFrame | None = None, feedback: pd.DataFrame | None = None, revenues: pd.DataFrame | None = None, lang: str = "中文") -> dict[str, Any]:
    return {
        "summary": "全局图谱上下文",
        "content_rows": int(len(contents)) if contents is not None else 0,
        "product_rows": int(len(products)) if products is not None else 0,
        "feedback_rows": int(len(feedback)) if feedback is not None else 0,
        "revenue_rows": int(len(revenues)) if revenues is not None else 0,
    }


def graph_insight_cards(products: pd.DataFrame, contents: pd.DataFrame, feedback: pd.DataFrame, lang: str = "中文") -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    if contents is not None and not contents.empty and "topic" in contents.columns:
        value_col = "revenue" if "revenue" in contents.columns else "views"
        top = contents.groupby("topic")[value_col].sum().sort_values(ascending=False).head(1)
        if not top.empty:
            cards.append({
                "title": f"重点主题：{top.index[0]}",
                "reason": f"该主题累计{value_col}最高。",
                "action": "优先围绕该主题做小范围验证，再决定是否放大。",
                "priority": "high",
            })
    if feedback is not None and not feedback.empty:
        cards.append({
            "title": "反馈已进入图谱",
            "reason": f"已读取 {len(feedback)} 条反馈，可用于解释用户需求。",
            "action": "把高频问题转成下一轮内容或产品验证项。",
            "priority": "medium",
        })
    return cards


def strategy_constraint_checks(cards: list[dict[str, Any]], contents: pd.DataFrame, ab_tests: pd.DataFrame, beta_tests: pd.DataFrame, lang: str = "中文") -> list[dict[str, Any]]:
    checked = []
    has_experiment = (ab_tests is not None and not ab_tests.empty) or (beta_tests is not None and not beta_tests.empty)
    for card in cards:
        next_card = dict(card)
        if not has_experiment and next_card.get("priority") == "high":
            next_card["confidence"] = "缺少实验结果，建议先小范围验证。"
        checked.append(next_card)
    return checked
