#!/usr/bin/env python3
"""Run benchmark with feedback — wraps layered_eval_runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solodeck_v3.bench.layered_eval_runner import run_layered_benchmark


def main() -> int:
    sample = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    report = run_layered_benchmark(sample_size=sample)
    out = ROOT / "data" / "solodeck_v3_memory" / "layered_eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["fars_metrics"], ensure_ascii=False, indent=2))
    print(f"layered_valid_rate={report['layered_valid_rate']}")
    print(f"written {out}")
    return 0 if report["layered_valid_rate"] >= 0.5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
