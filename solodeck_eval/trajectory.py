from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "trajectories"
SECRET_PATTERN = re.compile(r"(?:QC-|sk-)[A-Za-z0-9_-]{12,}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    measured: bool = False


@dataclass
class TrajectoryStep:
    task_id: str
    step_id: str
    timestamp: str
    state_context_summary: dict[str, Any]
    available_tools: list[str]
    selected_tool: str
    arguments: dict[str, Any]
    observation: dict[str, Any]
    execution_status: str
    latency_ms: float
    token_usage: dict[str, Any]
    intermediate_reward: float
    final_reward: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TrajectoryLogger:
    """Append-only JSONL logger with bounded, redacted observations."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            day = datetime.now(timezone.utc).date().isoformat()
            path = DEFAULT_ROOT / f"trajectory-{day}.jsonl"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, step: TrajectoryStep | dict[str, Any]) -> dict[str, Any]:
        payload = asdict(step) if isinstance(step, TrajectoryStep) else dict(step)
        payload = _safe(payload)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return payload


def log_agent_result(
    result: dict[str, Any],
    user_task: str,
    *,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Normalize current v4 tool calls into SFT/RL-ready step records."""
    from solodeck_v4.tools.registry import list_tools

    task_spec = result.get("task_spec") or {}
    task_id = result.get("task_id") or (result.get("task_spec_v2") or {}).get("task_id") or result.get("trace_id", "unknown")
    audits = {row.get("call_id"): row for row in result.get("tool_audit") or []}
    rewards = (result.get("step_rewards") or {}).get("steps") or []
    calls = result.get("tool_calls") or []
    final_reward = float((result.get("industrial_process_reward") or {}).get("total", 0.0))
    available = [item.get("name") for item in list_tools() if item.get("name")]
    logger = TrajectoryLogger(path)
    rows = []
    for index, call in enumerate(calls, 1):
        audit = audits.get(call.get("call_id"), {})
        usage = call.get("token_usage") or audit.get("token_usage") or TokenUsage().__dict__
        intermediate = rewards[min(index - 1, len(rewards) - 1)].get("reward", 0.0) if rewards else 0.0
        row = TrajectoryStep(
            task_id=str(task_id),
            step_id=f"{result.get('trace_id', task_id)}:{index:03d}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            state_context_summary={
                "user_task": user_task[:300],
                "task_type": task_spec.get("task_type"),
                "objective": task_spec.get("objective"),
                "selected_columns": (result.get("analytical_state") or {}).get("selected_columns", [])[:20],
                "artifact_count": len(result.get("claims") or result.get("user_artifact") or {}),
            },
            available_tools=available,
            selected_tool=str(call.get("tool") or audit.get("tool") or "unknown"),
            arguments=call.get("arguments") or audit.get("arguments") or {},
            observation={key: value for key, value in call.items() if key not in {"arguments", "token_usage"}},
            execution_status=str(audit.get("status") or ("ok" if call.get("ok") else "error")),
            latency_ms=float(audit.get("latency_ms") or call.get("latency_ms") or 0.0),
            token_usage=_normalize_usage(usage),
            intermediate_reward=float(intermediate),
            final_reward=final_reward if index == len(calls) else None,
            metadata={"trace_id": result.get("trace_id"), "session_id": result.get("session_id")},
        )
        rows.append(logger.append(row))
    return rows


def _normalize_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return TokenUsage().__dict__
    prompt = int(value.get("prompt_tokens", value.get("input_tokens", 0)) or 0)
    completion = int(value.get("completion_tokens", value.get("output_tokens", 0)) or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": int(value.get("total_tokens", prompt + completion) or 0),
        "measured": bool(value.get("measured", prompt + completion > 0)),
    }


def _safe(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "<truncated>"
    if isinstance(value, dict):
        return {str(key)[:80]: _safe(item, depth + 1) for key, item in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [_safe(item, depth + 1) for item in value[:30]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = SECRET_PATTERN.sub("<redacted>", str(value))
    return text[:1200] + ("..." if len(text) > 1200 else "")
