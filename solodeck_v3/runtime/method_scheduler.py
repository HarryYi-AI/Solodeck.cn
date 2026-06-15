from __future__ import annotations

import math
from collections import Counter
from typing import Any


def method_entropy(method_counts: dict[str, int]) -> float:
    total = sum(method_counts.values())
    if total <= 0:
        return 0.0
    probs = [count / total for count in method_counts.values() if count > 0]
    return -sum(p * math.log(p, 2) for p in probs)


def select_methods(candidate_methods: list[str], history: list[dict[str, Any]], uncertainty: float, k: int = 1) -> dict[str, Any]:
    usage = Counter(item.get("method") for item in history if item.get("method"))
    failures = Counter(item.get("method") for item in history if item.get("valid") is False)
    scores = {}
    for method in candidate_methods:
        score = 1.0 / (1 + failures[method]) + uncertainty / (1 + usage[method])
        scores[method] = score
    selected = sorted(candidate_methods, key=lambda m: scores[m], reverse=True)[:k]
    entropy = method_entropy({m: usage[m] + 1 for m in candidate_methods})
    return {"selected_methods": selected, "scores": scores, "method_entropy": entropy}

