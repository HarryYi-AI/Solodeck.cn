# SoloDeck Agent Workbench Pack

Drop-in workbench surfaces for SoloDeck v3 (lesson 42 capstone adapted).

## Install

Already colocated at repo root. To refresh:

```bash
bash agent-workbench-pack/bin/install.sh --force
python agent-workbench-pack/scripts/init_agent.py
```

## Scripts

| Script | Purpose |
|---|---|
| `init_agent.py` | Create `agent_state.json`, `task_board.json` |
| `verify_agent.py` | Single v3 run + layered eval gate |
| `run_with_feedback.py` | Sample benchmark + write report |
| `generate_handoff.py` | Handoff md from snapshot |

## Docs

See `docs/agent-rules.md`, `reliability-policy.md`, `handoff-protocol.md`, `reviewer-rubric.md`.

Pack version: see `VERSION`.
