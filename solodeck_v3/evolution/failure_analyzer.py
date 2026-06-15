from __future__ import annotations

from .error_analyzer import classify_failure


def analyze_failure(validation_report: dict) -> dict:
    return classify_failure(validation_report)

