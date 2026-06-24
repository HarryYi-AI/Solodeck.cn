# AGENTS.md — SoloDeck v3

You are working in the SoloDeck creator analytics repository.

Read before acting:

1. `data/solodeck_v3_memory/` — persistent memory (dataset, schema, graph, trace, failure, utility).
2. `solodeck_v3/docs/SYSTEM_MAP.md` — architecture and evaluation layers.
3. `agent-workbench-pack/docs/agent-rules.md` — causal safety, scope, verification.
4. `solodeck_v3/docs/LAYERED_EVALUATION.md` — L1–L4 eval routing.

Primary runtime entry:

```bash
python -c "from solodeck_v3.workflows.data_agent_graph import run_v3_data_agent; ..."
```

Verification:

```bash
python agent-workbench-pack/scripts/verify_agent.py
python -m solodeck_v3.bench.layered_eval_runner
```

Pack version: 1.0.0
