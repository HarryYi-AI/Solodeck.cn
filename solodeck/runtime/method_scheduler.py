from __future__ import annotations

import math
from collections import Counter
from typing import Any


def select_method(candidate_methods: list[str], skill_history: list[dict[str, Any]], uncertainty: float) -> dict[str, Any]:
    if not candidate_methods:
        return {"method": "none", "entropy": 0.0, "reason": "没有候选方法"}
    usage = Counter(item.get("method") for item in skill_history if item.get("method"))
    failures = Counter(item.get("method") for item in skill_history if item.get("valid") is False)
    scores = {}
    for method in candidate_methods:
        exploit = 1.0 / (1.0 + failures[method])
        exploration = uncertainty / (1.0 + usage[method])
        scores[method] = exploit + exploration
    selected = max(scores, key=scores.get)
    total = sum(usage[m] + 1 for m in candidate_methods)
    probs = [(usage[m] + 1) / total for m in candidate_methods]
    entropy = -sum(p * math.log(p, 2) for p in probs)
    return {"method": selected, "entropy": entropy, "scores": scores, "reason": "不只选择历史最高频方法；不确定性越高越鼓励探索。"}

