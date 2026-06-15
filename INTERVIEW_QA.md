# Interview QA

## 1. What is a Data Agent Runtime?

A runtime that converts open-ended data tasks into typed workflows, executes skills, validates artifacts, logs lineage, assigns rewards and updates memory.

## 2. Why LangGraph?

LangGraph gives explicit state, conditional routing, loop control and recoverable multi-step agent execution.

## 3. Where is the LangGraph workflow implemented?

`solodeck_v3/workflows/data_agent_graph.py`.

## 4. What is KG used for?

KG is used for context retrieval, candidate confounders, forbidden edge constraints, artifact lineage and explanation.

## 5. Is KG treated as causal truth?

No. KG is constraint and memory context only.

## 6. Which causal discovery algorithms are used?

Optional `causal-learn`, `LiNGAM`, `DAGMA`; fallback is rule-based candidate graph generation.

## 7. Why is causal discovery exploratory?

Observational data can contain confounding and selection bias. Discovery proposes hypotheses; it does not prove effects.

## 8. How does process reward work?

Each workflow step receives a reward based on final validation, causal safety, privacy, repair behavior and artifact completeness.

## 9. How does Agent RL appear in the system?

The system uses process rewards, agent-wise normalization and selected workflow memory as a lightweight self-improvement loop.

## 10. How does test-time evolution work?

For complex tasks, SoloDeck generates multiple candidate workflows, validates them, scores them by validity/cost/latency/reward and stores the best plan.

## 11. How does the system prevent unsupported causal claims?

Causal readiness, bootstrap CI, causal validators and repair nodes downgrade unsupported claims to validation plans.

## 12. How does it differ from a normal LLM agent or BI dashboard?

BI reports what happened. A normal LLM agent may answer directly. SoloDeck v3 creates verifiable workflows with traceable artifacts, validation, repair, rewards and memory updates.

