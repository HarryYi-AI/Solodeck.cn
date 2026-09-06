from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Iterable


def load_ds1000_pandas_numpy(path: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    """Load an official DS-1000 jsonl.gz export without changing its tests."""
    selected = []
    with gzip.open(Path(path), "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            library = str(row.get("metadata", {}).get("library") or row.get("library") or "").lower()
            if library not in {"pandas", "numpy"}:
                continue
            selected.append({
                "task_id": f"ds1000:{row.get('metadata', {}).get('problem_id', row.get('problem_id', len(selected)))}",
                "source": "DS-1000-official",
                "kind": library,
                "prompt": row.get("prompt") or row.get("problem"),
                "reference": row,
            })
            if len(selected) >= limit:
                break
    return selected


def load_infiagent_dabench(records: str | Path | Iterable[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """Normalize downloaded InfiAgent-DABench records while retaining raw scoring fields."""
    if isinstance(records, (str, Path)):
        path = Path(records)
        if path.suffix == ".jsonl":
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            rows = value if isinstance(value, list) else value.get("data", value.get("records", []))
    else:
        rows = list(records)
    output = []
    for index, row in enumerate(rows[:limit]):
        output.append({
            "task_id": f"infiagent-dabench:{row.get('id', row.get('question_id', index))}",
            "source": "InfiAgent-DABench-official",
            "kind": "data_analysis",
            "prompt": row.get("question") or row.get("prompt") or row.get("instruction"),
            "data_files": row.get("data_files") or row.get("file_name") or row.get("files"),
            "reference": row,
        })
    return output
