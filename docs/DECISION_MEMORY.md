# Decision Memory

SoloDeck Decision Memory is a project-scoped, hierarchical, temporal memory layer for analytical decisions. It stores historical context and outcomes while leaving current-value computation to the live-data layer.

## Lifecycle

```text
verified analysis artifact
-> DecisionEpisode
-> DecisionFact
-> observed outcome
-> StrategyEvidence
-> periodic consolidation
-> CreatorProfile / BusinessRegime / StrategySkillCandidate
```

An analysis without an actionable decision is not written as a long-term episode. A decision without an observed outcome remains an episode but does not become Strategy Evidence.

## Query path

`MemoryQueryPlan` determines which historical sources are useful and which fields still require live queries. For example, “为什么最近收藏率下降？” requests:

- active business regime
- similar historical episodes
- prior strategy evidence and failures
- recent and previous save rate from live data
- topic mix, format mix, posting frequency and platform segmentation from live data

`DecisionMemoryContext` is supplied to the analysis runtime as evidence. It is not returned as the final business answer without fresh analysis.

## Retrieval score

```text
0.35 * semantic similarity
+ 0.30 * context match
+ 0.15 * recency
+ 0.20 * outcome relevance
```

Context match evaluates platform, topic, account stage, content format and metric. The default semantic component is deterministic lexical similarity. An embedding function can be injected, but exact filters remain authoritative.

## Temporal resolution

Business regimes carry `valid_from`, `valid_to` and `status`. Activating a new regime in the same scope changes the prior active regime to `historical`; history is never overwritten.

Consolidation compares older and newer Strategy Evidence within each scope. A change in the best observed strategy is returned as a drift candidate, not activated automatically.

## Causal safety

Evidence levels are ordered as:

```text
observational < adjusted < experimental
```

Observational repetition can produce a strategy candidate. Causal wording requires experimental evidence, or adjusted evidence with confounder checks. Promotion into the executable Skill library additionally requires verifier approval, human approval and at least three supporting records.

## Storage

`SQLiteDecisionMemoryStore` implements the storage contract and uses six normalized tables with JSON payload columns:

- `decision_episodes`
- `decision_facts`
- `business_regimes`
- `creator_profiles`
- `strategy_evidence`
- `strategy_skill_candidates`

Project ID is mandatory on every table. In the web application it is derived from the authenticated workspace on the server.

## Integration API

Python:

```python
service.record_decision(...)
service.get_decision_context(...)
service.record_outcome(...)
service.run_consolidation(...)
```

HTTP:

```text
GET  /api/v4/decision-memory/context
POST /api/v4/decision-memory/outcomes
POST /api/v4/decision-memory/consolidate
```

The runtime calls `record_decision` only after report verification and calls `get_decision_context` through the retrieval tool. Consolidation and outcome collection remain explicit operations.
