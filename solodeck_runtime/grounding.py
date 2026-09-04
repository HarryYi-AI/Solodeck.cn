from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .models import EvidenceObject, TaskSpec


ALIASES = {
    "customer_id": {"customer_id", "cust_id", "user_identifier", "user_id", "客户编号", "用户编号"},
    "content_id": {"content_id", "post_id", "video_id", "内容编号"},
    "platform": {"platform", "channel", "渠道", "平台"},
    "revenue": {"revenue", "amount", "gmv", "收入", "营收"},
    "conversions": {"conversions", "orders", "成交", "订单"},
}


@dataclass
class GroundingResult:
    dataset_versions: dict[str, str]
    selected_tables: list[str]
    selected_columns: list[str]
    join_candidates: list[dict[str, Any]]
    evidence: list[EvidenceObject]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_versions": self.dataset_versions,
            "selected_tables": self.selected_tables,
            "selected_columns": self.selected_columns,
            "join_candidates": self.join_candidates,
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": self.warnings,
        }


class DataGrounder:
    """Source-aware grounding over schemas, entities, artifacts, state and text."""

    def ground(
        self,
        task: TaskSpec,
        datasets: dict[str, pd.DataFrame],
        *,
        text_documents: dict[str, str] | None = None,
        artifact_evidence: list[EvidenceObject] | None = None,
        state_evidence: list[EvidenceObject] | None = None,
    ) -> GroundingResult:
        versions, evidence, scored_columns = {}, [], []
        for table, frame in datasets.items():
            version = dataset_version(frame)
            versions[table] = version
            profile = profile_schema(frame)
            relevance = self._table_relevance(task, table, profile)
            evidence.append(EvidenceObject(
                project_id=task.project_id, task_id=task.task_id, source_type="schema",
                source_id=f"schema:{table}", dataset_id=table, dataset_version=version,
                content_summary=f"{table}: {len(frame)} 行、{len(frame.columns)} 列",
                structured_payload=profile, retrieval_score=relevance, confidence=0.95,
                provenance=[{"table": table, "dataset_version": version}], generated_by="SchemaGrounder",
            ))
            for column in frame.columns:
                score = self._column_relevance(task, str(column)) + relevance * 0.2
                if score > 0.15:
                    scored_columns.append((score, table, str(column)))

        joins = infer_join_candidates(datasets)
        for join in joins:
            evidence.append(EvidenceObject(
                project_id=task.project_id, task_id=task.task_id, source_type="graph",
                source_id=f"join:{join['left_table']}:{join['right_table']}:{join['canonical_entity']}",
                content_summary=f"候选连接：{join['left_table']}.{join['left_column']} = {join['right_table']}.{join['right_column']}",
                structured_payload=join, retrieval_score=join["confidence"], confidence=join["confidence"],
                provenance=[{"method": "alias+cardinality"}], generated_by="EntityGrounder",
                warnings=[] if join["confidence"] >= 0.8 else ["列名相似不代表语义完全一致，执行连接前需验证"],
            ))

        evidence.extend(self._text_ground(task, text_documents or {}))
        evidence.extend(artifact_evidence or [])
        evidence.extend(state_evidence or [])
        evidence.sort(key=lambda item: item.retrieval_score, reverse=True)
        selected_tables = [name for name, _ in sorted(((name, self._table_relevance(task, name, profile_schema(df))) for name, df in datasets.items()), key=lambda x: x[1], reverse=True)]
        selected_columns = [column for _, _, column in sorted(scored_columns, reverse=True)]
        return GroundingResult(versions, selected_tables, list(dict.fromkeys(selected_columns))[:20], joins, evidence[:40])

    @staticmethod
    def _table_relevance(task: TaskSpec, table: str, profile: dict[str, Any]) -> float:
        requested = set(task.candidate_tables)
        score = 0.8 if table in requested else 0.2
        columns = set(profile["columns"])
        score += 0.15 * bool(task.outcome and task.outcome in columns)
        score += 0.15 * bool(task.treatment and task.treatment in columns)
        return min(1.0, score)

    @staticmethod
    def _column_relevance(task: TaskSpec, column: str) -> float:
        score = 0.0
        if column in task.candidate_columns: score += 0.7
        if column == task.treatment: score += 1.0
        if column == task.outcome: score += 1.0
        if column in task.dimensions: score += 0.8
        if column.lower() in task.user_goal.lower(): score += 0.6
        return min(1.0, score)

    def _text_ground(self, task: TaskSpec, documents: dict[str, str]) -> list[EvidenceObject]:
        if not documents:
            return []
        query_tokens = _tokens(task.user_goal)
        document_tokens = {doc_id: _tokens(text) for doc_id, text in documents.items()}
        average_length = sum(map(len, document_tokens.values())) / max(1, len(document_tokens))
        frequency = Counter(token for tokens in document_tokens.values() for token in set(tokens))
        hits = []
        for doc_id, tokens in document_tokens.items():
            score = _bm25(query_tokens, tokens, frequency, len(documents), average_length)
            if score <= 0:
                continue
            hits.append(EvidenceObject(
                project_id=task.project_id, task_id=task.task_id, source_type="text",
                source_id=doc_id, content_summary=(documents[doc_id][:180] + "…") if len(documents[doc_id]) > 180 else documents[doc_id],
                retrieval_score=min(1.0, score / 5), confidence=0.6,
                provenance=[{"method": "bm25", "document_id": doc_id}], generated_by="TextGrounder",
            ))
        return sorted(hits, key=lambda item: item.retrieval_score, reverse=True)[:8]


