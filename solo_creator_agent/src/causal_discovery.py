from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


class CausalDiscoverySkill:
    """Generate a candidate DAG using optional causal discovery libraries and deterministic fallbacks."""

    PREFERRED_ORDER = [
        "account_id",
        "platform",
        "topic",
        "title_style",
        "production_hours",
        "publish_time",
        "views",
        "favorites",
        "consultations",
        "conversions",
        "revenue",
    ]

    def run(self, df: pd.DataFrame, kg_constraints: dict[str, Any] | None = None) -> dict[str, Any]:
        method, library_edges = self._try_optional_libraries(df)
        if library_edges:
            edges = library_edges
        else:
            method = "相关性筛选 + 时间顺序 + KG 约束"
            edges = self._fallback_edges(df)
        edges = self._apply_constraints(edges, kg_constraints or {})
        nodes = sorted({node for edge in edges for node in edge[:2]})
        return {
            "method": method,
            "nodes": [{"id": node, "label": _label(node)} for node in nodes],
            "edges": [{"source": a, "target": b, "weight": round(float(w), 3), "reason": reason} for a, b, w, reason in edges[:36]],
            "warning": "这是候选 DAG，用来提出可验证假设；不能把它当作已经证明的因果图。",
            "explanation": "系统先看变量之间是否同步变化，再用发布时间、业务常识和知识图谱约束过滤不合理方向。",
        }

    def _try_optional_libraries(self, df: pd.DataFrame) -> tuple[str, list[tuple[str, str, float, str]]]:
        numeric = [c for c in self.PREFERRED_ORDER if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        if len(numeric) < 3:
            return "", []
        data = df[numeric].fillna(0).to_numpy()
        try:
            from causallearn.search.ConstraintBased.PC import pc

            graph = pc(data)
            matrix = np.asarray(graph.G.graph)
            edges = []
            for i, j in zip(*np.where(matrix != 0)):
                if i < j:
                    source, target = self._order_pair(numeric[i], numeric[j])
                    corr = abs(np.corrcoef(df[source].fillna(0), df[target].fillna(0))[0, 1])
                    edges.append((source, target, float(corr), "causal-learn PC 候选边"))
            return "causal-learn PC", edges
        except Exception:
            pass
        try:
            import lingam

            model = lingam.DirectLiNGAM()
            model.fit(data)
            matrix = np.asarray(model.adjacency_matrix_)
            edges = []
            for i, j in zip(*np.where(abs(matrix) > 0.01)):
                source, target = numeric[i], numeric[j]
                source, target = self._order_pair(source, target)
                edges.append((source, target, abs(float(matrix[i, j])), "LiNGAM 候选边"))
            return "LiNGAM", edges
        except Exception:
            return "", []

    def _fallback_edges(self, df: pd.DataFrame) -> list[tuple[str, str, float, str]]:
        candidates = [c for c in self.PREFERRED_ORDER if c in df.columns]
        numeric = [c for c in candidates if pd.api.types.is_numeric_dtype(df[c])]
        encoded = {}
        for column in candidates:
            if column in numeric:
                encoded[column] = df[column].fillna(0).astype(float)
            else:
                encoded[column] = pd.Series(pd.factorize(df[column].fillna("").astype(str))[0], index=df.index).astype(float)
        edges: list[tuple[str, str, float, str]] = []
        for a, b in zip(candidates, candidates[1:]):
            if a in encoded and b in encoded:
                corr = _safe_corr(encoded[a], encoded[b])
                if corr >= 0.08:
                    source, target = self._order_pair(a, b)
                    edges.append((source, target, corr, "变量同步变化且方向符合业务顺序"))
        outcomes = [c for c in ["consultations", "conversions", "revenue"] if c in encoded]
        strategies = [c for c in ["platform", "topic", "title_style", "production_hours"] if c in encoded]
        for source in strategies:
            for target in outcomes:
                corr = _safe_corr(encoded[source], encoded[target])
                if corr >= 0.05:
                    edges.append((source, target, corr, "策略变量与结果指标存在可验证关系"))
        return sorted(edges, key=lambda e: e[2], reverse=True)

    def _order_pair(self, a: str, b: str) -> tuple[str, str]:
        order = {name: idx for idx, name in enumerate(self.PREFERRED_ORDER)}
        return (a, b) if order.get(a, 999) <= order.get(b, 999) else (b, a)

    def _apply_constraints(self, edges: list[tuple[str, str, float, str]], constraints: dict[str, Any]) -> list[tuple[str, str, float, str]]:
        forbidden = {(item[0], item[1]) for item in constraints.get("forbidden_edges", []) if len(item) >= 2}
        filtered = [edge for edge in edges if (edge[0], edge[1]) not in forbidden]
        seen = set()
        unique = []
        for edge in filtered:
            key = (edge[0], edge[1])
            if key in seen:
                continue
            seen.add(key)
            unique.append(edge)
        return unique


def _safe_corr(a: pd.Series, b: pd.Series) -> float:
    if a.nunique(dropna=False) <= 1 or b.nunique(dropna=False) <= 1:
        return 0.0
    value = np.corrcoef(a.fillna(0), b.fillna(0))[0, 1]
    if np.isnan(value):
        return 0.0
    return abs(float(value))


def _label(name: str) -> str:
    labels = {
        "platform": "平台",
        "topic": "主题",
        "title_style": "标题风格",
        "production_hours": "制作投入",
        "views": "播放量",
        "favorites": "收藏数",
        "consultations": "咨询数",
        "conversions": "成交数",
        "revenue": "收入",
        "account_id": "账号",
        "publish_time": "发布时间",
    }
    return labels.get(name, name)
