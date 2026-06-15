# Interview QA

## What is a Data Agent Runtime?

A system that compiles open-ended data tasks into typed workflows, executes tools, validates artifacts, records trace and updates memory.

## Why LangGraph?

It gives explicit state, conditional routing, repair loops and controllable execution.

## Where is the LangGraph workflow implemented?

`solodeck_v3/workflows/data_agent_graph.py`.

## What is KG used for?

KG provides memory, entity context, provenance, candidate confounders and constraints.

## Is KG causal ground truth?

No. KG is context and constraint only.

## Which causal discovery algorithms are used?

Optional causal-learn, LiNGAM and DAGMA can be used when installed. Otherwise SoloDeck uses rule-based causal hypothesis graphs.

## Why is causal discovery exploratory?

Observational data can contain confounding, selection bias and missing variables.

## How does routing work?

The router maps TaskSpec to tools, budget level, candidate Skills and repair requirements.

## How does FARS map to KG-DAG-CI?

KG supports ideation, DAG supports planning, CI validates experiment results and ReportSkill writes final artifacts.

## How does process reward work?

Each workflow step receives rewards or penalties from validation, routing, causal safety and privacy outcomes.

## How does Agent RL appear without training a large model?

The system stores selected workflows as pseudo-labels and updates skill utility memory.

## How does self-evolution work?

Failures create regression tasks, update memory and influence future routing.

## How is this different from RAG, BI and a normal LLM agent?

RAG retrieves, BI reports, and a normal LLM may answer directly. SoloDeck executes verified workflows with trace, causal safety checks, repair and memory.

