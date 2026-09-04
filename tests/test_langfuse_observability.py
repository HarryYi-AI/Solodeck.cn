from __future__ import annotations

import pandas as pd

from solodeck_v4.observability import langfuse_status, safe_dataset_summary
from solodeck_v4.observability import langfuse as langfuse_adapter
from solodeck_v4.tools import call_tool


class _FakeObservation:
    def __init__(self) -> None:
        self.updates = []
        self.scores = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)

    def score_trace(self, **kwargs) -> None:
        self.scores.append(kwargs)


class _FakeManager:
    def __init__(self, observation: _FakeObservation) -> None:
        self.observation = observation

    def __enter__(self):
        return self.observation

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FakeClient:
    def __init__(self) -> None:
        self.calls = []
        self.observations = []

    def start_as_current_observation(self, **kwargs):
        observation = _FakeObservation()
        self.calls.append(kwargs)
        self.observations.append(observation)
        return _FakeManager(observation)


def test_langfuse_is_optional_when_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SOLODECK_LANGFUSE_ENABLED", "true")
    langfuse_adapter._client.cache_clear()

    status = langfuse_status()
    assert status["configured"] is False
    assert status["enabled"] is False

    state = {"message": "读取记忆", "permissions": ["memory:read"]}
    result = call_tool("retrieve_memory", state, {})
    assert result["ok"] is True
    assert state["tool_audit"][0]["tool"] == "retrieve_memory"


def test_dataset_summary_never_contains_uploaded_values() -> None:
    frame = pd.DataFrame({"private_order": ["customer-secret"], "revenue": [99.0]})
    summary = safe_dataset_summary(frame)
    assert summary == {
        "rows": 1,
        "columns": 2,
        "schema_hash": summary["schema_hash"],
    }
    assert "customer-secret" not in str(summary)
    assert "private_order" not in str(summary)


def test_tool_contract_emits_sanitized_langfuse_span(monkeypatch) -> None:
    client = _FakeClient()
    monkeypatch.setattr(langfuse_adapter, "_client", lambda: client)
    state = {"message": "读取记忆", "permissions": ["memory:read"]}

    result = call_tool("retrieve_memory", state, {"secret": "must-not-leak"})

    assert result["ok"] is True
    assert client.calls[0]["name"] == "tool:retrieve_memory"
    assert client.calls[0]["input"] == {"arg_keys": ["secret"]}
    assert "must-not-leak" not in str(client.calls)
    assert client.observations[0].updates[0]["output"]["ok"] is True
