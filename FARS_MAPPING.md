# FARS Mapping

SoloDeck v3 maps FARS-style research agents into a verifiable KG-DAG-CI runtime.

```text
IdeationAgent
-> uses Knowledge Graph, schema profiles, memory and prior failures
-> produces candidate hypotheses

PlanningAgent
-> turns hypotheses into tool routes and executable workflows
-> uses route_decision, plan_candidates and selected_plan

ExperimentAgent
-> executes Python Skills for metrics, causal readiness, DID, regression and bootstrap CI
-> records artifacts and warnings

WritingAgent
-> generates final user artifacts only after validation
-> includes limitations, confidence and next actions
```

Mapping to SoloDeck:

- KG supports Ideation.
- Candidate DAG supports Planning and causal hypotheses.
- Bootstrap CI, DID and regression support Experiment validation.
- ReportSkill and User Artifact View support Writing.

The KG is never treated as causal truth. It provides context, constraints and provenance. Causal claims must pass readiness, statistical and privacy checks, or they are downgraded to exploratory hypotheses or validation plans.

