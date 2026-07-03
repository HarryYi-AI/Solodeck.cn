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

## 13. What kind of RAG does SoloDeck use?

SoloDeck uses **Data-Agent Retrieval**, not generic document RAG. v4 retrieves structured evidence from schema memory, KG edges, prior artifacts, session turns, and optional text feedback chunks (`solodeck_v4/retrieval/`). Retrieval is intent-routed (schema / metric / relationship / causal / previous-result / text-feedback) and packed into an evidence object with scores and provenance.

## 14. Why is it not traditional document RAG?

Creator analytics questions need **typed, verifiable evidence** (columns, CI reports, DAG edges, validation artifacts), not arbitrary PDF chunks. Traditional RAG cannot guarantee metric lineage or causal readiness. SoloDeck retrieval feeds Python Skills and validators instead of letting an LLM answer from unstructured passages alone.

## 15. What is the difference between graph retrieval, artifact retrieval, and text retrieval?

- **Graph retrieval** (`kg_retriever.py`): 1–2 hop neighbors from `kg_edges.json` with relations like `may_confound`, `may_affect`, `derived_from`, `generated_by`.
- **Artifact retrieval** (`artifact_retriever.py`): prior analysis outputs, bootstrap CI, causal readiness, validation reports, and action cards ranked by task type, variable match, and recency.
- **Text retrieval** (`text_retriever.py`): BM25-like keyword search over user feedback chunks; optional sentence-transformers embeddings if installed.

## 16. What is currently implemented and what is future work?

**Implemented:** intent router, five memory stores under `data/memory/`, BM25 text retrieval with embedding fallback, KG multi-hop retrieval, artifact/session ranking, evidence pack + citation validator, developer trace retrieval panel.

**Future work:** live sync from v3 JSONL memory writers into `data/memory/`, dense vector index service, cross-session artifact deduplication, retrieval-aware SkillOpt-style skill documents ([SkillOpt](https://github.com/microsoft/SkillOpt)), and automatic write-back of retrieval logs for offline skill optimization.

