"""SoloDeck v4 voice gateway — stack-aware Pipecat-shaped pipeline."""

from __future__ import annotations

from typing import Any, Callable

from solodeck_v3.voice.gateway import simulate_turn
from solodeck_v4.voice.stacks import get_stack


def make_v4_runner(
    df: Any,
    session_id: str,
    text: str = "",
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    from solodeck_v4.runtime.runner import run_v4_agent

    def _run(task: str, session: dict[str, Any]) -> dict[str, Any]:
        sid = session.get("session_id") or session_id
        return run_v4_agent(task, df, sid, text=text)

    return _run


def simulate_voice_turn(
    transcript: str,
    *,
    stack_id: str = "pipecat",
    runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one voice turn with stack metadata and latency budget."""
    stack = get_stack(stack_id)
    base = simulate_turn(transcript, runner=runner, columns=columns)
    if session:
        base["session_id"] = session.get("session_id")
    base["stack"] = stack.to_dict()
    base["latency_budget_ms"] = {
        "target_e2e": stack.latency.e2e_target_ms,
        "label": stack.latency_label,
        "breakdown": {
            "vad": stack.latency.vad_ms,
            "stt": stack.latency.stt_ms,
            "llm_first_token": stack.latency.llm_first_token_ms,
            "solodeck_agent": stack.latency.agent_ms,
            "tts_first_audio": stack.latency.tts_first_audio_ms,
            "transport_rtt": stack.latency.transport_rtt_ms,
        },
    }
    base["architecture"] = (
        f"{stack.transport} → {stack.vad} → {stack.stt} → "
        f"{stack.llm} → SoloDeck v4 → {stack.tts} → speaker"
    )
    return base


def stack_wiring_notes(stack: VoiceStackProfile) -> list[str]:
    notes = [
        f"License: {stack.license}",
        f"Target latency: {stack.latency_label}",
        stack.solo_deck_backend,
        "Barge-in: UPSTREAM cancel frame → stop TTS + cancel agent task",
        "STT confidence < 0.5 → 请再说一遍，不调用 v4",
    ]
    if stack.id == "edge":
        notes.append("LLM 仅做意图路由；统计/因果数字必须来自 Python Skills")
    if stack.id == "livekit":
        notes.append("Use VoicePipelineAgent (not MultimodalAgent) for tool-level control")
    return notes
