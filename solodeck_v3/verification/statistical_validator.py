from __future__ import annotations


def validate_statistics(artifacts: list[dict], critique: dict | None = None) -> dict:
    critique = critique or {}
    bootstrap = next((a.get("content", {}) for a in artifacts if a.get("id") == "bootstrap_ci"), {})
    issues = []
    warnings = []
    if bootstrap:
        low, high = bootstrap.get("ci_95", [0, 0])
        if bootstrap.get("sample_size", 0) < 20:
            warnings.append("样本量偏小")
        if low <= 0 <= high:
            warnings.append("置信区间穿过 0")
            if not critique.get("downgraded_to_validation"):
                issues.append("区间不稳定但没有降级为验证建议")
    return {"name": "statistical_validity", "valid": not issues, "issues": issues, "warnings": warnings}

