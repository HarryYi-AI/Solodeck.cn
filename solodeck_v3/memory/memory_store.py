from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEMORY_ROOT = ROOT / "data" / "solodeck_v3_memory"
MEMORY_ROOT.mkdir(parents=True, exist_ok=True)


class JsonMemoryStore:
    def __init__(self, namespace: str) -> None:
        self.path = MEMORY_ROOT / f"{namespace}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, item: dict[str, Any]) -> dict[str, Any]:
        payload = {"time": datetime.now(timezone.utc).isoformat(), **item}
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def read(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:]


def compact_payload(payload: Any, max_chars: int = 900) -> Any:
    text = str(payload)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")

