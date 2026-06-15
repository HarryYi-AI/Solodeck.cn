from __future__ import annotations


def validate_artifact_completeness(artifacts: list[dict], final_report: dict | None = None) -> dict:
    final_report = final_report or {}
    required_report = ["objective", "method", "data_source", "result", "limitation"]
    missing_report = [field for field in required_report if not final_report.get(field)]
    artifact_ids = {a.get("id") for a in artifacts}
    missing_artifacts = [name for name in ["schema_summary", "data_quality_report", "kg_context"] if name not in artifact_ids]
    issues = [f"报告缺少字段：{field}" for field in missing_report] + [f"缺少产物：{artifact}" for artifact in missing_artifacts]
    return {"name": "artifact_completeness", "valid": not issues, "issues": issues}

