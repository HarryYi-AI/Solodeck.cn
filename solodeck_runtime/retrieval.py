from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from .models import EvidenceObject
from .persistence import SQLiteRuntimeRepository


@dataclass(frozen=True)
class RetrievalQuery:
    project_id: str
    task_id: str
    query: str = ""
    session_id: str | None = None
    dataset_id: str | None = None
    dataset_version: str | None = None
    source_type: str | None = None
    artifact_type: str | None = None
    referenced_id: str | None = None
    limit: int = 10


class Retriever(Protocol):
    def retrieve(self, query: RetrievalQuery) -> list[EvidenceObject]: ...


class SchemaRetriever:
    def __init__(self, repository: SQLiteRuntimeRepository) -> None:
        self.repository = repository

    def retrieve(self, query: RetrievalQuery) -> list[EvidenceObject]:
        return self.repository.query_evidence(
            query.project_id,
            source_type="schema",
            dataset_id=query.dataset_id,
            dataset_version=query.dataset_version,
        )[: query.limit]


class ArtifactRetriever:
    """Artifact retrieval is exact and lineage-aware, not vector based."""

    def __init__(self, repository: SQLiteRuntimeRepository) -> None:
        self.repository = repository

    def retrieve(self, query: RetrievalQuery) -> list[EvidenceObject]:
        if query.referenced_id:
            artifact = self.repository.get_artifact(query.referenced_id)
            artifacts = [artifact] if artifact and artifact.project_id == query.project_id else []
        else:
            artifacts = self.repository.query_artifacts(
                query.project_id,
                task_id=query.task_id or None,
                artifact_type=query.artifact_type,
            )[: query.limit]
        return [
            EvidenceObject(
                project_id=query.project_id,
                task_id=query.task_id,
                source_type="artifact",
                source_id=item.artifact_id,
                artifact_id=item.artifact_id,
                content_summary=f"{item.artifact_type}，由 {item.skill} 生成",
                structured_payload=item.payload,
                retrieval_score=1.0 if query.referenced_id else 0.85,
                confidence=1.0 if item.validation_status == "valid" else 0.6,
                provenance=[{
                    "producer_node": item.producer_node,
                    "skill": item.skill,
                    "input_artifacts": item.input_artifacts,
                    "dataset_versions": item.input_dataset_versions,
                }],
                generated_by="ArtifactRetriever",
                validated_by=[item.validation_status],
                warnings=item.warnings,
            )
            for item in artifacts
            if item is not None
        ]


class StateRetriever:
    def __init__(self, repository: SQLiteRuntimeRepository) -> None:
        self.repository = repository

    def retrieve(self, query: RetrievalQuery) -> list[EvidenceObject]:
        states = self.repository.list_states(query.project_id, query.session_id)
        if query.referenced_id:
            states = [state for state in states if state.state_id == query.referenced_id]
        if query.dataset_version:
            states = [state for state in states if query.dataset_version in state.dataset_versions.values()]
        return [
            EvidenceObject(
                project_id=query.project_id,
                task_id=query.task_id,
                source_type="state",
                source_id=state.state_id,
                content_summary="；".join(state.final_conclusions[:1]) or f"分析状态 {state.state_id}",
                structured_payload={
                    "state_id": state.state_id,
                    "parent_state_id": state.parent_state_id,
                    "branch_id": state.branch_id,
                    "selected_tables": state.selected_tables,
                    "selected_columns": state.selected_columns,
                    "artifacts": state.artifacts,
                    "validation_status": state.validation_status,
                },
                retrieval_score=1.0 if query.referenced_id else 0.75,
                confidence=1.0,
                provenance=[{"state_id": state.state_id, "task_id": state.task_id}],
                generated_by="StateRetriever",
            )
            for state in reversed(states[-query.limit :])
        ]


class GraphRetriever:
    """Graph evidence is explanatory context, never causal ground truth."""

    def __init__(self, repository: SQLiteRuntimeRepository) -> None:
        self.repository = repository

    def retrieve(self, query: RetrievalQuery) -> list[EvidenceObject]:
        return self.repository.query_evidence(
            query.project_id,
            source_type="graph",
            dataset_id=query.dataset_id,
            dataset_version=query.dataset_version,
        )[: query.limit]


class TextRetriever:
    """Portable sparse retrieval; PostgreSQL FTS/pgvector can replace this backend."""

    def __init__(self, repository: SQLiteRuntimeRepository) -> None:
        self.repository = repository

    def retrieve(self, query: RetrievalQuery) -> list[EvidenceObject]:
        candidates = self.repository.query_evidence(query.project_id, source_type="text")
        query_tokens = _tokens(query.query)
        document_tokens = [_tokens(item.content_summary) for item in candidates]
        document_frequency = Counter(token for tokens in document_tokens for token in set(tokens))
        average_length = sum(map(len, document_tokens)) / max(1, len(document_tokens))
        scored = []
        for item, tokens in zip(candidates, document_tokens):
            score = _bm25(query_tokens, tokens, document_frequency, len(candidates), average_length)
            if score <= 0:
                continue
            item.retrieval_score = min(1.0, score / 5)
            item.provenance = [*item.provenance, {"retriever": "bm25-local"}]
            scored.append(item)
        return sorted(scored, key=lambda item: item.retrieval_score, reverse=True)[: query.limit]


class StructuredRetriever:
    """Routes scoped queries to source-specific retrieval backends."""

    def __init__(self, repository: SQLiteRuntimeRepository) -> None:
        self.backends: dict[str, Retriever] = {
            "schema": SchemaRetriever(repository),
            "artifact": ArtifactRetriever(repository),
            "state": StateRetriever(repository),
            "graph": GraphRetriever(repository),
            "text": TextRetriever(repository),
        }

    def retrieve(self, query: RetrievalQuery) -> list[EvidenceObject]:
        sources = [query.source_type] if query.source_type else list(self.backends)
        evidence = []
        for source in sources:
            backend = self.backends.get(source or "")
            if backend is not None:
                evidence.extend(backend.retrieve(query))
        evidence.sort(key=lambda item: (item.confidence, item.retrieval_score), reverse=True)
        return evidence[: query.limit]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", (text or "").lower())


def _bm25(query: list[str], document: list[str], df: Counter, total: int, average_length: float) -> float:
    counts, score, k1, b = Counter(document), 0.0, 1.5, 0.75
    for token in set(query):
        if not counts[token]:
            continue
        inverse_frequency = math.log(1 + (total - df[token] + 0.5) / (df[token] + 0.5))
        score += inverse_frequency * counts[token] * (k1 + 1) / (
            counts[token] + k1 * (1 - b + b * len(document) / max(1, average_length))
        )
    return score
