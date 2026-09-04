from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def langfuse_status() -> dict[str, Any]:
    """Return configuration health without exposing credentials."""
    configured = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
    try:
        import langfuse  # noqa: F401

        installed = True
    except ImportError:
        installed = False
    requested = _truthy("SOLODECK_LANGFUSE_ENABLED")
    return {
        "requested": requested,
        "configured": configured,
        "sdk_installed": installed,
        "enabled": requested and configured and installed,
        "capture_content": _truthy("SOLODECK_LANGFUSE_CAPTURE_CONTENT"),
        "environment": os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development"),
        "host": os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    }


@lru_cache(maxsize=1)
def _client() -> Any | None:
    if not langfuse_status()["enabled"]:
        return None
    try:
        from langfuse import get_client

        return get_client()
    except Exception:
        return None


def _content(value: str) -> str | dict[str, Any]:
    if _truthy("SOLODECK_LANGFUSE_CAPTURE_CONTENT"):
        return value[:2000]
    return {
        "length": len(value),
        "sha256": hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16],
    }


def safe_dataset_summary(df: Any) -> dict[str, Any]:
    if df is None:
        return {"rows": 0, "columns": 0}
    shape = getattr(df, "shape", (0, 0))
    column_names = [str(name) for name in getattr(df, "columns", [])]
    return {
        "rows": int(shape[0]),
        "columns": int(shape[1]),
        "schema_hash": hashlib.sha256("|".join(column_names).encode("utf-8")).hexdigest()[:16],
    }


@contextmanager
def _observation(*, name: str, as_type: str, input: Any = None, metadata: dict[str, Any] | None = None, model: str | None = None) -> Iterator[Any | None]:
    client = _client()
    if client is None:
        yield None
        return
    kwargs: dict[str, Any] = {"as_type": as_type, "name": name}
    if input is not None:
        kwargs["input"] = input
    if metadata:
        kwargs["metadata"] = metadata
    if model:
        kwargs["model"] = model
    try:
        manager = client.start_as_current_observation(**kwargs)
        observation = manager.__enter__()
    except Exception:
        yield None
        return
    try:
        yield observation
    except BaseException as exc:
        try:
            manager.__exit__(type(exc), exc, exc.__traceback__)
        except Exception:
            pass
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception:
            pass


@contextmanager
def agent_observation(message: str, session_id: str, trace_id: str, df: Any) -> Iterator[Any | None]:
    metadata = {
        "solodeck_trace_id": trace_id,
        "runtime_version": "4.0.0",
        "dataset": safe_dataset_summary(df),
    }
    with _observation(
        name="solodeck-v4-agent",
        as_type="agent",
        input={"message": _content(message), "dataset": metadata["dataset"]},
        metadata=metadata,
    ) as observation:
        if observation is None:
            yield None
            return
        try:
            from langfuse import propagate_attributes
            manager = propagate_attributes(session_id=session_id, tags=["solodeck", "v4", "data-agent"])
            manager.__enter__()
        except Exception:
            yield observation
            return
        try:
            yield observation
        except BaseException as exc:
            try:
                manager.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:
                pass
            raise
        else:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                pass


def tool_observation(name: str, call_id: str, permission: str, args: dict[str, Any]) -> Any:
    return _observation(
        name=f"tool:{name}",
        as_type="tool",
        input={"arg_keys": sorted(args)},
        metadata={"call_id": call_id, "permission": permission},
    )


def workflow_observation(name: str, state: dict[str, Any]) -> Any:
    return _observation(
        name=f"node:{name}",
        as_type="chain",
        input={
            "trace_id": state.get("trace_id"),
            "revision": int(state.get("revision_number", 0)),
        },
        metadata={"node": name, "runtime": "langgraph"},
    )


def generation_observation(*, model: str, profile: str, attempt: int, message_count: int) -> Any:
    return _observation(
        name=f"llm:{profile}",
        as_type="generation",
        input={"message_count": message_count},
        metadata={"profile": profile, "fallback_attempt": attempt},
        model=model,
    )


def update_observation(observation: Any | None, **kwargs: Any) -> None:
    if observation is None:
        return
    try:
        observation.update(**kwargs)
    except Exception:
        return


def record_agent_scores(observation: Any | None, result: dict[str, Any]) -> None:
    if observation is None:
        return
    critic = result.get("critic_report") or {}
    governance = result.get("governance_report") or {}
    reward = result.get("industrial_process_reward") or {}
    scores = {
        "critic_quality": critic.get("overall_score"),
        "claim_governance_pass": 1.0 if governance.get("valid") else 0.0,
        "process_reward": reward.get("total"),
    }
    for name, value in scores.items():
        if value is None:
            continue
        try:
            observation.score_trace(name=name, value=float(value), data_type="NUMERIC")
        except Exception:
            continue


def get_langgraph_callback() -> Any | None:
    if _client() is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        return None


def flush_langfuse() -> None:
    client = _client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        return
