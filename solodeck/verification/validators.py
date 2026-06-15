from __future__ import annotations

import re
from typing import Any


def artifact_completeness_check(artifacts: dict[str, Any], required: list[str]) -> dict[str, Any]:
    missing = [name for name in required if name not in artifacts or artifacts.get(name) in [None, {}, []]]
    return {"name": "artifact_completeness", "valid": not missing, "issues": [f"缺少产物：{m}" for m in missing]}


def statistical_validity_check(artifacts: dict[str, Any]) -> dict[str, Any]:
    effect = artifacts.get("effect", {})
    issues = []
    if effect:
        low, high = effect.get("ci_95", [0, 0])
        if effect.get("sample_size", 0) < 20 and artifacts.get("validation_mode") != "low_cost_validation":
            issues.append("样本量偏少")
        if low <= 0 <= high and artifacts.get("validation_mode") != "low_cost_validation":
            issues.append("置信区间穿过 0，不能直接放大")
    return {"name": "statistical_validity", "valid": not issues, "issues": issues}


def causal_claim_check(text_or_artifacts: Any) -> dict[str, Any]:
    text = str(text_or_artifacts)
    overclaim_patterns = [r"已证明[^，。；]*导致", r"证明[^，。；]*必然", r"一定导致", r"必然提升", r"\bguarantee\b", r"\bproves\b"]
    issues = [f"存在过度因果表达：{pattern}" for pattern in overclaim_patterns if re.search(pattern, text, flags=re.I)]
    return {"name": "causal_claim", "valid": not issues, "issues": issues}


def privacy_check(text_or_artifacts: Any) -> dict[str, Any]:
    text = str(text_or_artifacts)
    issues = []
    if re.search(r"QC-[A-Za-z0-9-]{20,}", text):
        issues.append("疑似 API Key 泄露")
    if re.search(r"\b1[3-9]\d{9}\b", text):
        issues.append("疑似手机号泄露")
    return {"name": "privacy", "valid": not issues, "issues": issues}


def trace_completeness_check(trace: list[dict[str, Any]] | list[str]) -> dict[str, Any]:
    required = ["TaskCompiler", "DataPerception", "HypothesisTreePlanner", "BudgetController", "MultiPlanExecution", "Verification"]
    names = [item.get("step") if isinstance(item, dict) else str(item) for item in trace]
    missing = [name for name in required if name not in names]
    return {"name": "trace_completeness", "valid": not missing, "issues": [f"缺少追踪步骤：{m}" for m in missing]}


def output_format_check(output: Any) -> dict[str, Any]:
    valid = isinstance(output, dict)
    return {"name": "output_format", "valid": valid, "issues": [] if valid else ["最终输出必须是 JSON-ready dict"]}


def validate_final_artifacts(artifacts: dict[str, Any], required: list[str], trace: list[Any]) -> dict[str, Any]:
    checks = [
        artifact_completeness_check(artifacts, required),
        statistical_validity_check(artifacts),
        causal_claim_check(artifacts),
        privacy_check(artifacts),
        trace_completeness_check(trace),
        output_format_check(artifacts),
    ]
    issues = [issue for check in checks for issue in check["issues"]]
    return {"valid": not issues, "checks": checks, "issues": issues}
