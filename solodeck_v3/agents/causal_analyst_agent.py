from __future__ import annotations


class CausalAnalystAgent:
    name = "CausalAnalystAgent"

    def downgrade_if_needed(self, validation_report: dict, critique: dict) -> dict:
        issues = "；".join(validation_report.get("issues", []))
        if critique.get("unstable_ci") or "区间" in issues or "因果" in issues:
            return {"claim_level": "需要验证", "reason": "统计区间或因果条件不足，不能直接放大。"}
        return {"claim_level": "可谨慎行动", "reason": "基础统计和因果安全检查未发现阻断项。"}

