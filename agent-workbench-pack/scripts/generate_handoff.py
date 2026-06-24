#!/usr/bin/env python3
"""Generate handoff markdown from latest snapshot or trace_id."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAP = ROOT / "data" / "solodeck_v3_memory" / "snapshots"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-id", default="")
    args = parser.parse_args()
    trace_id = args.trace_id
    if not trace_id:
        files = sorted(SNAP.glob("*.compile_task.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            print("no snapshots found")
            return
        trace_id = files[0].name.split(".", 1)[0]

    compile_path = SNAP / f"{trace_id}.compile_task.json"
    lines = [
        f"# Handoff — {trace_id}",
        "",
        f"- snapshot: `{compile_path}`" if compile_path.exists() else "- snapshot: missing",
        "- next: run `python agent-workbench-pack/scripts/verify_agent.py`",
        "- memory: `data/solodeck_v3_memory/`",
        "",
    ]
    if compile_path.exists():
        data = json.loads(compile_path.read_text(encoding="utf-8"))
        lines.append("## TaskSpec")
        lines.append("```json")
        lines.append(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
        lines.append("```")

    out = ROOT / "data" / "solodeck_v3_memory" / f"handoff_{trace_id}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
