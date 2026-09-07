from __future__ import annotations

import hashlib
import math


def mock_embedding(text: str, dimensions: int = 16) -> list[float]:
    """Offline deterministic embedding for tests; not used for live structured data."""
    vector = [0.0] * dimensions
    for token in (text or "").lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:2], "big") % dimensions] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def mock_analysis(strategy: str, *, metric: str = "save_rate", value: float = 0.05) -> dict:
    return {
        "trace_id": f"mock_{abs(hash((strategy, metric, value)))}",
        "task_spec": {"task_type": "descriptive_comparison", "objective": strategy},
        "artifacts": [{"id": "descriptive_comparison", "content": {metric: value, "sample_size": 20}}],
        "action_cards": [{"title": strategy, "action": strategy, "evidence": f"{metric}={value}"}],
        "validation_report": {"valid": True, "issues": []},
        "selected_skills": ["DescriptiveComparisonSkill"],
    }
