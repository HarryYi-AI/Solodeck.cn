"""Canonical protocols for the stateful and verifiable SoloDeck Data Agent."""

from .models import AgentState, AnalysisState, Artifact, EvidenceObject, PlanStep, TaskSpec, Workflow, WorkflowNode
from .persistence import ArtifactRegistry, SQLiteRuntimeRepository, StateStore
from .grounding import DataGrounder, GroundingResult
from .retrieval import (
    ArtifactRetriever, GraphRetriever, RetrievalQuery, SchemaRetriever,
    StateRetriever, StructuredRetriever, TextRetriever,
)
from .workflow import WorkflowCompiler, WorkflowValidator
from .sources import DataFrameSourceAdapter, FileSourceAdapter, SourceAdapter, SourceDescriptor
from .tools import DataToolRegistry, ToolManifest

__all__ = [
    "AgentState", "AnalysisState", "Artifact", "ArtifactRegistry", "DataGrounder", "EvidenceObject", "PlanStep",
    "GroundingResult", "SQLiteRuntimeRepository", "StateStore", "TaskSpec", "Workflow",
    "WorkflowCompiler", "WorkflowNode", "WorkflowValidator", "RetrievalQuery",
    "StructuredRetriever", "SchemaRetriever", "ArtifactRetriever", "StateRetriever",
    "GraphRetriever", "TextRetriever",
    "DataFrameSourceAdapter", "FileSourceAdapter", "SourceAdapter", "SourceDescriptor",
    "DataToolRegistry", "ToolManifest",
    "run_solodatabench_lite",
]


def run_solodatabench_lite():
    from .benchmark import run_solodatabench_lite as run

    return run()
