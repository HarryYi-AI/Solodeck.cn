#!/usr/bin/env python3
"""Run SoloDeck verification gate — does not modify runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solo_creator_agent.src.data_loader import load_contents
from solodeck_v3.bench.layered_eval import run_layered_eval
from solodeck_v3.workflows.data_agent_graph import run_v3_data_agent


def main() -> int:
    data_path = ROOT / "data" / "solodeck_synthetic" / "mock_contents.csv"
    if not data_path.exists():
        print(f"missing fixture: {data_path}", file=sys.stderr)
        return 1
    df = load_contents(data_path)
    task = "评估痛点标题是否带来更多咨询，并给出可验证行动建议。"
    result = run_v3_data_agent(task, df, max_revisions=1)
    layered = run_layered_eval(result, task=task)
    print(json.dumps({
        "trace_id": result.get("trace_id"),
        "validation_valid": (result.get("validation_report") or {}).get("valid"),
        "layered": layered,
    }, ensure_ascii=False, indent=2))
    ok = bool(layered.get("all_valid")) and bool((result.get("validation_report") or {}).get("valid"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