def dataset_version(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update("|".join(map(str, frame.columns)).encode())
    digest.update(str(frame.shape).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return digest.hexdigest()[:20]


def profile_schema(frame: pd.DataFrame) -> dict[str, Any]:
    columns = []
    for name in frame.columns:
        series = frame[name]
        samples = [value for value in series.dropna().astype(str).drop_duplicates().head(3).tolist()]
        columns.append({
            "name": str(name), "dtype": str(series.dtype), "null_count": int(series.isna().sum()),
            "null_rate": float(series.isna().mean()), "unique_count": int(series.nunique(dropna=True)),
            "is_candidate_key": bool(len(series) and series.notna().all() and series.nunique() == len(series)),
            "sample_values": samples,
        })
    return {"row_count": int(len(frame)), "columns": [str(c) for c in frame.columns], "column_profiles": columns}


def infer_join_candidates(datasets: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    aliases = {alias.lower(): canonical for canonical, values in ALIASES.items() for alias in values}
    candidates = []
    names = list(datasets)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1:]:
            left, right = datasets[left_name], datasets[right_name]
            for left_col in left.columns:
                canonical = aliases.get(str(left_col).lower())
                if not canonical:
                    continue
                for right_col in right.columns:
                    if aliases.get(str(right_col).lower()) != canonical:
                        continue
                    overlap = _overlap(left[left_col], right[right_col])
                    candidates.append({
                        "left_table": left_name, "left_column": str(left_col), "right_table": right_name,
                        "right_column": str(right_col), "canonical_entity": canonical,
                        "overlap": overlap, "confidence": round(0.55 + 0.4 * overlap, 3),
                    })
    return sorted(candidates, key=lambda item: item["confidence"], reverse=True)


def _overlap(left: pd.Series, right: pd.Series) -> float:
    a, b = set(left.dropna().astype(str)), set(right.dropna().astype(str))
    return len(a & b) / max(1, min(len(a), len(b)))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", (text or "").lower())


def _bm25(query: list[str], document: list[str], df: Counter, total: int, avg_len: float) -> float:
    counts, score, k1, b = Counter(document), 0.0, 1.5, 0.75
    for token in set(query):
        tf = counts[token]
        if not tf:
            continue
        idf = math.log(1 + (total - df[token] + 0.5) / (df[token] + 0.5))
        score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(document) / max(1, avg_len)))
    return score
