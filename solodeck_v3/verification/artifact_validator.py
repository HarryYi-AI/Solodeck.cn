from __future__ import annotations


def validate_artifact_completeness(artifacts: list[dict], final_report: dict | None = None) -> dict:
    final_report = final_report or {}
    required_report = ["objective", "method", "data_source", "result", "limitation"]
    missing_report = [field for field in required_report if not final_report.get(field)]
    artifact_ids = {a.get("id") for a in artifacts}
    required_artifacts = ["schema_summary", "data_quality_report"]
    method = str(final_report.get("method", ""))
    if "知识图谱" in method or "候选因果图" in method:
        required_artifacts.append("kg_context")
    missing_artifacts = [name for name in required_artifacts if name not in artifact_ids]
    issues = [f"报告缺少字段：{field}" for field in missing_report] + [f"缺少产物：{artifact}" for artifact in missing_artifacts]
    return {"name": "artifact_completeness", "valid": not issues, "issues": issues}
