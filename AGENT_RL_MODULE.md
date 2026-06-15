# Agent RL Lite Module

SoloDeck v3 implements a lightweight process-reward mechanism inspired by test-time evolution and process reward modeling.

Trajectory:

```text
Planner -> Retriever -> Executor -> Critic -> Repair -> Report -> Memory
```

Reward signals:

- valid artifact: positive reward
- unsupported causal claim detected: positive critic reward
- correct method routing: positive planner reward
- missing required artifact: negative reward
- invalid causal overclaim: strong negative reward
- unvalidated report: negative report reward
- privacy block: strong negative reward

Agent-wise normalization prevents one role from dominating the update:

```text
Planner reward
Retriever reward
Executor reward
Critic reward
Repair reward
Report reward
```

Selected plans are stored in Skill Utility Memory as pseudo-labels for future routing.

