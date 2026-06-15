from __future__ import annotations


def build_user_artifact_view(state: dict) -> dict:
    report = state.get("final_report", {})
    validation = state.get("validation_report", {})
    return {
        "title": "可验证经营建议",
        "objective": report.get("objective", state.get("task", "")),
        "result": report.get("result", ""),
        "confidence": report.get("confidence", "需要验证"),
        "limitations": report.get("limitation", ""),
        "actions": [card for card in state.get("action_cards", [])],
        "validation_passed": validation.get("valid", False),
        "privacy_safe": not validation.get("block_output", False),
    }

