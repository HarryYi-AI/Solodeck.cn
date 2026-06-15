# Agent RL Lite Module

SoloDeck v3 does not train a large model online. It uses lightweight process rewards:

- valid artifact: positive reward
- correct method routing: positive reward
- correct causal warning: positive reward
- successful repair: positive reward
- missing fields, causal overclaim, ignored critic warnings and privacy leakage: negative reward

Rewards are normalized by agent role to avoid unstable assignment.

