from __future__ import annotations

from collections import defaultdict


def normalize_agent_rewards(step_rewards: dict) -> dict:
    by_role = defaultdict(list)
    for item in step_rewards.get("steps", []):
        by_role[item.get("role", "Unknown")].append(float(item.get("reward", 0)))
    normalized = {}
    for role, values in by_role.items():
        mean = sum(values) / max(1, len(values))
        spread = max(values) - min(values) if len(values) > 1 else 1.0
        normalized[role] = {
            "raw_mean": round(mean, 3),
            "normalized": round(mean / max(1.0, abs(spread)), 3),
            "steps": len(values),
        }
    return normalized

