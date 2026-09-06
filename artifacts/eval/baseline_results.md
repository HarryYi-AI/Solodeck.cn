# SoloDeck Baseline Results

任务数：60；固定随机种子：20260904。

> 说明：A 是不调用外部模型的 direct-LLM 离线代理，只用于验证评测管线；不能作为真实大模型能力结论。其余基线也在离线执行器上比较路由与工具策略。

| Baseline | Success rate | Avg tool calls | Execution error | Latency (ms) | Tokens | Token cost |
|---|---:|---:|---:|---:|---:|---:|
| A_direct_llm | 70.0% | 0.00 | 0.0% | 0.473 | 0 | 0.0000 |
| B_react_tools | 100.0% | 1.00 | 0.0% | 0.739 | 0 | 0.0000 |
| C_plan_tools | 100.0% | 1.00 | 0.0% | 0.669 | 0 | 0.0000 |
| D_solodeck_current | 100.0% | 1.00 | 0.0% | 12.130 | 0 | 0.0000 |

## Dataset composition

- `InfiAgent-DABench-compatible-local`: 20
- `DS-1000-Pandas-Numpy-compatible-local`: 20
- `SoloDeck-synthetic-SCM`: 20

## Interpretation

该结果证明评测、工具执行和自动校验链路可运行，不代表已完成 Agent RL 训练。
官方 InfiAgent-DABench 与 DS-1000 尚未整库导入；当前使用本地兼容任务验证接口，后续可通过适配器替换数据源。
