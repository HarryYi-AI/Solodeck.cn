from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SESSION_ROOT = ROOT / "data" / "solodeck_v4_sessions"
SESSION_ROOT.mkdir(parents=True, exist_ok=True)

_MEMORY: dict[str, dict[str, Any]] = {}


def create_session(dataset_id: str | None = None, cost_budget: float = 1.0) -> dict[str, Any]:
    session_id = f"s4_{uuid.uuid4().hex[:12]}"
    session = {
        "session_id": session_id,
        "dataset_id": dataset_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "turns": [],
        "linked_entities": {},
        "last_task_spec": None,
        "last_trace_id": None,
        "artifact_cache": {},
        "compressed_summary": "",
        "cost_budget": cost_budget,
        "cost_spent": 0.0,
        "plan_history": [],
    }
    _save(session)
    return session


def get_session(session_id: str) -> dict[str, Any] | None:
    if session_id in _MEMORY:
        return _MEMORY[session_id]
    path = SESSION_ROOT / f"{session_id}.json"
    if not path.exists():
        return None
    session = json.loads(path.read_text(encoding="utf-8"))
    _MEMORY[session_id] = session
    return session


def append_turn(session_id: str, role: str, content: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"session not found: {session_id}")
    turn = {
        "role": role,
        "content": content,
        "time": datetime.now(timezone.utc).isoformat(),
        "meta": meta or {},
    }
    session["turns"].append(turn)
    session["updated_at"] = turn["time"]
    _save(session)
    return turn


def update_session(session_id: str, **fields: Any) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"session not found: {session_id}")
    session.update(fields)
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(session)
    return session


def _save(session: dict[str, Any]) -> None:
    sid = session["session_id"]
    _MEMORY[sid] = session
    path = SESSION_ROOT / f"{sid}.json"
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
