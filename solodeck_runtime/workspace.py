from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd


class DataWorkspaceRepository:
    """Persistent catalog for datasets, agent runs and display-safe result artifacts."""

    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[1]
        self.path = Path(path or root / "data" / "solodeck_data_agent.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_datasets (
                  workspace_id TEXT NOT NULL,
                  dataset_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  storage_path TEXT NOT NULL,
                  row_count INTEGER NOT NULL,
                  column_count INTEGER NOT NULL,
                  profile_json TEXT NOT NULL,
                  mapping_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY (workspace_id, dataset_id)
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_datasets
                  ON workspace_datasets(workspace_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS workspace_runs (
                  run_id TEXT PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  dataset_id TEXT NOT NULL,
                  session_id TEXT,
                  state_id TEXT,
                  user_task TEXT NOT NULL,
                  task_type TEXT,
                  status TEXT NOT NULL,
                  selected_tools_json TEXT NOT NULL,
                  result_view_json TEXT NOT NULL,
                  reply TEXT NOT NULL,
                  latency_ms REAL NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_runs
                  ON workspace_runs(workspace_id, created_at DESC);
                """
            )

    def register_dataset(
        self,
        workspace_id: str,
        dataset_id: str,
        name: str,
        source_type: str,
        storage_path: str | Path,
        frame: pd.DataFrame,
        mapping: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        profile = profile_dataframe(frame)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO workspace_datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, dataset_id) DO UPDATE SET
                  name=excluded.name, source_type=excluded.source_type,
                  storage_path=excluded.storage_path, row_count=excluded.row_count,
                  column_count=excluded.column_count, profile_json=excluded.profile_json,
                  mapping_json=excluded.mapping_json, updated_at=excluded.updated_at
                """,
                (
                    workspace_id, dataset_id, name[:180], source_type, str(storage_path),
                    len(frame), len(frame.columns), _json(profile), _json(mapping or {}), now, now,
                ),
            )
        return self.get_dataset(workspace_id, dataset_id) or {}

    def list_datasets(self, workspace_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM workspace_datasets WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT ?",
                (workspace_id, max(1, min(limit, 100))),
            ).fetchall()
        return [_dataset_row(row) for row in rows]

    def get_dataset(self, workspace_id: str, dataset_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM workspace_datasets WHERE workspace_id = ? AND dataset_id = ?",
                (workspace_id, dataset_id),
            ).fetchone()
        return _dataset_row(row) if row else None

    def save_run(
        self,
        workspace_id: str,
        dataset_id: str,
        user_task: str,
        result: dict[str, Any],
        result_view: dict[str, Any],
        latency_ms: float,
    ) -> dict[str, Any]:
        run_id = f"run_{uuid4().hex[:16]}"
        task_spec = result.get("task_spec") or {}
        tools = [item.get("tool") for item in result.get("tool_calls") or [] if item.get("tool")]
        skills = result.get("selected_skills") or (result.get("developer_trace") or {}).get("executed_skills") or []
        tools = list(dict.fromkeys([*tools, *skills]))
        status = "completed" if not (result.get("validation_report") or {}).get("block_output") else "blocked"
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                "INSERT INTO workspace_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, workspace_id, dataset_id, result.get("session_id"), result.get("state_id"),
                    user_task[:1200], task_spec.get("task_type"), status, _json(tools),
                    _json(result_view), str(result.get("reply") or "")[:4000], float(latency_ms), created_at,
                ),
            )
        return self.get_run(workspace_id, run_id) or {}

    def list_runs(self, workspace_id: str, limit: int = 40) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM workspace_runs WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, max(1, min(limit, 100))),
            ).fetchall()
        return [_run_row(row) for row in rows]

    def get_run(self, workspace_id: str, run_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM workspace_runs WHERE workspace_id = ? AND run_id = ?",
                (workspace_id, run_id),
            ).fetchone()
        return _run_row(row) if row else None


def profile_dataframe(frame: pd.DataFrame) -> dict[str, Any]:
    numeric = list(frame.select_dtypes(include="number").columns)
    dates = [column for column in frame.columns if "date" in column.lower() or "time" in column.lower()]
    categorical = [column for column in frame.columns if column not in numeric and column not in dates]
    missing = int(frame.isna().sum().sum())
    duplicates = int(frame.duplicated().sum())
    return {
        "columns": [str(column) for column in frame.columns],
        "numeric_columns": numeric,
        "categorical_columns": categorical,
        "date_columns": dates,
        "missing_cells": missing,
        "missing_rate": missing / max(1, frame.size),
        "duplicate_rows": duplicates,
        "quality_score": max(0.0, 1.0 - missing / max(1, frame.size) - duplicates / max(1, len(frame))),
    }


def _dataset_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "workspace_id": row["workspace_id"], "dataset_id": row["dataset_id"],
        "name": row["name"], "source_type": row["source_type"],
        "row_count": row["row_count"], "column_count": row["column_count"],
        "profile": json.loads(row["profile_json"]), "mapping": json.loads(row["mapping_json"]),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _run_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"], "workspace_id": row["workspace_id"],
        "dataset_id": row["dataset_id"], "session_id": row["session_id"],
        "state_id": row["state_id"], "user_task": row["user_task"],
        "task_type": row["task_type"], "status": row["status"],
        "selected_tools": json.loads(row["selected_tools_json"]),
        "result_view": json.loads(row["result_view_json"]), "reply": row["reply"],
        "latency_ms": row["latency_ms"], "created_at": row["created_at"],
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
