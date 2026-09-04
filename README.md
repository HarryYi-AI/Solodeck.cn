# SoloDeck

**SoloDeck is a stateful and verifiable Data Agent that grounds natural-language analytical goals to heterogeneous data, compiles executable workflows, actively verifies intermediate results, and preserves analytical state across long-running interactions.**

中文：SoloDeck 是一个有状态、可验证的数据分析智能体运行时。它把自然语言目标映射到表、字段、实体和历史分析产物，执行真实的 Python/统计技能，并用证据血缘约束最终结论。

内容经营、收入和实验分析是当前产品场景；因果分析是高级 Skill Pack，而不是系统的全部身份。完整重构说明见 [Stateful and Verifiable Runtime](docs/STATEFUL_VERIFIABLE_RUNTIME.md)。

<img width="1495" height="798" alt="image" src="https://github.com/user-attachments/assets/1092a0cb-7e6a-4f41-a9a3-9560e0cc4729" />
<img width="1419" height="931" alt="image" src="https://github.com/user-attachments/assets/1a0ecda6-09fa-4442-aecd-d6e5a1fd15f1" />
<img width="1529" height="920" alt="image" src="https://github.com/user-attachments/assets/ba179ed1-0c22-4571-a1d8-6dab9796b157" />
<img width="1493" height="534" alt="image" src="https://github.com/user-attachments/assets/8f6c8ac1-d855-4424-93b6-e050ee360511" />

## Why SoloDeck

Most analytics tools answer:

> What happened in the data?

SoloDeck focuses on:

> What should I do next, where should I do it, and how can I verify it?

Creators and solo businesses often have useful data scattered across platform dashboards, spreadsheets, payment screenshots, feedback notes, and campaign records. SoloDeck helps them move from fragmented data to concrete operating decisions.

## Verifiable Data Analysis Agent Runtime

SoloDeck has evolved from a dashboard-style prototype into a verifiable data analysis Agent runtime:

```text
User data
-> typed task compiler
-> memory and knowledge graph context
-> hypothesis tree
-> method planner
-> executable Python skills
-> artifact/statistical/causal/privacy validation
-> repair loop
-> process reward
-> user-facing action cards
```

The default user interface remains simple: upload data, see diagnosis, check whether a decision is reliable, and read three next actions. The technical layer is available in the developer trace panel for review, but it is not exposed as raw JSON to users.

Research ideas used in the runtime:

- DataMind / Scaling Generalist Data-Analytic Agents: task taxonomy, easy-to-hard data-agent workflows, stable code-based multi-turn rollout.
- JanusCoder: visual-programmatic traceability, so visual output remains tied to executable logic.
- Memory failure studies: explicit dataset, graph, trace, failure, and skill-utility memory to reduce stale or contradictory agent memory.
- Binary-matrix test-case evaluation: SoloDeckBench-lite treats failures as diagnostic patterns, not just pass/fail demos.
- Graph structure-semantic evolution: the knowledge graph is treated as evolving operating memory across content, product, feedback, and experiment domains.

References:

- https://arxiv.org/abs/2509.25084
- https://arxiv.org/abs/2510.23538
- https://arxiv.org/abs/2510.08720
- https://arxiv.org/abs/2602.10506
- https://sites.google.com/view/memagent-iclr26/schedule

## What It Solves

- Content creators know which posts performed well, but not whether the title, platform, topic, timing, or account size caused the difference.
- Solo businesses often miss receivables, invoices, campaign reports, and follow-up tasks.
- Small product teams need to know whether a new feature, product variant, or beta-test result is worth scaling.
- Users want actions, not a wall of dashboards.

SoloDeck turns uploaded materials into:

- short-term and long-term task lists
- weekly validation plans
- revenue and campaign risk alerts
- content and platform strategy suggestions
- product and feedback priorities
- downloadable operating reports

## Core Features

### 1. Multi-Source Data Intake

SoloDeck supports:

- CSV files
- screenshots
- manual text input
- content performance data
- revenue records
- campaign records
- product data
- user feedback
- beta-test records
- experiment records

It does not require WeChat APIs or real platform APIs, so it is easy to demo and practical for real-world use.

### 2. Action-First Workspace

The default screen is intentionally simple:

1. Choose platforms
2. Add materials
3. Read the next actions

Metrics, charts, and detailed analysis are folded by default. Users first see the most important actions instead of long tables.

### 3. Creator and Content Strategy

SoloDeck analyzes:

- title styles
- topics
- platforms
- publishing time
- content series
- content fatigue
- duplication risk
- commercial value per content

It suggests what to publish next and how to validate the strategy.

### 4. Revenue and Business Workflow

SoloDeck identifies:

- revenue mix
- platform revenue
- pending payments
- high-value clients
- sponsorship risks
- missing reports
- invoice/payment issues

It also supports pricing suggestions and brand report generation.

### 5. Product and Feedback Analysis

SoloDeck also works beyond self-media scenarios. It supports small e-commerce teams, robot products, knowledge products, and productized services.

It analyzes:

