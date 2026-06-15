from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "data" / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def append_audit(dataset_id: str, step: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "dataset_id": dataset_id,
        "step": step,
        "summary": _compact(payload),
    }
    path = AUDIT_DIR / f"{dataset_id}.jsonl"
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_audit(dataset_id: str, limit: int = 80) -> list[dict[str, Any]]:
    path = AUDIT_DIR / f"{dataset_id}.jsonl"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def _compact(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        return str(value)[:180]
    if isinstance(value, dict):
        return {str(k): _compact(v, depth + 1) for k, v in list(value.items())[:24]}
    if isinstance(value, list):
        return [_compact(v, depth + 1) for v in value[:12]]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)[:180]
