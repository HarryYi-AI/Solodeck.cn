from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class StepReward:
    step: str
    agent: str
    reward: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


REWARD_RULES = {
    "valid_artifact": 1,
    "correct_method_routing": 1,
    "correct_causal_warning": 1,
    "successful_repair": 1,
    "missing_required_field": -1,
    "invalid_causal_overclaim": -2,
    "ignored_critic_warning": -2,
    "unvalidated_numeric_claim": -2,
    "privacy_leakage": -3,
}

