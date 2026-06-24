from __future__ import annotations

from typing import Any


def compress_session_context(session: dict[str, Any], max_turns: int = 4, max_chars: int = 2400) -> dict[str, Any]:
    """Context compression: keep recent turns verbatim, summarize older ones."""
    turns = session.get("turns") or []
    recent = turns[-max_turns:]
    older = turns[:-max_turns] if len(turns) > max_turns else []

    older_summary = []
    for turn in older:
        role = turn.get("role", "user")
        text = (turn.get("content") or "")[:120]
        older_summary.append(f"{role}: {text}")

    recent_block = [{"role": t.get("role"), "content": t.get("content")} for t in recent]
    linked = session.get("linked_entities") or {}
    last_spec = session.get("last_task_spec") or {}
    cache_keys = list((session.get("artifact_cache") or {}).keys())

    payload = {
        "session_id": session.get("session_id"),
        "older_turn_summary": " | ".join(older_summary[-6:]),
        "recent_turns": recent_block,
        "linked_entities": linked,
        "last_task_type": last_spec.get("task_type"),
        "last_objective": (last_spec.get("objective") or "")[:200],
        "cached_artifacts": cache_keys[:8],
        "compressed_summary": session.get("compressed_summary") or "",
    }
    text = str(payload)
    if len(text) > max_chars:
        payload["truncated"] = True
        payload["recent_turns"] = recent_block[-2:]
    return payload


def merge_turn_into_summary(session: dict[str, Any], user_message: str, assistant_summary: str) -> str:
    prior = session.get("compressed_summary") or ""
    line = f"Q: {user_message[:80]} → A: {assistant_summary[:120]}"
    merged = (prior + " | " + line).strip(" |")
    return merged[-900:]
