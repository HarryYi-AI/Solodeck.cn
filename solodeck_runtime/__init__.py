"""Canonical protocols for the stateful and verifiable SoloDeck Data Agent."""

from .models import AnalysisState, Artifact, EvidenceObject, TaskSpec, Workflow, WorkflowNode
from .persistence import ArtifactRegistry, SQLiteRuntimeRepository, StateStore
from .grounding import DataGrounder, GroundingResult
from .retrieval import (
    ArtifactRetriever, GraphRetriever, RetrievalQuery, SchemaRetriever,
    StateRetriever, StructuredRetriever, TextRetriever,
)
from .workflow import WorkflowCompiler, WorkflowValidator

__all__ = [
    "AnalysisState", "Artifact", "ArtifactRegistry", "DataGrounder", "EvidenceObject",
    "GroundingResult", "SQLiteRuntimeRepository", "StateStore", "TaskSpec", "Workflow",
    "WorkflowCompiler", "WorkflowNode", "WorkflowValidator", "RetrievalQuery",
    "StructuredRetriever", "SchemaRetriever", "ArtifactRetriever", "StateRetriever",
    "GraphRetriever", "TextRetriever",
    "run_solodatabench_lite",
]


def run_solodatabench_lite():
    from .benchmark import run_solodatabench_lite as run

    return run()
