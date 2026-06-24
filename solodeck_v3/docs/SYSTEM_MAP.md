# SoloDeck v3 — System Map

Full architecture with evaluation layers, workbench surfaces, and optional voice I/O.

## 1. 端到端主链路

```mermaid
flowchart TD
  subgraph ingest [数据接入层]
    U[用户上传 CSV/Excel/文本] --> P[SchemaSkill / DataMapping]
    P --> D[标准 schema DataFrame]
  end

  subgraph compile [Task Compiler]
    D --> TC[compile_user_goal]
    TC --> TS[TaskSpec: type / treatment / outcome / budget]
  end

  subgraph memory [Memory 层]
    M1[dataset_memory]
    M2[schema_memory]
    M3[graph_memory]
    M4[trace_memory]
    M5[failure_memory]
    M6[skill_utility_memory]
  end

  subgraph kg [Knowledge Graph]
    KG[KGConstructionSkill / kg_builder]
    CG[causal_graph_store / constraints]
  end

  subgraph orchestration [LangGraph Workflow]
    N1[CompileTask] --> N2[LoadMemory]
    N2 --> N3[BuildOrRetrieveKG]
    N3 --> N4[GenerateHypothesisTree]
    N4 --> N5[RouteTools]
    N5 --> N6[PlanWorkflow]
    N6 --> N7[ExecuteSkills]
    N7 --> N8[ValidateArtifacts]
    N8 --> N9[AssignProcessRewards]
    N9 --> N10[Reflect]
    N10 -->|needs_repair| N11[RepairOrExplore]
    N11 --> N5
    N10 -->|ok| N12[GenerateFinalArtifact]
    N12 --> N13[UpdateMemory]
  end

  subgraph agents [多 Agent 角色]
    A1[PlannerAgent]
    A2[RetrieverAgent]
    A3[CausalAnalystAgent]
    A4[ExecutorAgent]
    A5[VerifierAgent]
    A6[WriterAgent]
    A7[ExplorerAgent]
  end

  subgraph skills [Python Skills — 计算核心]
    S1[SchemaSkill]
    S2[DataQualitySkill]
    S3[KGConstructionSkill]
    S4[CausalReadinessSkill]
    S5[BootstrapSkill / RegressionSkill / DIDSkill]
    S6[ReportSkill]
  end

  subgraph verify [Verification + Process Reward]
    V1[artifact / statistical / causal / privacy / trace]
    V2[process_reward + agent_wise_normalization]
  end

  subgraph eval [分层评估 — 新增]
    E1[L1 FARS domain]
    E2[L2 RAGAS-shaped retrieval]
    E3[L3 G-Eval-shaped writer]
    E4[L4 Workbench harness]
  end

  subgraph out [输出]
    O1[user_artifact / action_cards]
    O2[developer_trace]
    O3[SPA 前端]
  end

  U --> TC
  TS --> N1
  memory --> N2
  KG --> N3
  agents -.-> orchestration
  skills --> N7
  N8 --> verify
  N13 --> memory
  N12 --> eval
  eval --> out
  N12 --> O1
  N12 --> O2
  O1 --> O3
```

## 2. 分层评估路由（与 LAYERED_EVALUATION.md 一致）

```mermaid
flowchart TD
  Task[用户问题] --> Router{任务类型 + 产物}
  Router -->|始终| FARS[L1: FARS / verification]
  Router -->|KG / ideation| RAGAS[L2: RAGAS 形四指标]
  Router -->|有行动卡片| GEval[L3: G-Eval 形 rubric]
  Router -->|完整 trace| WB[L4: Workbench 五结果]
  FARS --> Sum[all_valid + summary]
  RAGAS --> Sum
  GEval --> Sum
  WB --> Sum
```

## 3. Voyager 技能库（课程 10）— 适配层

```mermaid
flowchart LR
  Q[任务描述] --> SL[SoloDeckSkillLibrary.search]
  SL --> TO[topo_order 依赖排序]
  TO --> EX[execute_skill_sequence — 原有运行时]
  EX --> SU[skill_utility_memory 写入]
  FAIL[Skill 失败] --> RF[refine_from_failure 版本+1]
```

实现：`solodeck_v3/runtime/skill_library.py`（**不修改** `skill_runtime.py` 行为）

## 4. 语音网关（课程 22）— 可选 I/O

```mermaid
flowchart LR
  MIC[Mic 16kHz] --> VAD[VAD]
  VAD --> STT[STT]
  STT --> EL[entity_linker 会话实体]
  EL --> TOOL[SoloDeckToolProcessor]
  TOOL --> V3[run_v3_data_agent]
  V3 --> TTS[TTS 读行动卡片摘要]
  TTS --> SPK[Transport / 扬声器]
  BARGE[Barge-in cancel] -.->|UPSTREAM| TTS
  BARGE -.-> TOOL
```

实现：`solodeck_v3/voice/gateway.py`（**不修改** LangGraph 主图）

## 5. Agent Workbench 七接触面（课程 41 / 42）

```mermaid
flowchart TD
  Pack[agent-workbench-pack/] --> AG[AGENTS.md]
  Pack --> SC[schemas/]
  Pack --> DOC[docs/ rules + rubric + handoff]
  Pack --> SCR[scripts/ init verify handoff]
  Pack --> BIN[bin/install.sh]
  BIN --> Repo[heikesong 仓库]
  Repo --> Surfaces[与 solodeck_v3 运行时对齐]
```

## 6. 模块索引

| 路径 | 职责 |
|---|---|
| `solodeck_v3/compiler/` | TaskSpec 编译 |
| `solodeck_v3/router/` | 工具路由与预算 |
| `solodeck_v3/memory/` | 六类经营记忆 |
| `solodeck_v3/graph/` | KG + 因果约束 |
| `solodeck_v3/workflows/data_agent_graph.py` | LangGraph 主图 |
| `solodeck_v3/skills/` | 可验证 Python 计算 |
| `solodeck_v3/verification/` | 领域校验关卡 |
| `solodeck_v3/reward/` | Process reward |
| `solodeck_v3/bench/` | FARS + **layered_eval** |
| `solodeck_v3/runtime/skill_library.py` | Voyager 适配 |
| `solodeck_v3/nlp/entity_linker.py` | 业务实体链接（可选） |
| `solodeck_v3/voice/` | 语音流水线桩 |
| `agent-workbench-pack/` | 可安装工作台包 |
| `solo_creator_agent/api_spa.py` | FastAPI + SPA |

## 7. 课程对照 — 对本项目的帮助

| 课程 | 采纳方式 | 侵入性 |
|---|---|---|
| [41 真实仓库工作台](https://aieng-zh.cn/lessons/14-agent-engineering/41-workbench-for-real-repos/) | L4 五结果 + `agent-workbench-pack/` | 低：独立目录 |
| [10 Voyager 技能库](https://aieng-zh.cn/lessons/14-agent-engineering/10-skill-libraries-voyager/) | `skill_library.py` 包装现有 Skill | 低：不改编排 |
| [22 语音 Pipecat/LiveKit](https://aieng-zh.cn/lessons/14-agent-engineering/22-voice-agents-pipecat-livekit/) | `voice/gateway.py` 帧流水线 | 低：可选 API |
| [42 工作台包 capstone](https://aieng-zh.cn/lessons/14-agent-engineering/42-agent-workbench-capstone/) | `agent-workbench-pack/` 安装器 | 低：复制即用 |
