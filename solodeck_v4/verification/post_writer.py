from __future__ import annotations

import re
from typing import Any


def validate_post_writer(state: dict[str, Any]) -> dict[str, Any]:
    """PostWriter hook: claim–artifact alignment after compose_response."""
    artifacts = state.get("artifacts") or []
    user = state.get("user_artifact") or {}
    report_text = _text(user)
    issues = []

    artifact_numbers = set()
    for art in artifacts:
        artifact_numbers |= _numbers(_text(art.get("content", {})))
    report_numbers = _numbers(report_text)
    orphan_numbers = {n for n in report_numbers if n not in artifact_numbers and n not in {"0", "1", "2", "95", "100"}}
    if len(orphan_numbers) > 3:
        issues.append("用户可见文案含未绑定 artifact 的数字")

    if re.search(r"已证明|必然|一定导致|guarantee", report_text, re.I):
        validation = state.get("validation_report") or {}
        if validation.get("valid"):
            issues.append("终稿含强因果表述但校验已通过，需降级")

    cards = user.get("action_cards") or state.get("action_cards") or []
    if cards and not any(c.get("title") or c.get("action") for c in cards):
        issues.append("行动卡片缺少可执行标题")

    valid = not issues
    if issues and user:
        user["validation_passed"] = False
        user["limitations"] = (user.get("limitations") or "") + "；" + issues[0]
        state["user_artifact"] = user

    return {
        "name": "post_writer",
        "valid": valid,
        "issues": issues,
        "block_output": bool(issues and re.search(r"隐私|PII", report_text, re.I)),
    }


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values())
    return str(value)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"-?\d+\.?\d*", text))
