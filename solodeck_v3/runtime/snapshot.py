from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from solodeck_v3.memory.memory_store import MEMORY_ROOT


SNAPSHOT_DIR = MEMORY_ROOT / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def save_snapshot(trace_id: str, state: dict[str, Any], name: str) -> str:
    safe = {k: v for k, v in state.items() if k not in {"df"}}
    path = SNAPSHOT_DIR / f"{trace_id}.{name}.json"
    path.write_text(json.dumps(_json_safe(safe), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_snapshot(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

