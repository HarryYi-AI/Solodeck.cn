"""Production voice stack profiles for SoloDeck v4.

Reference latencies and licensing from 2026 industry defaults:
  - livekit: 350-500 ms, commercial API
  - pipecat: 500-800 ms, mostly open source
  - edge: offline, privacy / on-device
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Literal

StackId = Literal["livekit", "pipecat", "edge"]


@dataclass(frozen=True)
class LatencyBudget:
    vad_ms: int
    stt_ms: int
    llm_first_token_ms: int
    agent_ms: int
    tts_first_audio_ms: int
    transport_rtt_ms: int

    @property
    def e2e_target_ms(self) -> int:
        return self.vad_ms + self.stt_ms + self.llm_first_token_ms + self.agent_ms + self.tts_first_audio_ms + self.transport_rtt_ms

    @property
    def e2e_label(self) -> str:
        return getattr(self, "_e2e_label", "500-800 ms")


@dataclass(frozen=True)
class VoiceStackProfile:
    id: StackId
    name: str
    tagline: str
    transport: str
    stt: str
    llm: str
    tts: str
    vad: str
    license: str
    latency: LatencyBudget
    latency_label: str
    solo_deck_backend: str
    when_to_use: str
    env_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tagline": self.tagline,
            "transport": self.transport,
            "stt": self.stt,
            "llm": self.llm,
            "tts": self.tts,
            "vad": self.vad,
            "license": self.license,
            "latency": {
                **asdict(self.latency),
                "e2e_target_ms": self.latency.e2e_target_ms,
                "e2e_label": self.latency_label,
            },
            "solo_deck_backend": self.solo_deck_backend,
            "when_to_use": self.when_to_use,
            "env_keys": list(self.env_keys),
        }


VOICE_STACKS: dict[StackId, VoiceStackProfile] = {
    "livekit": VoiceStackProfile(
        id="livekit",
        name="LiveKit 生产栈",
        tagline="行业默认 · 商用 API",
        transport="LiveKit WebRTC / SIP",
        vad="Silero VAD",
        stt="Deepgram Nova-3",
        llm="GPT-4o (tool call → SoloDeck v4)",
        tts="Cartesia Sonic",
        license="商用 API",
        latency=LatencyBudget(vad_ms=40, stt_ms=180, llm_first_token_ms=200, agent_ms=80, tts_first_audio_ms=120, transport_rtt_ms=50),
        latency_label="350-500 ms",
        solo_deck_backend="POST /api/v4/chat — VoicePipelineAgent 文本级控制",
        when_to_use="上线 Demo、电话/SIP、需要 350-500 ms 首音频",
        env_keys=("LIVEKIT_URL", "LIVEKIT_API_KEY", "DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CARTESIA_API_KEY"),
    ),
    "pipecat": VoiceStackProfile(
        id="pipecat",
        name="Pipecat DIY 栈",
        tagline="大体开源 · 自托管友好",
        transport="Pipecat SmallWebRTC / FastAPI WebSocket",
        vad="Silero VAD",
        stt="Whisper-streaming",
        llm="GPT-4o 或 Claude（tool → v4）",
        tts="Kokoro-82M",
        license="大体开源 + 模型 API",
        latency=LatencyBudget(vad_ms=50, stt_ms=220, llm_first_token_ms=250, agent_ms=100, tts_first_audio_ms=150, transport_rtt_ms=60),
        latency_label="500-800 ms",
        solo_deck_backend="Pipecat FrameProcessor 链 → SoloDeckToolProcessor",
        when_to_use="成本敏感、需要帧级 UPSTREAM 插话、500-800 ms 可接受",
        env_keys=("OPENAI_API_KEY",),
    ),
    "edge": VoiceStackProfile(
        id="edge",
        name="边缘离线栈",
        tagline="隐私 / 边缘 · 全开源",
        transport="本地 Audio I/O (sounddevice)",
        vad="Silero VAD (ONNX)",
        stt="Whisper.cpp",
        llm="llama.cpp 本地小模型（仅路由）+ SoloDeck Skills 计算",
        tts="Kokoro-ONNX",
        license="开源",
        latency=LatencyBudget(vad_ms=30, stt_ms=400, llm_first_token_ms=300, agent_ms=120, tts_first_audio_ms=200, transport_rtt_ms=0),
        latency_label="离线",
        solo_deck_backend="语音只做 I/O；数字结论仅来自 Python Skills",
        when_to_use="数据不出设备、创作者隐私、无网环境",
        env_keys=(),
    ),
}


def get_stack(stack_id: str | None) -> VoiceStackProfile:
    sid: StackId = stack_id if stack_id in VOICE_STACKS else "pipecat"  # type: ignore
    return VOICE_STACKS.get(sid, VOICE_STACKS["pipecat"])


def list_stacks() -> list[dict[str, Any]]:
    return [s.to_dict() for s in VOICE_STACKS.values()]
