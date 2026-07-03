from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CheckpointStore:
    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(__file__).resolve().parents[2]
        self.root = Path(root or base / "data" / "runtime_checkpoints")
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, trace_id: str, node: str, state: dict[str, Any]) -> Path:
        path = self.root / trace_id / f"{len(list((self.root / trace_id).glob('*.json'))) + 1:03d}_{node}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_safe(state), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    def list(self, trace_id: str) -> list[Path]:
        return sorted((self.root / trace_id).glob("*.json"))

    def replay(self, trace_id: str, checkpoint: int = -1) -> dict[str, Any]:
        paths = self.list(trace_id)
        if not paths:
            raise KeyError(f"checkpoint not found: {trace_id}")
        return json.loads(paths[checkpoint].read_text(encoding="utf-8"))


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        private_keys = {"df", "text", "artifact_cache", "raw_data", "structured_data", "unstructured_chunks"}
        return {str(k): _safe(v) for k, v in value.items() if k not in private_keys}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if hasattr(value, "item"):
        try: return value.item()
        except Exception: pass
    return value
