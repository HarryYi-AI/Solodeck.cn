from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AnalysisState, Artifact, EvidenceObject, TaskSpec


class SQLiteRuntimeRepository:
    """Portable P0 persistence; PostgreSQL can implement the same public methods."""

    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[1]
        self.path = Path(path or root / "data" / "solodeck_data_agent.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                  task_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, session_id TEXT,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_scope ON tasks(project_id, session_id, created_at);
                CREATE TABLE IF NOT EXISTS evidence (
                  evidence_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, task_id TEXT,
                  source_type TEXT, source_id TEXT, dataset_id TEXT, dataset_version TEXT,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_scope ON evidence(project_id, task_id, source_type);
                CREATE TABLE IF NOT EXISTS artifacts (
                  artifact_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, task_id TEXT,
                  artifact_type TEXT, producer_node TEXT, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_scope ON artifacts(project_id, task_id, artifact_type);
                CREATE TABLE IF NOT EXISTS analytical_states (
                  state_id TEXT PRIMARY KEY, parent_state_id TEXT, branch_id TEXT NOT NULL,
                  project_id TEXT NOT NULL, session_id TEXT, task_id TEXT,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_states_scope ON analytical_states(project_id, session_id, branch_id, created_at);
                """
            )

    def save_task(self, task: TaskSpec) -> TaskSpec:
        self._put("tasks", "task_id", task.task_id, task.to_dict(), task.project_id, task.session_id, task.created_at)
        return task

    def get_task(self, task_id: str) -> TaskSpec | None:
        row = self._get("tasks", "task_id", task_id)
        return TaskSpec(**row) if row else None

    def save_evidence(self, evidence: EvidenceObject) -> EvidenceObject:
        data = evidence.to_dict()
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (evidence.evidence_id, evidence.project_id, evidence.task_id, evidence.source_type,
                 evidence.source_id, evidence.dataset_id, evidence.dataset_version, _json(data), evidence.created_at),
            )
        return evidence

    def query_evidence(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
        source_type: str | None = None,
        dataset_id: str | None = None,
        dataset_version: str | None = None,
    ) -> list[EvidenceObject]:
        clauses, values = ["project_id = ?"], [project_id]
        for field, value in (
            ("task_id", task_id),
            ("source_type", source_type),
            ("dataset_id", dataset_id),
            ("dataset_version", dataset_version),
        ):
            if value is not None:
                clauses.append(f"{field} = ?")
                values.append(value)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT payload FROM evidence WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
                values,
            ).fetchall()
        return [EvidenceObject(**json.loads(row["payload"])) for row in rows]

    def save_artifact(self, artifact: Artifact) -> Artifact:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (artifact.artifact_id, artifact.project_id, artifact.task_id, artifact.artifact_type,
                 artifact.producer_node, _json(artifact.to_dict()), artifact.created_at),
            )
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        row = self._get("artifacts", "artifact_id", artifact_id)
        return Artifact(**row) if row else None

    def query_artifacts(self, project_id: str, *, task_id: str | None = None, artifact_type: str | None = None) -> list[Artifact]:
        clauses, values = ["project_id = ?"], [project_id]
        for field, value in (("task_id", task_id), ("artifact_type", artifact_type)):
            if value is not None:
                clauses.append(f"{field} = ?")
                values.append(value)
        with self._connect() as db:
            rows = db.execute(f"SELECT payload FROM artifacts WHERE {' AND '.join(clauses)} ORDER BY created_at DESC", values).fetchall()
        return [Artifact(**json.loads(row["payload"])) for row in rows]

    def save_state(self, state: AnalysisState) -> AnalysisState:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO analytical_states VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (state.state_id, state.parent_state_id, state.branch_id, state.project_id,
                 state.session_id, state.task_id, _json(state.to_dict()), state.created_at),
            )
        return state

    def get_state(self, state_id: str) -> AnalysisState | None:
        row = self._get("analytical_states", "state_id", state_id)
        return AnalysisState.from_dict(row) if row else None

    def list_states(self, project_id: str, session_id: str | None = None, branch_id: str | None = None) -> list[AnalysisState]:
        clauses, values = ["project_id = ?"], [project_id]
        for field, value in (("session_id", session_id), ("branch_id", branch_id)):
            if value is not None:
                clauses.append(f"{field} = ?")
                values.append(value)
        with self._connect() as db:
            rows = db.execute(f"SELECT payload FROM analytical_states WHERE {' AND '.join(clauses)} ORDER BY created_at", values).fetchall()
        return [AnalysisState.from_dict(json.loads(row["payload"])) for row in rows]

    def _put(self, table: str, key_name: str, key: str, payload: dict[str, Any], project_id: str, session_id: str, created_at: str) -> None:
        if table != "tasks" or key_name != "task_id":
            raise ValueError("unsupported repository write")
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?, ?)", (key, project_id, session_id, _json(payload), created_at))

    def _get(self, table: str, key_name: str, key: str) -> dict[str, Any] | None:
        allowed = {
            ("tasks", "task_id"),
            ("artifacts", "artifact_id"),
            ("analytical_states", "state_id"),
        }
        if (table, key_name) not in allowed:
            raise ValueError("unsupported repository query")
        with self._connect() as db:
            row = db.execute(f"SELECT payload FROM {table} WHERE {key_name} = ?", (key,)).fetchone()
        return json.loads(row["payload"]) if row else None


class ArtifactRegistry:
    def __init__(self, repository: SQLiteRuntimeRepository | None = None) -> None:
        self.repository = repository or SQLiteRuntimeRepository()

    def register(self, artifact: Artifact) -> Artifact:
        missing = [item for item in artifact.input_artifacts if self.repository.get_artifact(item) is None]
        if missing:
            raise ValueError(f"unknown input artifacts: {missing}")
        return self.repository.save_artifact(artifact)

    def lineage(self, artifact_id: str) -> dict[str, Any]:
        root = self.repository.get_artifact(artifact_id)
        if root is None:
            raise KeyError(artifact_id)
        nodes, edges, pending, seen = [], [], [root], set()
        while pending:
            current = pending.pop()
            if current.artifact_id in seen:
                continue
            seen.add(current.artifact_id)
            nodes.append(current.to_dict())
            for parent_id in current.input_artifacts:
                edges.append({"source": parent_id, "target": current.artifact_id})
                parent = self.repository.get_artifact(parent_id)
                if parent is not None:
                    pending.append(parent)
        return {"nodes": nodes, "edges": edges}


class StateStore:
    def __init__(self, repository: SQLiteRuntimeRepository | None = None) -> None:
        self.repository = repository or SQLiteRuntimeRepository()

    def snapshot(self, state: AnalysisState) -> AnalysisState:
        return self.repository.save_state(state)

    def restore(self, state_id: str) -> AnalysisState:
        state = self.repository.get_state(state_id)
        if state is None:
            raise KeyError(state_id)
        return state

    def branch(self, state_id: str, branch_id: str, **changes: Any) -> AnalysisState:
        source = self.restore(state_id).to_dict()
        source.update(changes)
        source.update({
            "state_id": AnalysisState.__dataclass_fields__["state_id"].default_factory(),
            "parent_state_id": state_id,
            "branch_id": branch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return self.snapshot(AnalysisState.from_dict(source))

    def rollback(self, current_state_id: str, target_state_id: str) -> AnalysisState:
        current, target = self.restore(current_state_id), self.restore(target_state_id)
        if current.project_id != target.project_id or current.session_id != target.session_id:
            raise ValueError("rollback target is outside the analytical session")
        source = target.to_dict()
        source.update({
            "state_id": AnalysisState.__dataclass_fields__["state_id"].default_factory(),
            "parent_state_id": current_state_id,
            "branch_id": current.branch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return self.snapshot(AnalysisState.from_dict(source))

    def diff(self, left_id: str, right_id: str) -> dict[str, dict[str, Any]]:
        left, right = self.restore(left_id).to_dict(), self.restore(right_id).to_dict()
        ignored = {"state_id", "parent_state_id", "created_at"}
        return {key: {"left": left.get(key), "right": right.get(key)} for key in sorted(set(left) | set(right)) if key not in ignored and left.get(key) != right.get(key)}

    def merge(self, base_id: str, branch_id: str, *, prefer: str = "branch") -> AnalysisState:
        base = self.restore(base_id)
        candidates = self.repository.list_states(base.project_id, base.session_id, branch_id)
        if not candidates:
            raise KeyError(branch_id)
        branch = candidates[-1]
        merged = base.to_dict()
        for key, value in branch.to_dict().items():
            if key not in {"state_id", "parent_state_id", "branch_id", "created_at"} and (prefer == "branch" or not merged.get(key)):
                merged[key] = value
        merged.update({
            "state_id": AnalysisState.__dataclass_fields__["state_id"].default_factory(),
            "parent_state_id": base_id,
            "branch_id": base.branch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return self.snapshot(AnalysisState.from_dict(merged))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
