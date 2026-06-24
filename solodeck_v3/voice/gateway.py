"""Pipecat-shaped voice gateway stub for SoloDeck — stdlib only.

DOWNSTREAM: audio → VAD → STT → SoloDeck tool → TTS → transport
UPSTREAM: cancel (barge-in)

Does not require pipecat/livekit. Wire real STT/TTS providers in production.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from solodeck_v3.nlp.entity_linker import link_entities


@dataclass
class Frame:
    kind: str
    payload: Any
    direction: str = "downstream"


class Processor:
    def __init__(self, name: str) -> None:
        self.name = name
        self.next: Processor | None = None
        self.prev: Processor | None = None
        self.trace: list[str] = []

    def process(self, frame: Frame) -> None:
        self.trace.append(f"{self.name} saw {frame.kind}")
        if self.next is not None and frame.direction == "downstream":
            self.next.process(frame)
        elif self.prev is not None and frame.direction == "upstream":
            self.prev.process(frame)


class VAD(Processor):
    threshold: float = 0.5

    def process(self, frame: Frame) -> None:
        if frame.kind == "audio_chunk":
            is_speech = bool(frame.payload)
            if is_speech:
                super().process(Frame("vad_speech", frame.payload))
        else:
            super().process(frame)


class STT(Processor):
    def process(self, frame: Frame) -> None:
        if frame.kind == "vad_speech":
            transcript = str(frame.payload)
            confidence = 0.92 if len(transcript) > 2 else 0.4
            self.trace.append(f"STT confidence={confidence}")
            if confidence < 0.5:
                super().process(Frame("transcript", "请再说一遍，我没有听清楚。"))
            else:
                super().process(Frame("transcript", transcript))
        else:
            super().process(frame)


class SoloDeckToolProcessor(Processor):
    """Calls v3 agent or a stub; keeps text-level control (VoicePipelineAgent pattern)."""

    def __init__(self, name: str, runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        super().__init__(name)
        self.runner = runner
        self.session: dict[str, Any] = {"prior_entities": {}}

    def process(self, frame: Frame) -> None:
        if frame.kind == "cancel":
            self.trace.append("SoloDeckTool: cancelled")
            super().process(frame)
            return
        if frame.kind == "transcript":
            text = str(frame.payload)
            if text.startswith("请再说一遍"):
                super().process(Frame("text", text))
                return
            linked = link_entities(text, self.session.get("columns", []), self.session.get("prior_entities"))
            self.session["prior_entities"] = {e["mention"]: e.get("column") for e in linked.get("linked_entities", []) if e.get("column")}
            if self.runner is None:
                reply = f"收到：{text}。我会基于你的数据做可验证分析，请在前端查看行动卡片。"
            else:
                result = self.runner(text, self.session)
                artifact = result.get("user_artifact") or {}
                cards = artifact.get("action_cards") or result.get("action_cards") or []
                if cards:
                    first = cards[0]
                    reply = first.get("title") or first.get("action") or "分析完成，请查看行动建议。"
                else:
                    summary = artifact.get("summary") or result.get("validation_report", {}).get("valid")
                    reply = f"分析完成。校验通过：{summary}" if summary else "分析完成，建议查看完整报告。"
            super().process(Frame("text", reply))
        else:
            super().process(frame)


class TTS(Processor):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.cancelled = False

    def process(self, frame: Frame) -> None:
        if frame.kind == "cancel":
            self.cancelled = True
            super().process(frame)
            return
        if frame.kind == "text":
            self.cancelled = False
            words = str(frame.payload).split()
            emitted: list[str] = []
            for word in words:
                if self.cancelled:
                    break
                emitted.append(word)
            super().process(Frame("tts_audio", emitted))
        else:
            super().process(frame)


class Transport(Processor):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.delivered: list[list[str]] = []

    def process(self, frame: Frame) -> None:
        if frame.kind == "tts_audio":
            self.delivered.append(list(frame.payload))
        else:
            super().process(frame)


def link_processors(*processors: Processor) -> None:
    for a, b in zip(processors, processors[1:]):
        a.next = b
        b.prev = a


def build_pipeline(runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None) -> tuple[VAD, SoloDeckToolProcessor, Transport]:
    vad = VAD("vad")
    stt = STT("stt")
    tool = SoloDeckToolProcessor("solodeck_tool", runner=runner)
    tts = TTS("tts")
    transport = Transport("transport")
    link_processors(vad, stt, tool, tts, transport)
    return vad, tool, transport


def simulate_turn(transcript: str, runner: Callable | None = None, columns: list[str] | None = None) -> dict[str, Any]:
    vad, tool, transport = build_pipeline(runner=runner)
    tool.session["columns"] = columns or ["platform", "title_style", "consultations", "views", "revenue"]
    vad.process(Frame("audio_chunk", transcript))
    return {
        "transcript": transcript,
        "delivered": transport.delivered,
        "trace": {p.name: p.trace for p in (vad, tool, transport)},
    }


def make_v3_runner(df: Any, text: str = "") -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    from solodeck_v3.workflows.data_agent_graph import run_v3_data_agent

    def _run(task: str, session: dict[str, Any]) -> dict[str, Any]:
        return run_v3_data_agent(task, df, text=text, max_revisions=1)

    return _run
