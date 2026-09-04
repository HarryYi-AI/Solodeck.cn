# SoloDeck Interview Guide

## 30-second version

SoloDeck is an evidence-driven Data Agent for creators and one-person companies. It
compiles natural-language goals into a typed TaskSpec, selects a low-cost or deep
analysis route, retrieves only relevant schema, graph, artifact and session evidence,
and executes deterministic Python Skills. A Structured Critic validates statistics,
causal wording, privacy and action safety. Failed runs enter a bounded repair loop;
successful and failed trajectories update memory and future plan utility.

## Three-minute version

1. **Problem**: dashboards tell users what happened, but creators need to know what
   to do next and whether a strategy difference is trustworthy.
2. **Task compilation**: L1 exact rules, L2 vector retrieval and L3 guarded LLM JSON
   turn a user question into TaskSpec. L3 only handles low-confidence ambiguity.
3. **Planning**: the Planner combines task type, risk, cost and historical plan
   utility. It uses a UCB-style exploration bonus instead of always picking plan 0.
4. **Execution**: registered Python Skills perform schema mapping, data quality,
   descriptive comparison, KG construction, causal readiness, bootstrap, regression,
   IPTW/DID and report assembly. LLMs do not calculate metrics.
5. **Verification**: the Critic checks nine dimensions. Numeric claims must bind to
   Python/SQL artifacts; confidence intervals crossing zero cannot produce scale-up
   advice; privacy violations block output.
6. **Repair and memory**: typed failures trigger at most two alternate-plan retries.
   Trace, evaluation, failure and plan-utility memories support later retrieval.
7. **Evaluation**: tests cover routing, tools, Claim grounding, Critic decisions,
   safety, latency/cost and synthetic causal tasks.

## Questions and answers

### Why not send every request to an LLM planner?

It is expensive, non-deterministic and difficult to audit. High-frequency requests
use deterministic rules, implicit expressions use vector retrieval, and only the
uncertain tail reaches a schema-constrained LLM.

### Is this really Multi-Agent?

The current product is better described as a Data Agent workflow. Planner, Executor,
Critic and Writer are role boundaries over shared state. Calling them independent
agents would be misleading until they have independent goals and dynamic delegation.

### What makes it agentic rather than a pipeline?

It keeps durable state, chooses tools from task/risk/memory, observes tool results,
verifies completion, conditionally repairs, stops under explicit budgets and updates
future policy memory. The path is conditional rather than a fixed one-shot chain.

### How is Memory implemented?

Session turns, compressed context and artifact cache serve the conversation. SQLite
UnifiedMemory stores evaluation, failure and skill utility with project/session scope,
version, lineage, retention and quality. Retrieval is intent-aware; summaries are
context, not evidence.

### Is DAPO used?

Not as token-level RL. SoloDeck borrows dynamic trajectory sampling and asymmetric
clipping for workflow utility updates. There is no policy-model log-probability ratio,
gradient update or online LLM fine-tuning, so the accurate term is DAPO-inspired
runtime policy optimization.

### How do you prevent hallucinated analysis?

The LLM never owns numeric estimation. Skills create versioned artifacts, Claim
Ledger binds visible claims to artifacts, and governance rejects unsupported numbers,
overstated causal language and unsafe actions.

### What would you build next?

Calibrate router confidence on a labeled held-out set, add a reranker for retrieval,
enforce hard timeouts in isolated workers, connect accepted Skill patches through a
human approval workflow, and expose OpenTelemetry spans for production monitoring.