- product variants
- feature tags
- new vs old versions
- refunds
- ratings
- beta-test results
- feedback themes
- roadmap priorities

### 6. Causal-Aware Analysis

SoloDeck does not treat correlation as guaranteed causality.

It separates:

- correlation findings
- controlled lift estimates
- paired comparisons
- experiment results
- validation plans

The system can control for factors such as:

- account ID
- platform
- topic
- follower base
- production hours
- ad spend
- content type

Supported statistical ideas include:

- group mean comparison
- ATE estimation from treatment/control groups
- paired differences for same-content cross-platform analysis
- fixed-effect style controls
- propensity-score matching fallback
- inverse-probability weighting fallback
- bootstrap confidence intervals
- placebo-style refutation checks
- subsample stability checks

The output is cautious: if evidence is weak, SoloDeck recommends a small validation experiment instead of directly scaling the strategy.

### 7. Workflow Trace, Knowledge Base, and Feedback Learning

SoloDeck includes a lightweight workflow layer:

```text
Data intake -> Revenue analysis -> Strategy analysis -> Lift estimation -> Experiment planning -> Action generation
```

It also includes:

- a small operating knowledge base for content, e-commerce, product tests, and campaign follow-up
- TF-IDF retrieval to explain why a recommendation is relevant
- preference feedback so users can mark recommendations as useful or not useful
- a lightweight bandit-style ranking adjustment for future suggestions

## Demo Upload Pack

A ready-to-use demo pack is included:

```text
solo_creator_agent/demo_upload_pack/
```

It contains virtual screenshots and CSV files that can be uploaded during a live demo:

- operating dashboard screenshot
- pending payment screenshot
- feedback notes screenshot
- campaign tracker screenshot
- content CSV
- revenue CSV
- campaign CSV
- product CSV
- feedback CSV
- experiment CSV
- beta-test CSV

Zip file:

```text
solo_creator_agent/solodeck_demo_upload_pack.zip
```

Suggested demo flow:

1. Open SoloDeck.
2. Upload screenshots first to show that the product can work without platform APIs.
3. Paste a manual note, for example:

```text
Tomorrow at 9 AM I need to review robot campaign data with the client, but the report is not ready.
```

4. Upload CSV files to show full analysis.
5. Show "Next Actions", "What to Validate This Week", "How SoloDeck Reached These Actions", and the downloadable report.

## Project Structure

```text
.
├── solo_creator_agent/
│   ├── app.py
│   ├── requirements.txt
│   ├── src/
│   │   ├── agent_orchestrator.py
│   │   ├── auto_insights.py
│   │   ├── business_collab.py
│   │   ├── causal_estimator.py
│   │   ├── causal_experiment.py
│   │   ├── causal_refute.py
│   │   ├── data_loader.py
│   │   ├── knowledge_base.py
│   │   ├── llm_agent.py
│   │   ├── product_feedback.py
│   │   ├── recommendation_learning.py
│   │   ├── revenue_analysis.py
│   │   ├── strategy_analysis.py
│   │   ├── text_structured.py
│   │   ├── user_storage.py
│   │   └── workflow_engine.py
│   ├── data/
│   ├── demo_upload_pack/
│   ├── scripts/
│   ├── deploy/
│   ├── Dockerfile
│   └── docker-compose.yml
├── package.json
└── README.md
```

## Quick Start

```bash
cd solo_creator_agent
conda env create -f environment.yml
conda activate solodeck-py310
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

If you already have a compatible Python environment, install the same dependencies with:

```bash
pip install -r requirements.txt
```

Open:

```text
http://localhost:8501
```

For a remote server:

```bash
ssh -L 8501:localhost:8501 username@server_ip
```

Then open:

```text
http://localhost:8501
```

## Environment Variables

Create `.env` in the repository root or configure environment variables directly:

```env
OPENAI_BASE_URL=https://aiping.cn/api/v1
OPENAI_API_KEY_BASIC=your-basic-model-key
OPENAI_MODEL_BASIC=Qwen3.5-Plus
OPENAI_API_KEY_ADVANCED=your-advanced-model-key
OPENAI_MODEL_ADVANCED=GLM-5-Turbo

