# SoloDeck v4 Agent Architecture

## 1. One-line summary

SoloDeck v4 is a session-aware business analysis agent layered on top of SoloDeck v3:

- **v3** provides the analysis engine: schema mapping, knowledge graph, causal estimation, validation, rewards, and action cards.
- **v4** adds the conversation runtime: multi-turn session memory, task planning, tool orchestration, context compression, risk routing, and pre-output gating.

In short:

```text
v3 = one-shot verified analysis engine
v4 = conversational orchestration layer around v3
```

## 2. Presentation-ready architecture flow

```text
User Input
  ├─ Structured files: CSV / Excel / ZIP
  ├─ Unstructured input: screenshots / OCR / pasted text / chat follow-up
  └─ Voice transcript
        ↓
Data Understanding Layer
  ├─ Schema mapping
  ├─ Entity linking
  ├─ Text normalization
  ├─ Knowledge graph construction
  └─ Candidate causal graph generation
        ↓
Task Orchestration Layer (v4)
  ├─ Session store
  ├─ Enhanced task compiler
  ├─ Risk router
  ├─ Task planner
  ├─ Tool registry
  └─ Context compressor
        ↓
Execution Layer (v3 + Python Skills)
  ├─ Retrieve memory
  ├─ Compile task
  ├─ Plan steps
  ├─ Execute analysis
  │    ├─ bootstrap confidence interval
  │    ├─ fixed-effects adjustment
  │    ├─ stratified effect estimation
  │    ├─ ATE / relative lift
  │    ├─ knowledge graph summary
  │    └─ candidate DAG reasoning
  ├─ Validate artifacts
  └─ Compose response
        ↓
Verification & Safety Layer
  ├─ data quality checks
  ├─ causal readiness checks
  ├─ trace validation
  ├─ claim review
  ├─ privacy validation
  └─ post-writer gate
        ↓
Output Layer
  ├─ action cards
  ├─ business reply
  ├─ diagnosis summary
  ├─ decision check
  ├─ graph/causal digest
  └─ weekly report
```

## 3. Mermaid flowchart

```mermaid
flowchart LR
    A[User Input\nCSV / Excel / ZIP / Screenshot / Text / Voice] --> B[Schema Mapping]
    B --> C[Entity Linking]
    C --> D[Knowledge Graph]
    C --> E[Candidate Causal Graph]

    D --> F[Enhanced Task Compiler]
    E --> F
    A --> F

    F --> G[Risk Router]
    G --> H[Task Planner]
    H --> I[Tool Registry]

    I --> J[retrieve_memory]
    J --> K[compile_task]
    K --> L[plan_steps]
    L --> M[execute_analysis]
    M --> N[validate_artifacts]
    N --> O[compose_response]

    M --> P[Bootstrap CI]
    M --> Q[Fixed Effects / Stratified Estimation]
    M --> R[KG + DAG Summary]

    O --> S[PostWriter Gate]
    S --> T[Action Cards / Reply / Report]

    T --> U[Session Memory Update]
    U --> J
```

## 4. Mind-map version

```text
SoloDeck v4
├─ Input
│  ├─ CSV / Excel / ZIP
│  ├─ Screenshot / OCR
│  ├─ Pasted text
│  └─ Voice transcript
├─ Understanding
│  ├─ Schema mapping
│  ├─ Entity linking
│  ├─ Knowledge graph
│  └─ Candidate causal graph
├─ Orchestration
│  ├─ Session store
│  ├─ Task compiler
│  ├─ Risk router
│  ├─ Planner
│  ├─ Tool registry
│  └─ Context compression
├─ Analysis
│  ├─ ATE / relative lift
│  ├─ Bootstrap CI
│  ├─ Fixed effects
│  ├─ Stratified effects
│  ├─ KG summary
│  └─ DAG evidence
├─ Verification
│  ├─ Data quality
│  ├─ Causal readiness
│  ├─ Trace validation
│  ├─ Claim review
│  ├─ Privacy checks
│  └─ Post-writer gate
└─ Output
   ├─ Action cards
   ├─ Chat reply
   ├─ Decision check
   ├─ Diagnosis
   └─ Weekly report
```

## 5. What v4 adds over v3

### v3

- Strong at **single-run analysis**
- Builds:
  - KG
  - candidate causal structure
  - causal readiness
  - bootstrap intervals
  - fixed-effects adjustments
  - validation reports
  - action cards

### v4

- Strong at **interactive analysis**
- Adds:
  - multi-turn conversation
  - session-level memory
  - context carry-over
  - risk-based routing
  - tool-by-tool orchestration
  - pre-output gating
  - voice-turn wrapper

## 6. The 7 v4 tools

```text
1. retrieve_memory
2. compile_task
3. plan_steps
4. execute_analysis
5. validate_artifacts
6. compose_response
7. clarify
```

### Their role

- `retrieve_memory`: load prior turns, linked entities, cached artifacts
- `compile_task`: convert user question into a task spec
- `plan_steps`: decompose the question into executable steps
- `execute_analysis`: call v3 workflows / Python skills
- `validate_artifacts`: check whether the outputs are safe and usable
- `compose_response`: translate artifacts into user-facing answer + actions
- `clarify`: ask follow-up when ambiguity is too high

## 7. How LangGraph fits in

LangGraph is not the whole system; it is the **workflow controller** inside the orchestration layer.

It manages:

- step sequencing
- retries / reflection-friendly execution
- tool invocation order
- memory-aware task continuation

So the system is better described as:

```text
Session Runtime + Task Compiler + LangGraph Workflow + Python Skills + Validators
```

not just:

```text
an LLM with LangGraph
```

## 8. How to explain this in a talk

Use this script:

> SoloDeck v4 is a verified business analysis agent for creators and solo companies.  
> The bottom half is a deterministic analysis engine: schema mapping, knowledge graph construction, causal estimation, bootstrap confidence intervals, fixed-effects adjustment, and validation.  
> The top half is a conversation runtime: it remembers prior turns, compiles the next question into a task, routes the problem based on risk, executes tools in sequence, validates the result, and only then returns action cards.  
> So instead of a one-shot dashboard, it behaves like a memory-enabled analyst that can be questioned, corrected, and continued across turns.

