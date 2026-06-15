from __future__ import annotations

from collections import defaultdict


def normalize_agent_rewards(process_rewards: dict) -> dict:
    by_agent = defaultdict(list)
    for item in process_rewards.get("steps", []):
        by_agent[item.get("agent") or item.get("role") or "Unknown"].append(float(item.get("reward", 0)))
    normalized = {}
    for agent, values in by_agent.items():
        mean = sum(values) / max(1, len(values))
        spread = max(values) - min(values) if len(values) > 1 else 1.0
        normalized[agent] = {
            "raw_mean": round(mean, 3),
            "normalized": round(mean / max(1.0, abs(spread)), 3),
            "steps": len(values),
        }
    return normalized

