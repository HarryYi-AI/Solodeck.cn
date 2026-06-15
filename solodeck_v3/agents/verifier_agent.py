from __future__ import annotations


class VerifierAgent:
    name = "VerifierAgent"

    def summarize_validation(self, validation_report: dict) -> dict:
        checks = validation_report.get("checks", [])
        return {
            "valid": bool(validation_report.get("valid")),
            "failed_checks": [c.get("name") for c in checks if not c.get("valid")],
            "blocked": bool(validation_report.get("block_output")),
        }

