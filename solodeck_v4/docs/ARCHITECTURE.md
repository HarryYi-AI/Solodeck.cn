# SoloDeck v4 Architecture

v4 extends v3 without breaking v3 APIs. New capabilities:

- **Multi-turn**: `session/store.py` persists turns, entities, artifact cache
- **Tool calling**: `tools/registry.py` — 7 structured tools
- **Orchestration**: `planning/task_planner.py` + `runtime/runner.py`
- **Context compression**: `context/compressor.py`
- **Risk routing**: `risk/risk_router.py` — deep path vs cache reuse
- **PostWriter gate**: `verification/post_writer.py`
- **Voice stacks**: `voice/stacks.py` — LiveKit / Pipecat / Edge profiles

## API

- `POST /api/v4/session` — create session
- `POST /api/v4/chat` — multi-turn message
- `GET /api/v4/session/{id}` — session state
- `GET /api/v4/tools` — tool manifest
- `GET /api/v4/voice/stacks` — voice stack catalog
- `POST /api/v4/voice/turn` — simulate STT → v4 → TTS preview

## Voice stacks

See `docs/VOICE_STACKS.md`.

| Stack | Latency | License |
|---|---|---|
| livekit | 350-500 ms | 商用 API |
| pipecat | 500-800 ms | 大体开源 |
| edge | offline | 开源 |

## Run

```bash
python -c "
from solo_creator_agent.src.data_loader import load_contents
from solodeck_v4 import create_session, run_v4_agent
from pathlib import Path
df = load_contents(Path('data/solodeck_synthetic/mock_contents.csv'))
s = create_session()
print(run_v4_agent('痛点标题是否提升咨询？', df, s['session_id'])['reply'])
"
```
