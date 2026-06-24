# Agent Rules — SoloDeck

## startup/read-memory-first
- Read `data/solodeck_v3_memory/schema_memory.jsonl` before changing field mappings.

## forbidden/causal-overclaim
- Never write "已证明/必然导致" when CI crosses zero or sample size is small.
- KG is context only — not causal ground truth.

## forbidden/privacy
- Do not expose raw row-level PII in user artifacts.

## done/verification-pass
- A causal task is done only when `validation_report.valid` is true OR downgraded to experiment plan.

## scope/skills-only-compute
- LLM explains; Python Skills compute. Do not replace BootstrapSkill/RegressionSkill with LLM numbers.

## approval/new-dependency
- Adding ragas/deepeval/pipecat/livekit requires explicit approval and optional CI profile.
