# SoloDeckBench-lite

Run:

```bash
python -m solodeck_v3.bench.benchmark_runner
```

Synthetic tasks:

- 10 schema grounding tasks
- 5 KG construction tasks
- 5 causal validity tasks
- 5 statistical uncertainty tasks
- 5 failure repair tasks

Metrics:

- task success rate
- artifact validity rate
- causal overclaim rate
- statistical warning recall
- repair success rate
- average latency
- average cost
- agent reward variance
- improvement after memory update

