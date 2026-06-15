from __future__ import annotations


def classify_failure(validation_report: dict) -> dict:
    issues = validation_report.get("issues", [])
    failure_type = "none"
    joined = " ".join(issues)
    if "隐私" in joined or "Key" in joined:
        failure_type = "privacy_error"
    elif "因果" in joined:
        failure_type = "causal_overclaim"
    elif "区间" in joined or "样本" in joined:
        failure_type = "statistical_instability"
    elif "报告" in joined or "字段" in joined:
        failure_type = "report_format_error"
    elif "缺少产物" in joined:
        failure_type = "tool_error"
    return {"failure_type": failure_type, "issues": issues, "repairable": failure_type != "privacy_error"}

