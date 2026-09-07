from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from solo_creator_agent.src import auth
from solo_creator_agent import api_spa
from solodeck_runtime.workspace import DataWorkspaceRepository


def test_auth_session_round_trip_and_revocation(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "SOLODECK_AUTH_DB_PATH", tmp_path / "auth.db")
    registered = auth.register_user("owner@example.com", "secret12", "Owner")

    assert registered["ok"] is True
    token = auth.create_auth_session(registered["user_id"])
    current = auth.user_from_session(token)
    assert current == {
        "user_id": registered["user_id"],
        "email": "owner@example.com",
        "display_name": "Owner",
    }

    auth.revoke_auth_session(token)
    assert auth.user_from_session(token) is None


def test_threads_restore_messages_and_keep_workspaces_isolated(tmp_path):
    database = tmp_path / "workspace.db"
    repository = DataWorkspaceRepository(database)
    frame = pd.DataFrame({"platform": ["小红书"], "conversions": [4]})
    repository.register_dataset("user_1", "dataset_a", "orders.csv", "文件上传", tmp_path / "orders.csv", frame)

    thread = repository.create_thread("user_1", "dataset_a")
    repository.append_message("user_1", thread["thread_id"], "user", "哪个平台转化更好？")
    repository.bind_thread_session("user_1", thread["thread_id"], "session_a", "dataset_a")
    repository.append_message(
        "user_1",
        thread["thread_id"],
        "assistant",
        "小红书当前转化最高。",
        {"reply": "小红书当前转化最高。", "user_artifact": {"kind": "ranking"}, "raw_rows": [1, 2]},
    )

    restored = DataWorkspaceRepository(database).get_thread("user_1", thread["thread_id"], include_messages=True)
    assert restored["session_id"] == "session_a"
    assert restored["title"] == "哪个平台转化更好？"
    assert [item["role"] for item in restored["messages"]] == ["user", "assistant"]
    assert restored["messages"][1]["result"]["user_artifact"] == {"kind": "ranking"}
    assert "raw_rows" not in restored["messages"][1]["result"]
    assert repository.list_threads("user_2") == []
    assert repository.get_thread("user_2", thread["thread_id"], include_messages=True) is None


def test_archived_thread_disappears_without_deleting_audit_history(tmp_path):
    repository = DataWorkspaceRepository(tmp_path / "workspace.db")
    thread = repository.create_thread("user_1", None, "临时分析")
    repository.append_message("user_1", thread["thread_id"], "user", "检查数据")

    assert repository.archive_thread("user_1", thread["thread_id"]) is True
    assert repository.list_threads("user_1") == []
    assert repository.get_thread("user_1", thread["thread_id"], include_messages=True)["messages"][0]["content"] == "检查数据"


def test_api_reuses_thread_session_and_scopes_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "SOLODECK_AUTH_DB_PATH", tmp_path / "auth.db")
    monkeypatch.setitem(api_spa.register_user.__globals__, "SOLODECK_AUTH_DB_PATH", tmp_path / "auth.db")
    repository = DataWorkspaceRepository(tmp_path / "workspace.db")
    monkeypatch.setattr(api_spa, "WORKSPACES", repository)
    dataset_id = "dataset_thread_test"
    frame = pd.DataFrame({"platform": ["小红书", "抖音"], "conversions": [4, 2]})
    api_spa.DATASETS[dataset_id] = frame

    session_state = {}
    def fake_create_session(**kwargs):
        session_state.update({"session_id": "session_fixed", "dataset_id": kwargs.get("dataset_id")})
        return dict(session_state)
    def fake_update_session(session_id, **fields):
        session_state.update(fields)
        return dict(session_state)
    monkeypatch.setattr(api_spa, "create_session", fake_create_session)
    monkeypatch.setattr(api_spa, "get_session", lambda session_id: dict(session_state) if session_id and session_state else None)
    monkeypatch.setattr(api_spa, "update_session", fake_update_session)
    monkeypatch.setattr(api_spa, "build_agent_trace", lambda *args, **kwargs: {"steps": [], "task_spec": {}})
    monkeypatch.setattr(api_spa, "run_v4_agent", lambda message, df, session_id, text="": {
        "session_id": session_id,
        "state_id": f"state_{len(message)}",
        "reply": f"已分析：{message}",
        "task_spec": {"task_type": "descriptive_comparison"},
        "validation_report": {"block_output": False},
        "result_view": {"kind": "ranking"},
        "tool_calls": [{"tool": "Describe"}],
    })

    client = TestClient(api_spa.app)
    registered = client.post("/api/auth/register", json={
        "email": "api@example.com", "password": "secret12", "display_name": "API Owner",
    })
    assert registered.status_code == 200
    user_workspace = registered.json()["workspace_id"]
    repository.register_dataset(user_workspace, dataset_id, "orders.csv", "文件上传", tmp_path / "orders.csv", frame)
    workspace = client.get("/api/data-agent/workspace", params={"workspace_id": "workspace_attacker"}).json()
    assert workspace["workspace_id"] == user_workspace
    assert workspace["datasets"][0]["dataset_id"] == dataset_id

    first = client.post("/api/data-agent/query", json={"dataset_id": dataset_id, "message": "哪个平台更好？"}).json()
    revised_dataset_id = "dataset_thread_revised"
    revised_frame = pd.concat([frame, pd.DataFrame({"platform": ["淘宝"], "conversions": [7]})], ignore_index=True)
    api_spa.DATASETS[revised_dataset_id] = revised_frame
    repository.register_dataset(user_workspace, revised_dataset_id, "orders-updated.csv", "增量补充", tmp_path / "orders-updated.csv", revised_frame)
    second = client.post("/api/data-agent/query", json={
        "dataset_id": revised_dataset_id, "thread_id": first["thread_id"], "message": "结合新数据继续看成交数",
    }).json()
    assert second["session_id"] == first["session_id"] == "session_fixed"
    assert session_state["dataset_id"] == revised_dataset_id
    assert session_state["data_revision"] == 1
    thread = client.get(f"/api/data-agent/threads/{first['thread_id']}").json()
    assert [item["role"] for item in thread["messages"]] == ["user", "assistant", "user", "assistant"]


def test_upload_can_append_rows_to_current_dataset(tmp_path, monkeypatch):
    repository = DataWorkspaceRepository(tmp_path / "workspace.db")
    monkeypatch.setattr(api_spa, "WORKSPACES", repository)
    workspace_id = "workspace_append"
    base_id = "dataset_base_rows"
    base = pd.DataFrame({"platform": ["小红书", "抖音"], "conversions": [4, 2]})
    api_spa.DATASETS[base_id] = base
    repository.register_dataset(workspace_id, base_id, "orders.csv", "文件上传", tmp_path / "orders.csv", base)
    monkeypatch.setattr(api_spa, "_persist_runtime_dataset", lambda *args, **kwargs: None)
    monkeypatch.setattr(api_spa, "_runtime_dataset_path", lambda dataset_id: tmp_path / f"{dataset_id}.csv")
    monkeypatch.setattr(api_spa, "_run", lambda dataset_id, question_id="pain_point_title": {
        "dataset_id": dataset_id, "mapping": {}, "trace": [],
    })

    response = TestClient(api_spa.app).post(
        "/api/upload",
        data={"workspace_id": workspace_id, "append_to_dataset_id": base_id},
        files={"files": ("more.csv", b"platform,conversions\nTaobao,7\n", "text/csv")},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["appended"] is True
    assert payload["added_rows"] == 1
    assert len(api_spa.DATASETS[payload["dataset_id"]]) == 3
    assert payload["dataset"]["row_count"] == 3
