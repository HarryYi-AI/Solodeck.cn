# SoloDeck Langfuse 可观测性

SoloDeck 同时保留两套互补追踪：

- 本地 `trace`、`tool_audit`、checkpoint：用于业务回放和可验证计算，不依赖外部服务。
- Langfuse：用于跨请求查看 Agent 路径、Skill 耗时、模型调用、错误和质量分数。

Langfuse 不参与路由、统计计算或因果判断。即使 SDK 不存在、服务不可达或未配置密钥，SoloDeck 仍会继续运行。

## 观测层级

```text
solodeck-v4-agent                         Trace
├── tool:retrieve_memory                  Span
├── tool:compile_task                     Span
├── tool:plan_steps                       Span
├── tool:execute_analysis                 Span
├── llm:basic / llm:advanced              Generation
├── tool:validate_artifacts               Span
└── tool:compose_response                 Span
    ├── critic_quality                    Score
    ├── claim_governance_pass             Score
    └── process_reward                    Score
```

正式 `run_industrial_graph()` 路径会直接把每个 LangGraph Node 包装成 Langfuse Chain Span，因此无需为了追踪额外安装完整的 LangChain。若运行环境本身装有 LangChain，也会附加官方 CallbackHandler。

## 配置

安装依赖：

```bash
cd /workspace/ylj/harry_main/heikesong
/workspace/ylj/miniconda3/envs/py310/bin/pip install -r solo_creator_agent/requirements.txt
```

在项目根目录 `.env` 中加入：

```dotenv
SOLODECK_LANGFUSE_ENABLED=true
SOLODECK_LANGFUSE_CAPTURE_CONTENT=false
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=production
LANGFUSE_TRACING_RELEASE=solodeck-v4
```

若使用 Langfuse US、Japan 或自托管实例，把 `LANGFUSE_BASE_URL` 改为对应地址。修改环境变量后重启 FastAPI 服务。

验证：

```bash
curl https://solodeck.cn/api/v4/observability
```

当响应中的 `enabled`、`configured` 和 `sdk_installed` 都为 `true`，发送一次“对话分析”请求后即可在 Langfuse 的 Traces 页面查看链路。

## 隐私边界

默认 `SOLODECK_LANGFUSE_CAPTURE_CONTENT=false`：

- 不上传 CSV/Excel 行数据。
- 不上传用户原始问题和模型回复正文，只记录长度与摘要哈希。
- 数据集只记录行数、列数和字段集合哈希。
- Tool 只记录参数名、状态、耗时、成本和错误类别。
- 不记录 API Key、访问令牌或上传文件内容。

只有在脱敏测试环境确实需要调试 Prompt 时，才临时开启 `SOLODECK_LANGFUSE_CAPTURE_CONTENT=true`。生产环境建议保持关闭；若数据合规要求更高，使用自托管 Langfuse并配置数据保留策略。

## 代码入口

- `solodeck_v4/observability/langfuse.py`：可选 SDK 适配与脱敏策略。
- `solodeck_v4/runtime/runner.py`：Agent 根 Trace 与质量 Score。
- `solodeck_v4/tools/contracts.py`：Tool Span。
- `solo_creator_agent/src/llm_agent.py`：模型 Generation、Token 用量和备用模型重试。
- `solodeck_v4/workflows/state_graph.py`：LangGraph CallbackHandler。
- `GET /api/v4/observability`：无密钥状态检查。
