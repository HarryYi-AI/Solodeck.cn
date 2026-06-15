from __future__ import annotations

import json
from pathlib import Path


def generate_regression_task(failure_report: dict, trace_id: str, bench_dir: str | Path = "solodeck_v3/bench/generated_failures") -> dict:
    path = Path(bench_dir)
    path.mkdir(parents=True, exist_ok=True)
    task = {
        "id": f"failure_{trace_id}",
        "type": failure_report.get("failure_type", "unknown"),
        "goal": "复现并修复失败路径",
        "issues": failure_report.get("issues", []),
    }
    (path / f"{task['id']}.json").write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return task

