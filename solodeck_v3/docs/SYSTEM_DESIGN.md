# SoloDeck v3 System Design

SoloDeck v3 is a verifiable self-evolving runtime for data-centric agents.

Runtime:

```text
CompileTask -> LoadMemory -> BuildOrRetrieveKG -> RouteTools -> PlanWorkflow
-> ExecuteSkills -> ValidateArtifacts -> AssignRewards -> Reflect
-> RepairOrExplore or GenerateFinalArtifact -> UpdateMemory
```

The runtime separates user-facing artifacts from developer trace. Numerical analysis is executed by Python Skills. LLMs may assist text interpretation and writing, but they do not fabricate numerical results.

