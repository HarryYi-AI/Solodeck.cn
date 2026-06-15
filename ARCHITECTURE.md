# Architecture

Important packages:

```text
solodeck_v3/compiler       TaskSpec and task compiler
solodeck_v3/memory         dataset, graph, trace, failure and skill utility memory
solodeck_v3/graph          KG builder, constraint graph, causal graph store
solodeck_v3/planning       hypothesis tree and method planner
solodeck_v3/runtime        state, scheduler, skill runtime, budget, snapshots
solodeck_v3/skills         standalone executable Skills
solodeck_v3/verification   artifact, statistical, causal, privacy, trace, reward validators
solodeck_v3/evolution      process reward, repair, regression task generation, scheduler update
solodeck_v3/workflows      LangGraph StateGraph
solodeck_v3/bench          SoloDeckBench-lite
```

API:

```text
POST /api/v3-agent
```

Returns:

- `user_artifact`: validated final user view
- `developer_trace`: TaskSpec, selected workflow, skills, validation, rewards, memory updates
- `validation_report`
- `step_rewards` and `agent_rewards`

