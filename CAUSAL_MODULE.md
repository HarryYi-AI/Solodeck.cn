# Causal Module

SoloDeck v3 treats causal discovery as exploratory.

The causal pipeline:

```text
KG constraints
-> candidate confounder selection
-> optional causal discovery
-> fallback rule-based graph
-> causal readiness check
-> Bootstrap / regression / counterfactual validation
-> claim downgrade when unsupported
```

Optional discovery backends:

- `causal-learn`
- `lingam`
- `dagma`

Fallback:

- correlation screening
- business temporal order
- KG forbidden edge constraints

Rules:

- Never present discovered graph as final causal truth.
- If sample size is small, mark graph unstable.
- If CI crosses zero, recommend low-cost validation rather than scaling.
- Unsupported causal claims are downgraded by the critic/repair loop.

