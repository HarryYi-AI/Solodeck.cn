from __future__ import annotations


def validate_output_format(user_artifact: dict | None, developer_trace: dict | None = None) -> dict:
    artifact = user_artifact or {}
    issues = []
    if not isinstance(artifact, dict):
        issues.append("用户产物不是结构化对象")
    if "actions" in artifact:
        required = ["title", "objective", "result", "confidence", "actions"]
    else:
        required = ["objective", "result"]
    for field in required:
        if not artifact.get(field):
            issues.append(f"用户产物缺少字段：{field}")
    actions = artifact.get("actions", [])
    if actions and not all(isinstance(card, dict) and card.get("title") for card in actions):
        issues.append("行动卡格式不完整")
    trace_text = str(developer_trace or {})
    if "raw_records" in trace_text or "raw_private_data" in trace_text:
        issues.append("开发追踪暴露了原始私有数据")
    return {"name": "output_format", "valid": not issues, "issues": issues}
