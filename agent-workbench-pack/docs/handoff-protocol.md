# Handoff Protocol — SoloDeck

Session end must produce:

1. `trace_id` and `data/solodeck_v3_memory/snapshots/{trace_id}.*.json` if present.
2. `developer_trace` summary: route, skills run, validation issues.
3. Open questions when `linked_entities.unresolved` is non-empty (voice/multi-turn).
4. Next acceptance command: `python agent-workbench-pack/scripts/verify_agent.py`.

Run: `python agent-workbench-pack/scripts/generate_handoff.py --trace-id <id>`
