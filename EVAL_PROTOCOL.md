# SoloDeck Evaluation Protocol

## Objective

Measure whether the agent selects an executable method, obtains the correct result, handles causal uncertainty and produces a numerically consistent report. The first-stage benchmark prioritizes reproducibility over scale.

## Task set

The default run contains 60 deterministic tasks with seed `20260904`:

| Source | Count | Purpose |
|---|---:|---|
| InfiAgent-DABench-compatible local tasks | 20 | Grouping, aggregation and business-table questions |
| DS-1000 Pandas/NumPy-compatible local tasks | 20 | Scalar array and DataFrame operations |
| SoloDeck synthetic SCM | 20 | `Z -> T`, `Z -> Y`, `T -> Y` with saved true ATE |

The first two groups are **local compatibility subsets**, not claims of completing the official benchmark suites. Official datasets can later be connected through the same `BenchmarkCase` adapter.

Official-data loaders are provided in `solodeck_eval/external_adapters.py`. They preserve the original records and tests rather than silently converting local examples into official scores. DS-1000 data follows the official `xlangai/DS-1000` JSONL format; InfiAgent-DABench records can be loaded from a downloaded JSON/JSONL export.

## Baselines

1. `A_direct_llm`: offline deterministic proxy with no tool calls. It validates the harness only and is not reported as real LLM performance.
2. `B_react_tools`: route one tool at a time and allow one fallback.
3. `C_plan_tools`: determine the tool before execution.
4. `D_solodeck_current`: current router + executor + verifier evaluation path.

External model evaluation is intentionally disabled in the reproducible default run. When a real model is added, record model/version, prompt, temperature, token usage, pricing snapshot and failure policy.

## Verifiers

- Python snippets are parsed, compiled and executed in a restricted benchmark namespace.
- SQL is executed against an isolated in-memory SQLite database.
- Numeric answers use explicit absolute and relative tolerances.
- DataFrame outputs are compared after deterministic sorting.
- Report numbers must match known artifact values.
- Causal estimates are compared with SCM true ATE and optionally confidence-interval coverage.

## Metrics

- Success rate
- Average tool calls
- Execution error rate
- Average latency
- Measured token usage and token cost

Unmeasured tokens are reported as `0` with an explicit disclosure, not estimated.

## Reproduction

```bash
/workspace/ylj/miniconda3/envs/py310/bin/python -m solodeck_eval.benchmark_runner --limit 60
/workspace/ylj/miniconda3/envs/py310/bin/python -m pytest -q
```

Outputs are written to `artifacts/eval/benchmark_results.json`, `baseline_results.md` and `demo_trajectory.jsonl`.