SOLODECK_ACCESS_CODE=your-demo-code
SOLODECK_REQUIRE_LOGIN=false
CREATOR_ALIPAY_ACCOUNT=your-payment-account
```

The app can run with mock/demo data without an LLM key. LLM keys enable screenshot/text extraction and more polished natural-language advice.

Security note:

- Do not commit `.env` to GitHub.
- Keep real API keys, access codes, and payment accounts in environment variables.
- This repository only includes placeholders and `.env.example` style configuration.
- If a key is accidentally committed, revoke it immediately and generate a new one.

## Generate Demo Data

```bash
cd solo_creator_agent
python scripts/generate_demo_upload_pack.py
```

This regenerates:

```text
demo_upload_pack/
solodeck_demo_upload_pack.zip
```

## Public Demo Script

```bash
cd solo_creator_agent
bash scripts/run_public_demo.sh
```

For production-like deployment:

```bash
cd solo_creator_agent
bash scripts/deploy_docker.sh
```

Nginx and systemd examples are in:

```text
solo_creator_agent/deploy/
```

## Agent, KG and Causal Workflow

The current SPA calls real Python Skills through FastAPI. The main endpoint for the full agent loop is:

```text
POST /api/full-agent
```

It returns:

- `kg`: a lightweight knowledge graph built from content, platform, topic, title style, account, series, feedback keywords and revenue/conversion signals
- `dag`: a candidate causal graph for hypothesis generation
- `decision.effect`: ATE-style estimate, adjusted effect, CATE segments, IPTW fallback when feasible, and Bootstrap 95% confidence interval
- `action_cards`: three action cards for continue, reduce/pause, or validate next week
- `audit`: step-by-step audit trail without exposing raw uploaded rows

### Knowledge Graph

`solo_creator_agent/src/knowledge_graph.py` builds graph entities and relations:

```text
Content -> Platform
Content -> Topic
Content -> Title Style
Content -> Series
Content -> Text Feature
Feedback Text -> Keyword Entity
```

The KG is used for explanation and constraints. It does not by itself claim causality.

### Candidate DAG

`solo_creator_agent/src/causal_discovery.py` generates candidate DAG edges. It tries optional libraries first:

```text
causal-learn PC
LiNGAM
```

If those packages are not installed, SoloDeck uses a deterministic fallback:

```text
correlation screening + business time order + KG constraints
```

This creates a candidate DAG for low-cost validation planning, not a final proof.

### Bootstrap Confidence Interval

`EffectEstimationSkill` repeatedly resamples treatment and control groups, then recomputes the mean difference. The 2.5% and 97.5% quantiles become the 95% interval.

Plain-English reading:

```text
If the interval crosses 0, the result is not stable enough to scale.
If most or all of the interval is above 0, the strategy is more likely positive.
If the interval is below 0, pause or redesign the strategy.
```

### LangGraph Workflow

`solo_creator_agent/src/agent_workflow.py` is LangGraph-compatible. When `langgraph` is installed, it compiles and runs a `StateGraph`. When it is not installed, the same named nodes run through a deterministic fallback executor.

```text
DataIngestion
  -> KnowledgeGraph
  -> CausalDiscovery
  -> DecisionQuestion
  -> EffectEstimation
  -> Reflection
  -> Evaluation
  -> ActionPlan
```

Reflection and Evaluation decide whether a result can be scaled or should loop into low-cost validation because the confidence interval is unstable.

## SoloDeck v2: Self-Evolving Data Agent Runtime

The v2 runtime lives in the top-level `solodeck/` package. It turns SoloDeck from a single decision-support app into a multi-agent data runtime:

```text
Document
  -> NER / text chunking
  -> Relation Extraction
  -> Knowledge Graph
  -> Causal Discovery
  -> Candidate Causal Graph
  -> GraphRAG-style evidence retrieval
  -> Strategy Agent
```

Implemented modules:

```text
solodeck/compiler/task_compiler.py
solodeck/planning/hypothesis_tree.py
solodeck/runtime/budget_controller.py
solodeck/runtime/skill_runtime.py
solodeck/runtime/method_scheduler.py
solodeck/runtime/model_router.py
solodeck/verification/validators.py
solodeck/evolution/process_reward.py
solodeck/evolution/test_time_evolution.py
solodeck/memory/trace_memory.py
solodeck/workflows/data_agent_graph.py
```

The v2 API endpoint is:

```text
POST /api/v2-agent
```

It returns task spec, hypothesis tree, dynamic reasoning budget, selected plan, validation result, process rewards, memory update and developer-safe trace.

LangGraph is used when installed. The current development environment installs `langgraph>=0.2`; if unavailable in a lighter deployment, the same node functions can run through the deterministic fallback executor.

Run the benchmark:

```bash
python solodeck_bench/run_benchmark.py
```

Benchmark metrics include task success rate, artifact validity, causal overclaim rate, repair success rate, latency, reward and method entropy.

## Data Privacy and User Storage

SoloDeck includes a local account and workspace system:

- user uploads are stored by user ID
- imported records are stored per user
- task status is stored per user
- recommendation feedback is stored per user
- passwords are hashed with PBKDF2

The current version uses SQLite for easy demo and development. For commercial deployment, migrate storage to PostgreSQL or another managed database.

## Current Limitations

- Causal estimates are exploratory and should not be treated as definitive causal proof.
- Screenshot extraction depends on the configured vision-capable model.
- LangGraph is supported when installed; otherwise the same nodes run through the local fallback executor.
- RAG is currently a lightweight TF-IDF knowledge matching module, not a full vector database pipeline.
- Recommendation learning is a transparent bandit-style ranking adjustment, not a full reinforcement-learning system.

## Suggested GitHub Topics

```text
ai-agent
creator-economy
solo-business
causal-inference
streamlit
data-analysis
business-intelligence
ab-testing
productivity
```

## License

This project is prepared for hackathon and demo use. Add a license before public commercial distribution.
