# SoloDeck 面试版收敛审计

## 结论

主线统一为 `solodeck_runtime` 中的小型可验证 Data Agent。v3 的统计 Skill 和 v4 的会话 API 继续复用，不再增加新的版本目录。

## WORKING

- Task Compiler：`solodeck_runtime.models.TaskSpec` 与 `solodeck_v4.compiler.enhanced_compiler`
- 数据源操作：CSV、Excel、SQLite、TXT/Markdown 的 list / inspect / search / read
- Planner / Executor / Critic：`solodeck_runtime.data_agent.InterviewDataAgent`
- JIT Tool Loading：`solodeck_runtime.tools.DataToolRegistry`
- 结构化计算：pandas 受控分组与比率、只读 SQL
- 状态：`AnalysisState` 与 SQLite snapshot / restore / branch / diff
- Memory：working state、analytical state、episode、failure，SQLite 持久化
- Retrieval：Schema/Artifact/State 精确检索，文本 BM25
- Validator：字段、分母、空结果、多对多连接膨胀、工件一致性
- 高级 Skill：Bootstrap、回归、DID、因果就绪度与候选 DAG
- 前端：React SPA，上传、提问、结果、真实工具轨迹、历史运行

## PARTIAL

- Planner 的常见分析意图以确定性规则为主，复杂语义仍复用 v4 的可选 LLM 编译器。
- Excel 支持工作表检查与读取，但尚无公式依赖分析。
- Memory 使用词法相关性、时间衰减和质量分工程权重，尚未学习权重。
- Benchmark 已有离线兼容任务和 SCM 真值任务，尚未导入完整官方数据集。

## EXPERIMENTAL

- 因果发现、知识图谱、SkillOpt-lite、Process Reward。
- Langfuse、Neo4j、Embedding/FAISS 均为可选集成，不是主流程依赖。

## DEPRECATED

- Streamlit 旧界面仅保留兼容，不再作为产品入口。
- v3/v4 中重复的展示型 Agent 命名不再用于面试主叙事。
- “所有问题都先做因果推断”的旧路由已停用；普通比较直接执行描述性计算。

## 面试主线

```text
discover -> inspect -> search -> read
-> plan -> execute -> verify -> repair -> remember
```

因果分析是工具箱中的高级技能，不是 SoloDeck 的系统身份。
