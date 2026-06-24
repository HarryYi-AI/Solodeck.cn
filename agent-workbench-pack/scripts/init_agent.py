#!/usr/bin/env python3
"""Initialize SoloDeck workbench state — idempotent."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEMORY = ROOT / "data" / "solodeck_v3_memory"
STATE = ROOT / "agent_state.json"
BOARD = ROOT / "task_board.json"
VERSION = Path(__file__).resolve().parents[1] / "VERSION"


def main() -> None:
    MEMORY.mkdir(parents=True, exist_ok=True)
    pack_version = VERSION.read_text(encoding="utf-8").strip()
    if not STATE.exists():
        STATE.write_text(json.dumps({
            "initialized_at": datetime.now(timezone.utc).isoformat(),
            "pack_version": pack_version,
            "last_trace_id": None,
            "status": "ready",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"created {STATE}")
    else:
        print(f"exists {STATE}")

    if not BOARD.exists():
        BOARD.write_text(json.dumps({
            "active_task": {
                "id": "bootstrap",
                "goal": "跑通 v3-agent 并验证 layered eval",
                "acceptance_commands": [
                    "python agent-workbench-pack/scripts/verify_agent.py",
                ],
            },
            "backlog": [],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"created {BOARD}")
    else:
        print(f"exists {BOARD}")

    (ROOT / ".workbench-version").write_text(pack_version + "\n", encoding="utf-8")
    print(f"workbench pack {pack_version} ready")


if __name__ == "__main__":
    main()
