# Reliability Policy — SoloDeck

Absorbs five recurring failure modes:

1. **Hallucinated numbers** — caught by artifact + statistical validators.
2. **Causal overclaim** — caught by `causal_validator` + L3 G-Eval proxy.
3. **Scope creep** — workbench scope contract; Skills stay in `solodeck_v3/skills/`.
4. **Context loss** — six memory stores + trace snapshots, not chat history alone.
5. **Tool misuse** — Router + SkillLibrary topo order + process reward.

Override path: human edits `failure_memory` regression tasks, not agent self-override.
