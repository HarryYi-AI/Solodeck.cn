from __future__ import annotations

import re


def validate_causal_claims(artifacts: list[dict], final_report: dict | None, critique: dict | None = None) -> dict:
    final_report = final_report or {}
    critique = critique or {}
    text = str(final_report)
    issues = []
    if re.search(r"已证明[^，。；]*导致|一定导致|必然提升|guarantee|proves", text, flags=re.I):
        issues.append("存在未支持的强因果表述")
    readiness = critique.get("causal_readiness", {})
    if readiness and readiness.get("score", 0) < 70 and not critique.get("downgraded_to_validation"):
        issues.append("因果准备度不足但没有降级")
    return {"name": "causal_validity", "valid": not issues, "issues": issues}

