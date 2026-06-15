# SoloDeck v3 System Design

SoloDeck v3 is a verifiable self-evolving runtime for data-centric agents. It is not a BI dashboard. It compiles open-ended data tasks into typed task specs, executes structured skills through a LangGraph workflow, validates intermediate artifacts, assigns process rewards, and updates memory after failures.

Core workflow:

```text
CompileTask
-> LoadOrBuildMemory
-> BuildKGContext
-> GenerateHypothesisTree
-> GenerateCandidatePlans
-> RouteAndScheduleSkills
-> ExecuteSkills
-> ValidateArtifacts
-> AssignProcessRewards
-> ReflectOrRepair
-> GenerateFinalReport
-> UpdateMemory
```

If validation fails and revision budget remains, the workflow routes to `RepairPlan`, then re-executes selected skills.

Design principles:

- All numerical analysis is computed in Python.
- KG is graph-structured memory and constraint context, not causal truth.
- Causal discovery is exploratory hypothesis generation.
- Final user-facing claims must pass artifact, statistical, causal, privacy and trace checks.
- Developer trace exposes lineage and rewards, not raw private data.

