from __future__ import annotations

import re


def validate_privacy(payload: object) -> dict:
    text = str(payload)
    issues = []
    if re.search(r"QC-[A-Za-z0-9-]{16,}", text):
        issues.append("疑似 API Key 泄露")
    if re.search(r"\b1[3-9]\d{9}\b", text):
        issues.append("疑似手机号泄露")
    return {"name": "privacy", "valid": not issues, "issues": issues, "block_output": bool(issues)}

