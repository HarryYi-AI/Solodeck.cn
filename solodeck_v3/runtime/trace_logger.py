from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def append_trace(state: dict[str, Any], step: str, role: str, summary: dict[str, Any] | str, artifact_ids: list[str] | None = None) -> dict[str, Any]:
    trace = state.setdefault("trace", [])
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "step": step,
        "role": role,
        "summary": _safe(summary),
        "artifact_ids": artifact_ids or [],
    }
    trace.append(event)
    return state


def _safe(value: Any, max_chars: int = 900) -> Any:
    if isinstance(value, dict):
        return {k: _safe(v, max_chars=max_chars // 2) for k, v in list(value.items())[:16]}
    if isinstance(value, list):
        return [_safe(v, max_chars=max_chars // 2) for v in value[:10]]
    text = str(value)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")

