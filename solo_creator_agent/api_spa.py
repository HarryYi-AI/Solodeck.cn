from __future__ import annotations

import json
import re
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.append(str(ROOT))

from src.agent_orchestrator import find_synthetic_data_dir
from src.agent_workflow import SoloDeckAgentWorkflow
from src.audit_log import read_audit
from src.data_loader import load_contents
from src.llm_agent import extract_records_from_uploads
from src.mock_data import generate_all
from src.skills import dataset_fingerprint, run_skill_pipeline
from src.auth import (
    create_auth_session,
    login_user,
    register_user,
    revoke_auth_session,
    user_from_session,
)
from solodeck.workflows.data_agent_graph import run_data_agent_graph
from solodeck_v3.workflows.data_agent_graph import run_v3_data_agent
from solodeck_v4.runtime.runner import create_session, run_v4_agent
from solodeck_v4.tools.registry import list_tools
from solodeck_v4.session.store import get_session, update_session
from solodeck_runtime.workspace import DataWorkspaceRepository
from solodeck_runtime.data_agent import build_agent_trace
from solodeck_runtime.sources import DataFrameSourceAdapter
from solodeck_runtime.tools import DataToolRegistry


app = FastAPI(title="SoloDeck Skill API", version="4.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATASETS: dict[str, pd.DataFrame] = {}
TEXTS: dict[str, str] = {}
ANALYSIS_CACHE: dict[str, dict[str, Any]] = {}
V4_SESSIONS: dict[str, str] = {}
RUNTIME_DATASET_ROOT = REPO_ROOT / "data" / "runtime_datasets"
RUNTIME_DATASET_ROOT.mkdir(parents=True, exist_ok=True)
WORKSPACES = DataWorkspaceRepository()
AUTH_COOKIE = "solodeck_session"


def _workspace_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{8,96}", candidate):
        return candidate
    return "workspace_local"


def _current_user(request: Request) -> dict[str, Any] | None:
    return user_from_session(request.cookies.get(AUTH_COOKIE))


def _request_workspace(request: Request, supplied: str | None = None) -> str:
    user = _current_user(request)
    return f"user_{user['user_id']}" if user else _workspace_id(supplied)


def _set_auth_cookie(response: JSONResponse, request: Request, token: str) -> None:
    forwarded = request.headers.get("x-forwarded-proto", "").lower()
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=request.url.scheme == "https" or forwarded == "https",
        samesite="lax",
        path="/",
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (pd.Series,)):
        return value.to_dict()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _load_default() -> pd.DataFrame:
    synthetic = find_synthetic_data_dir(ROOT.parent)
    data_dir = synthetic or ROOT / "data"
    if not (data_dir / "mock_contents.csv").exists():
        generate_all(data_dir)
    return load_contents(data_dir / "mock_contents.csv")


def _read_file(file: UploadFile, data: bytes) -> pd.DataFrame:
    name = (file.filename or "").lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(data))
    return pd.read_csv(BytesIO(data))


def _read_frames(file: UploadFile, data: bytes) -> list[pd.DataFrame]:
    name = (file.filename or "").lower()
    if name.endswith(".zip"):
        frames: list[pd.DataFrame] = []
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for member in archive.namelist():
                member_name = member.lower()
                if member_name.endswith("/"):
                    continue
                payload = archive.read(member)
                if member_name.endswith(".csv"):
                    frames.append(pd.read_csv(BytesIO(payload)))
                elif member_name.endswith((".xlsx", ".xls")):
                    frames.append(pd.read_excel(BytesIO(payload)))
        return frames
    return [_read_file(file, data)]


def _is_image_file(file: UploadFile) -> bool:
    name = (file.filename or "").lower()
    mime = (file.content_type or "").lower()
    return mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp"))


def _is_text_file(file: UploadFile) -> bool:
    name = (file.filename or "").lower()
    mime = (file.content_type or "").lower()
    if name.endswith((".csv", ".tsv")):
        return False
    return name.endswith((".txt", ".md", ".json")) or mime in {
        "text/plain",
        "text/markdown",
        "application/json",
    }


def _text_to_frame(text: str) -> pd.DataFrame:
    if not text.strip():
        return pd.DataFrame()
    rows = []
    chunks = [line.strip(" -，,。") for line in text.splitlines() if line.strip()]
    for index, chunk in enumerate(chunks[:40]):
        amount = 0.0
        money = re.search(r"(?:¥|￥)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", chunk)
        if money:
            amount = float(money.group(1).replace(",", ""))
        platform = "wechat"
        for key, value in {"小红书": "xiaohongshu", "B站": "bilibili", "抖音": "douyin", "TikTok": "tiktok", "YouTube": "youtube", "公众号": "wechat"}.items():
            if key.lower() in chunk.lower():
                platform = value
                break
        rows.append({
            "content_id": f"T{index + 1:04d}",
            "platform": platform,
            "title": chunk[:80],
            "topic": "文字导入",
            "title_style": "pain_point" if any(word in chunk for word in ["痛", "问题", "不会", "失败"]) else "tutorial",
            "views": 0,
            "likes": 0,
            "favorites": 0,
            "comments": 0,
            "new_followers": 0,
            "consultations": 1 if any(word in chunk for word in ["咨询", "私信", "沟通", "联系"]) else 0,
            "conversions": 1 if any(word in chunk for word in ["成交", "付款", "购买", "订单"]) else 0,
            "revenue": amount,
            "production_hours": 0,
        })
    return pd.DataFrame(rows)


def _get_df(dataset_id: str | None) -> tuple[str, pd.DataFrame]:
    if dataset_id and dataset_id in DATASETS:
        return dataset_id, DATASETS[dataset_id]
    if dataset_id:
        persisted = _load_runtime_dataset(dataset_id)
        if persisted is not None:
            DATASETS[dataset_id] = persisted
            return dataset_id, persisted
        raise KeyError(f"dataset not found: {dataset_id}")
    df = _load_default()
    did = dataset_fingerprint(df)
    DATASETS[did] = df
    _persist_runtime_dataset(did, df)
    return did, df


def _runtime_dataset_path(dataset_id: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", dataset_id or ""):
        return None
    return RUNTIME_DATASET_ROOT / f"{dataset_id}.csv"


def _persist_runtime_dataset(dataset_id: str, df: pd.DataFrame, text: str = "") -> None:
    path = _runtime_dataset_path(dataset_id)
    if path is None:
        return
    df.to_csv(path, index=False)
    if text.strip():
        path.with_suffix(".txt").write_text(text[:120000], encoding="utf-8")


def _load_runtime_dataset(dataset_id: str) -> pd.DataFrame | None:
    path = _runtime_dataset_path(dataset_id)
    if path is None or not path.exists():
        return None
    text_path = path.with_suffix(".txt")
    if text_path.exists():
        TEXTS[dataset_id] = text_path.read_text(encoding="utf-8")
    return pd.read_csv(path)


def _run(dataset_id: str | None, question_id: str = "pain_point_title") -> dict[str, Any]:
    did, df = _get_df(dataset_id)
    key = f"{did}:{question_id}"
    if key not in ANALYSIS_CACHE:
        result = run_skill_pipeline(df, question_id=question_id)
        result_id = result.get("dataset_id") or did
        # Mapping produces a canonical-data fingerprint. Keep that public ID
        # recoverable after process restarts as well as in the current process.
        DATASETS[result_id] = df
        _persist_runtime_dataset(result_id, df, TEXTS.get(did, ""))
        ANALYSIS_CACHE[key] = result
    return ANALYSIS_CACHE[key]


def _run_agent(dataset_id: str | None, question_id: str = "pain_point_title") -> dict[str, Any]:
    did, df = _get_df(dataset_id)
    key = f"agent:{did}:{question_id}"
    if key not in ANALYSIS_CACHE:
        ANALYSIS_CACHE[key] = SoloDeckAgentWorkflow().run(df, question_id=question_id, unstructured_text=TEXTS.get(did, ""))
    return ANALYSIS_CACHE[key]


@app.get("/api/health")
def health() -> dict[str, Any]:
    from solodeck_v4.observability import langfuse_status

    return {"ok": True, "service": "SoloDeck Skill API", "observability": langfuse_status()}


@app.post("/api/auth/register")
async def auth_register(payload: dict[str, Any], request: Request) -> JSONResponse:
    result = register_user(
        str(payload.get("email") or ""),
        str(payload.get("password") or ""),
        str(payload.get("display_name") or ""),
    )
    if not result.get("ok"):
        return JSONResponse({"error": result.get("error")}, status_code=400)
    token = create_auth_session(int(result["user_id"]))
    user = {key: result[key] for key in ("user_id", "email", "display_name")}
    response = JSONResponse({"authenticated": True, "user": user, "workspace_id": f"user_{result['user_id']}"})
    _set_auth_cookie(response, request, token)
    return response


@app.post("/api/auth/login")
async def auth_login(payload: dict[str, Any], request: Request) -> JSONResponse:
    result = login_user(str(payload.get("email") or ""), str(payload.get("password") or ""))
    if not result.get("ok"):
        return JSONResponse({"error": result.get("error")}, status_code=401)
    token = create_auth_session(int(result["user_id"]))
    user = {key: result[key] for key in ("user_id", "email", "display_name")}
    response = JSONResponse({"authenticated": True, "user": user, "workspace_id": f"user_{result['user_id']}"})
    _set_auth_cookie(response, request, token)
    return response


@app.get("/api/auth/me")
async def auth_me(request: Request) -> JSONResponse:
    user = _current_user(request)
    if not user:
        return JSONResponse({"authenticated": False, "user": None})
    return JSONResponse({"authenticated": True, "user": user, "workspace_id": f"user_{user['user_id']}"})


@app.post("/api/auth/logout")
async def auth_logout(request: Request) -> JSONResponse:
    revoke_auth_session(request.cookies.get(AUTH_COOKIE))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(AUTH_COOKIE, path="/")
    return response


@app.get("/api/v4/observability")
def v4_observability() -> dict[str, Any]:
    from solodeck_v4.observability import langfuse_status

    return langfuse_status()


@app.get("/api/demo")
def demo() -> JSONResponse:
    result = _run(None)
    return JSONResponse(_json_safe({"dataset_id": result["dataset_id"], "mapping": result["mapping"]}))


@app.post("/api/upload")
async def upload(
    request: Request,
    files: list[UploadFile] = File(default=[]),
    text: str = Form(default=""),
    workspace_id: str = Form(default=""),
    append_to_dataset_id: str = Form(default=""),
) -> JSONResponse:
    frames = []
    notes = []
    source_names = [file.filename or "未命名文件" for file in files]
    image_files: list[Any] = []
    extracted_tasks: list[dict[str, Any]] = []
    text_fragments = [text] if text else []
    for file in files:
        data = await file.read()
        if _is_image_file(file):
            from types import SimpleNamespace

            image_files.append(
                SimpleNamespace(
                    name=file.filename or "upload.png",
                    type=file.content_type or "image/png",
                    getvalue=lambda payload=data: payload,
                )
            )
            continue
        if _is_text_file(file):
            try:
                decoded = data.decode("utf-8", errors="ignore").strip()
                if decoded:
                    text_fragments.append(decoded[:12000])
            except Exception as exc:
                notes.append(f"{file.filename} 文字读取失败：{exc}")
            continue
        try:
            parsed = _read_frames(file, data)
            if not parsed:
                notes.append(f"{file.filename} 中没有可读取的 CSV/Excel 文件。")
                continue
            frames.extend(parsed)
        except Exception as exc:
            notes.append(f"{file.filename} 未能读取：{exc}")
    full_text = "\n".join(fragment for fragment in text_fragments if fragment).strip()
    if image_files:
        try:
            extracted = extract_records_from_uploads(full_text, image_files, "contents", language="中文")
            if extracted.get("records"):
                frames.append(pd.DataFrame(extracted["records"]))
            if extracted.get("tasks"):
                extracted_tasks = extracted["tasks"]
            if extracted.get("notes"):
                notes.append(str(extracted["notes"]))
        except Exception as exc:
            notes.append(f"截图识别暂时失败：{exc}")
    text_frame = _text_to_frame(full_text)
    if not text_frame.empty:
        frames.append(text_frame)
    if not frames:
        return JSONResponse({"error": "没有可读取的 CSV、Excel、ZIP、图片截图或文字。", "notes": notes}, status_code=400)
    incoming_df = pd.concat(frames, ignore_index=True, sort=False)
    current_workspace = _request_workspace(request, workspace_id)
    append_target = append_to_dataset_id.strip()
    appended_from: dict[str, Any] | None = None
    if append_target:
        appended_from = WORKSPACES.get_dataset(current_workspace, append_target)
        if not appended_from:
            return JSONResponse({"error": "要补充的数据集不存在或不属于当前工作区。"}, status_code=404)
        try:
            _, existing_df = _get_df(append_target)
        except KeyError:
            return JSONResponse({"error": "原数据文件已不可用，请重新上传完整资料。"}, status_code=410)
        df = pd.concat([existing_df, incoming_df], ignore_index=True, sort=False)
        notes.append(f"已在当前数据的 {len(existing_df)} 条记录后补充 {len(incoming_df)} 条新记录。")
    else:
        df = incoming_df
    did = dataset_fingerprint(df)
    DATASETS[did] = df
    TEXTS[did] = full_text
    _persist_runtime_dataset(did, df, full_text)
    for key in list(ANALYSIS_CACHE):
        if key.startswith(f"{did}:") or key.startswith(f"agent:{did}:"):
            ANALYSIS_CACHE.pop(key, None)
    result = _run(did)
    final_did = result["dataset_id"]
    DATASETS[final_did] = df
    TEXTS[final_did] = full_text
    _persist_runtime_dataset(final_did, df, full_text)
    dataset = WORKSPACES.register_dataset(
        current_workspace,
        final_did,
        f"{appended_from['name']}（已更新）" if appended_from else ("、".join(source_names[:3]) if source_names else "粘贴文本"),
        "增量补充" if appended_from else ("文件上传" if source_names else "文本输入"),
        _runtime_dataset_path(final_did) or "",
        df,
        result.get("mapping") or {},
    )
    payload = {
        "dataset_id": final_did,
        "dataset": dataset,
        "mapping": result["mapping"],
        "notes": notes,
        "tasks": extracted_tasks,
        "appended": bool(appended_from),
        "previous_dataset_id": append_target or None,
        "added_rows": len(incoming_df),
        "trace": result["trace"][:1],
    }
    return JSONResponse(_json_safe(payload))


@app.post("/api/data-agent/demo")
async def data_agent_demo(payload: dict[str, Any], request: Request) -> JSONResponse:
    workspace_id = _request_workspace(request, payload.get("workspace_id"))
    result = _run(None)
    did, frame = _get_df(result["dataset_id"])
    dataset = WORKSPACES.register_dataset(
        workspace_id,
        did,
        "SoloDeck 经营分析演示数据",
        "演示数据",
        _runtime_dataset_path(did) or "",
        frame,
        result.get("mapping") or {},
    )
    return JSONResponse(_json_safe({"dataset_id": did, "mapping": result.get("mapping"), "dataset": dataset}))


@app.get("/api/data-agent/workspace")
async def data_agent_workspace(request: Request, workspace_id: str = "") -> JSONResponse:
    current = _request_workspace(request, workspace_id)
    datasets = WORKSPACES.list_datasets(current)
    runs = WORKSPACES.list_runs(current)
    return JSONResponse(_json_safe({
        "workspace_id": current,
        "datasets": datasets,
        "runs": runs,
        "summary": {
            "dataset_count": len(datasets),
            "run_count": len(runs),
            "total_rows": sum(item["row_count"] for item in datasets),
        },
    }))


@app.get("/api/data-agent/datasets/{dataset_id}")
async def data_agent_dataset(dataset_id: str, request: Request, workspace_id: str = "") -> JSONResponse:
    current = _request_workspace(request, workspace_id)
    dataset = WORKSPACES.get_dataset(current, dataset_id)
    if not dataset:
        return JSONResponse({"error": "数据集不存在或不属于当前工作区。"}, status_code=404)
    try:
        _get_df(dataset_id)
    except KeyError:
        return JSONResponse({"error": "数据文件已丢失，请重新上传。"}, status_code=410)
    return JSONResponse(_json_safe(dataset))


@app.post("/api/diagnose")
async def diagnose(payload: dict[str, Any]) -> JSONResponse:
    result = _run(payload.get("dataset_id"), payload.get("question_id", "pain_point_title"))
    return JSONResponse(_json_safe({
        "dataset_id": result["dataset_id"],
        "mapping": result["mapping"],
        "kpis": result["kpis"],
        "observations": result["observations"],
        "trace": result["trace"][:3],
    }))


@app.post("/api/decision")
async def decision(payload: dict[str, Any]) -> JSONResponse:
    result = _run(payload.get("dataset_id"), payload.get("question_id", "pain_point_title"))
    return JSONResponse(_json_safe({
        "dataset_id": result["dataset_id"],
        "decision": result["decision"],
        "trace": result["trace"][:8],
    }))


@app.post("/api/action-plan")
async def action_plan(payload: dict[str, Any]) -> JSONResponse:
    result = _run(payload.get("dataset_id"), payload.get("question_id", "pain_point_title"))
    return JSONResponse(_json_safe({
        "dataset_id": result["dataset_id"],
        "action_cards": result["action_cards"],
        "trace": result["trace"],
    }))


@app.post("/api/full-agent")
async def full_agent(payload: dict[str, Any]) -> JSONResponse:
    result = _run_agent(payload.get("dataset_id"), payload.get("question_id", "pain_point_title"))
    return JSONResponse(_json_safe({
        "dataset_id": result["dataset_id"],
        "kg": result["kg"],
        "dag": result["dag"],
        "decision": {
            "query": result["query"],
            "readiness": result["readiness"],
            "effect": result["effect"],
            "evaluation": result.get("evaluation", {}),
            "validation_loop": result.get("validation_loop", {}),
        },
        "action_cards": result["action_cards"],
        "trace": result["trace"],
        "audit": read_audit(result["dataset_id"], limit=24),
    }))


@app.post("/api/v2-agent")
async def v2_agent(payload: dict[str, Any]) -> JSONResponse:
    did, df = _get_df(payload.get("dataset_id"))
    goal = payload.get("user_goal") or "判断哪些内容策略值得下周验证，并避免过度因果结论。"
    result = run_data_agent_graph(goal, df, text=TEXTS.get(did, ""), query=payload.get("query"))
    safe = {
        "task_spec": result.get("task_spec", {}),
        "hypothesis_tree": result.get("hypothesis_tree", {}),
        "budget": result.get("budget", {}),
        "selected_plan": result.get("evolution", {}).get("selected_plan", {}),
        "validation": result.get("validation", {}),
        "reflection": result.get("reflection", {}),
        "report": result.get("report", {}),
        "action_cards": result.get("action_cards", []),
        "rewards": result.get("rewards", {}),
        "memory": result.get("memory", {}),
        "trace": result.get("trace", []),
    }
    return JSONResponse(_json_safe(safe))


@app.post("/api/v3-agent")
async def v3_agent(payload: dict[str, Any]) -> JSONResponse:
    did, df = _get_df(payload.get("dataset_id"))
    task = payload.get("task") or payload.get("user_goal") or "评估内容策略增量，生成可验证的下一步行动。"
    result = run_v3_data_agent(task, df, text=TEXTS.get(did, ""), max_revisions=int(payload.get("max_revisions", 2)))
    safe = {
        "trace_id": result.get("trace_id"),
        "user_artifact": result.get("user_artifact", {}),
        "developer_trace": result.get("developer_trace", {}),
        "task_spec": result.get("task_spec", {}),
        "selected_plan": result.get("selected_plan", {}),
        "validation_report": result.get("validation_report", {}),
        "step_rewards": result.get("step_rewards", {}),
        "agent_rewards": result.get("agent_rewards", {}),
        "memory_updates": result.get("memory_updates", []),
        "failure_report": result.get("failure_report", {}),
    }
    return JSONResponse(_json_safe(safe))


@app.post("/api/voice-simulate")
async def voice_simulate(payload: dict[str, Any]) -> JSONResponse:
    """Optional Pipecat-shaped voice stub — does not affect v3-agent."""
    from solodeck_v3.voice.gateway import make_v3_runner, simulate_turn

    did, df = _get_df(payload.get("dataset_id"))
    transcript = payload.get("transcript") or payload.get("text") or ""
    use_v3 = bool(payload.get("run_v3", False))
    runner = make_v3_runner(df, TEXTS.get(did, "")) if use_v3 else None
    columns = list(df.columns) if not df.empty else ["platform", "title_style", "consultations"]
    result = simulate_turn(transcript, runner=runner, columns=columns)
    return JSONResponse(_json_safe(result))


@app.post("/api/eval/layered")
async def layered_eval_api(payload: dict[str, Any]) -> JSONResponse:
    """Optional layered evaluation on a fresh or cached v3 run."""
    from solodeck_v3.bench.layered_eval import run_layered_eval

    did, df = _get_df(payload.get("dataset_id"))
    task = payload.get("task") or payload.get("user_goal") or "评估内容策略并生成行动建议。"
    result = run_v3_data_agent(task, df, text=TEXTS.get(did, ""), max_revisions=int(payload.get("max_revisions", 1)))
    layered = run_layered_eval(result, task=task)
    return JSONResponse(_json_safe({"trace_id": result.get("trace_id"), "layered": layered}))


@app.post("/api/v4/session")
async def v4_create_session(payload: dict[str, Any], request: Request) -> JSONResponse:
    did, _ = _get_df(payload.get("dataset_id"))
    session = create_session(dataset_id=did, cost_budget=float(payload.get("cost_budget", 1.0)))
    current_user = _current_user(request)
    session = update_session(
        session["session_id"],
        project_id=_request_workspace(request, payload.get("workspace_id")),
        user_id=str(current_user["user_id"]) if current_user else _workspace_id(payload.get("workspace_id")),
    )
    V4_SESSIONS[session["session_id"]] = did
    return JSONResponse(_json_safe(session))


@app.get("/api/v4/session/{session_id}")
async def v4_get_session(session_id: str, request: Request, workspace_id: str = "") -> JSONResponse:
    session = get_session(session_id)
    if not session:
        return JSONResponse({"error": "session not found"}, status_code=404)
    if session.get("project_id") and session["project_id"] != _request_workspace(request, workspace_id):
        return JSONResponse({"error": "session not found"}, status_code=404)
    return JSONResponse(_json_safe(session))


@app.get("/api/v4/tools")
async def v4_tools() -> JSONResponse:
    return JSONResponse(_json_safe({"tools": list_tools(), "version": "4.0.0"}))


@app.post("/api/v4/chat")
async def v4_chat(payload: dict[str, Any], request: Request) -> JSONResponse:
    message = (payload.get("message") or payload.get("task") or "").strip()
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)
    session_id = payload.get("session_id")
    if not session_id:
        try:
            did, _ = _get_df(payload.get("dataset_id"))
        except KeyError:
            return JSONResponse(
                {"error": "当前数据已不可用，请重新上传原文件后继续提问。"},
                status_code=409,
            )
        session = create_session(dataset_id=did, cost_budget=float(payload.get("cost_budget", 1.0)))
        session_id = session["session_id"]
        V4_SESSIONS[session_id] = did
    persisted_session = get_session(session_id) or {}
    expected_project = _request_workspace(request, payload.get("workspace_id"))
    if persisted_session.get("project_id") and persisted_session["project_id"] != expected_project:
        return JSONResponse({"error": "session not found"}, status_code=404)
    current_user = _current_user(request)
    persisted_session = update_session(
        session_id,
        project_id=expected_project,
        user_id=str(current_user["user_id"]) if current_user else expected_project,
    )
    did = V4_SESSIONS.get(session_id) or persisted_session.get("dataset_id") or payload.get("dataset_id")
    try:
        _, df = _get_df(did)
    except KeyError:
        return JSONResponse(
            {"error": "当前会话关联的数据已不可用，请重新上传原文件后继续提问。"},
            status_code=409,
        )
    result = run_v4_agent(message, df, session_id, text=TEXTS.get(did or "", ""))
    safe = {
        "session_id": result.get("session_id"),
        "trace_id": result.get("trace_id"),
        "reply": result.get("reply"),
        "user_artifact": result.get("user_artifact"),
        "developer_trace": result.get("developer_trace"),
        "task_spec": result.get("task_spec"),
        "plan_steps": result.get("plan_steps"),
        "tool_calls": result.get("tool_calls"),
        "risk_profile": result.get("risk_profile"),
        "validation_report": result.get("validation_report"),
        "post_writer_validation": result.get("post_writer_validation"),
        "governance_report": result.get("governance_report"),
        "evidence_level": result.get("evidence_level"),
        "failure_report": result.get("failure_report"),
        "memory_updates": result.get("memory_updates"),
        "decision_memory_update": result.get("decision_memory_update"),
        "cost_spent": result.get("cost_spent"),
        "session_cost_total": result.get("session_cost_total"),
        "version": result.get("version"),
        "state_id": result.get("state_id"),
        "result_view": result.get("result_view"),
        "executed_skills": result.get("selected_skills"),
        "analytical_state_summary": _analytical_state_summary(result.get("analytical_state")),
        "workflow_summary": _workflow_summary(result.get("analysis_workflow"), result.get("workflow_validation")),
    }
    return JSONResponse(_json_safe(safe))


@app.post("/api/data-agent/threads")
async def create_data_agent_thread(payload: dict[str, Any], request: Request) -> JSONResponse:
    workspace_id = _request_workspace(request, payload.get("workspace_id"))
    dataset_id = str(payload.get("dataset_id") or "") or None
    if dataset_id and not WORKSPACES.get_dataset(workspace_id, dataset_id):
        return JSONResponse({"error": "数据集不存在或不属于当前工作区。"}, status_code=404)
    thread = WORKSPACES.create_thread(workspace_id, dataset_id, str(payload.get("title") or "新对话"))
    return JSONResponse(_json_safe(thread))


@app.get("/api/data-agent/threads")
async def list_data_agent_threads(request: Request, workspace_id: str = "") -> JSONResponse:
    current = _request_workspace(request, workspace_id)
    return JSONResponse(_json_safe({"threads": WORKSPACES.list_threads(current)}))


@app.get("/api/data-agent/threads/{thread_id}")
async def get_data_agent_thread(thread_id: str, request: Request, workspace_id: str = "") -> JSONResponse:
    current = _request_workspace(request, workspace_id)
    thread = WORKSPACES.get_thread(current, thread_id, include_messages=True)
    if not thread:
        return JSONResponse({"error": "对话不存在。"}, status_code=404)
    return JSONResponse(_json_safe(thread))


@app.delete("/api/data-agent/threads/{thread_id}")
async def archive_data_agent_thread(thread_id: str, request: Request, workspace_id: str = "") -> JSONResponse:
    current = _request_workspace(request, workspace_id)
    if not WORKSPACES.archive_thread(current, thread_id):
        return JSONResponse({"error": "对话不存在。"}, status_code=404)
    return JSONResponse({"archived": True})


@app.post("/api/data-agent/query")
async def data_agent_query(payload: dict[str, Any], request: Request) -> JSONResponse:
    message = (payload.get("message") or payload.get("task") or "").strip()
    if not message:
        return JSONResponse({"error": "请输入要分析的问题。"}, status_code=400)
    workspace_id = _request_workspace(request, payload.get("workspace_id"))
    dataset_id = str(payload.get("dataset_id") or "")
    if not WORKSPACES.get_dataset(workspace_id, dataset_id):
        return JSONResponse({"error": "请先在数据目录上传或选择一个数据集。"}, status_code=409)
    try:
        _, frame = _get_df(dataset_id)
    except KeyError:
        return JSONResponse({"error": "当前数据文件已不可用，请重新上传。"}, status_code=410)

    thread_id = str(payload.get("thread_id") or "")
    thread = WORKSPACES.get_thread(workspace_id, thread_id, include_messages=True) if thread_id else None
    if thread_id and not thread:
        return JSONResponse({"error": "当前对话不存在或不属于你的工作区。"}, status_code=404)
    if not thread:
        thread = WORKSPACES.create_thread(workspace_id, dataset_id, message)
        thread_id = thread["thread_id"]
    WORKSPACES.append_message(workspace_id, thread_id, "user", message)

    session_id = thread.get("session_id") or payload.get("session_id")
    persisted_session = get_session(session_id) if session_id else None
    if persisted_session and persisted_session.get("dataset_id") != dataset_id:
        persisted_session = update_session(
            session_id,
            dataset_id=dataset_id,
            artifact_cache={},
            last_task_spec=None,
            last_state_id=None,
            data_revision=int(persisted_session.get("data_revision", 0)) + 1,
        )
    if not persisted_session or persisted_session.get("dataset_id") != dataset_id:
        session = create_session(dataset_id=dataset_id, cost_budget=float(payload.get("cost_budget", 10.0)))
        session_id = session["session_id"]
        V4_SESSIONS[session_id] = dataset_id
    current_user = _current_user(request)
    persisted_session = update_session(
        session_id,
        project_id=workspace_id,
        user_id=str(current_user["user_id"]) if current_user else workspace_id,
    )
    WORKSPACES.bind_thread_session(workspace_id, thread_id, session_id, dataset_id)
    started = time.perf_counter()
    result = run_v4_agent(message, frame, session_id, text=TEXTS.get(dataset_id, ""))
    acquisition = build_agent_trace(
        message,
        frame,
        dataset_id,
        project_id=workspace_id,
        session_id=session_id,
    )
    result["data_agent_trace"] = acquisition
    elapsed_ms = (time.perf_counter() - started) * 1000
    result_view = result.get("result_view") or {}
    run = WORKSPACES.save_run(workspace_id, dataset_id, message, result, result_view, elapsed_ms)
    safe = {
        "session_id": result.get("session_id"),
        "trace_id": result.get("trace_id"),
        "reply": result.get("reply"),
        "user_artifact": result.get("user_artifact"),
        "task_spec": result.get("task_spec"),
        "plan_steps": result.get("plan_steps"),
        "tool_calls": result.get("tool_calls"),
        "risk_profile": result.get("risk_profile"),
        "validation_report": result.get("validation_report"),
        "post_writer_validation": result.get("post_writer_validation"),
        "evidence_level": result.get("evidence_level"),
        "failure_report": result.get("failure_report"),
        "memory_updates": result.get("memory_updates"),
        "decision_memory_update": result.get("decision_memory_update"),
        "cost_spent": result.get("cost_spent"),
        "state_id": result.get("state_id"),
        "result_view": result_view,
        "executed_skills": result.get("selected_skills"),
        "analytical_state_summary": _analytical_state_summary(result.get("analytical_state")),
        "workflow_summary": _workflow_summary(result.get("analysis_workflow"), result.get("workflow_validation")),
        "data_agent_trace": acquisition,
        "run": run,
        "thread_id": thread_id,
    }
    WORKSPACES.append_message(workspace_id, thread_id, "assistant", str(result.get("reply") or "分析完成"), safe)
    return JSONResponse(_json_safe(safe))


@app.get("/api/data-agent/tools")
async def data_agent_tools() -> JSONResponse:
    """Return lightweight manifests; full schemas are disclosed after selection."""
    registry = DataToolRegistry(DataFrameSourceAdapter({}))
    return JSONResponse({"tools": registry.manifests(), "loading": "progressive"})


@app.get("/api/data-agent/repair-demos")
async def data_agent_repair_demos() -> JSONResponse:
    from solodeck_runtime.repair_demos import silent_join_repair_demo, tool_failure_repair_demo

    return JSONResponse(_json_safe({
        "tool_failure": tool_failure_repair_demo(),
        "silent_join_error": silent_join_repair_demo(),
    }))


@app.get("/api/data-agent/runs")
async def data_agent_runs(request: Request, workspace_id: str = "") -> JSONResponse:
    current = _request_workspace(request, workspace_id)
    return JSONResponse(_json_safe({"runs": WORKSPACES.list_runs(current)}))


@app.get("/api/data-agent/runs/{run_id}")
async def data_agent_run(run_id: str, request: Request, workspace_id: str = "") -> JSONResponse:
    run = WORKSPACES.get_run(_request_workspace(request, workspace_id), run_id)
    if not run:
        return JSONResponse({"error": "运行记录不存在。"}, status_code=404)
    return JSONResponse(_json_safe(run))


def _analytical_state_summary(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not state:
        return None
    allowed = {
        "state_id", "parent_state_id", "branch_id", "task_id", "dataset_versions",
        "selected_tables", "selected_columns", "artifacts", "validation_status",
        "unresolved_questions", "evidence_level",
    }
    return {key: state.get(key) for key in allowed}


def _workflow_summary(workflow: dict[str, Any] | None, validation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not workflow:
        return None
    return {
        "workflow_id": workflow.get("workflow_id"),
        "version": workflow.get("version"),
        "operations": [node.get("operation_type") for node in workflow.get("physical_nodes") or []],
        "validation": validation or {},
    }


@app.get("/api/v4/trace/{trace_id}/checkpoints")
async def v4_trace_checkpoints(trace_id: str) -> JSONResponse:
    from solodeck_v4.runtime.checkpoint import CheckpointStore

    paths = CheckpointStore().list(trace_id)
    return JSONResponse({"trace_id": trace_id, "checkpoints": [path.name for path in paths]})


@app.get("/api/v4/trace/{trace_id}/replay")
async def v4_trace_replay(trace_id: str, checkpoint: int = -1) -> JSONResponse:
    from solodeck_v4.runtime.checkpoint import CheckpointStore

    try:
        state = CheckpointStore().replay(trace_id, checkpoint)
    except (KeyError, IndexError):
        return JSONResponse({"error": "checkpoint not found"}, status_code=404)
    # Replay inspection excludes uploaded rows and secret-bearing fields.
    safe = {key: value for key, value in state.items() if key not in {"df", "text", "artifact_cache"}}
    return JSONResponse(_json_safe(safe))


@app.get("/api/v4/memory/trace")
async def v4_memory_trace(request: Request, project_id: str = "", session_id: str | None = None) -> JSONResponse:
    from solodeck_v4.memory import UnifiedMemory

    current_project = _request_workspace(request, project_id)
    rows = UnifiedMemory().export_memory_trace(current_project, session_id)
    safe = [
        {
            "memory_id": row["memory_id"], "memory_type": row["memory_type"],
            "source_type": row["source_type"], "source_id": row["source_id"],
            "content_summary": row["content_summary"], "lineage": row["lineage"],
            "quality_score": row["quality_score"], "warnings": row["warnings"],
            "version": row["version"], "updated_at": row["updated_at"],
        }
        for row in rows
    ]
    return JSONResponse(_json_safe({"project_id": current_project, "session_id": session_id, "items": safe}))


@app.get("/api/v4/decision-memory/context")
async def v4_decision_memory_context(request: Request, query: str, workspace_id: str = "") -> JSONResponse:
    from solodeck_v4.decision_memory import DecisionMemoryService

    project_id = _request_workspace(request, workspace_id)
    context = DecisionMemoryService().get_decision_context(query, project_id=project_id)
    return JSONResponse(_json_safe(context))


@app.post("/api/v4/decision-memory/outcomes")
async def v4_decision_memory_outcome(payload: dict[str, Any], request: Request) -> JSONResponse:
    from solodeck_v4.decision_memory import DecisionMemoryService

    project_id = _request_workspace(request, payload.get("workspace_id"))
    service = DecisionMemoryService()
    episode_id = str(payload.get("episode_id") or "")
    episode = service.store.get_episode(episode_id)
    if not episode or episode.project_id != project_id:
        return JSONResponse({"error": "决策记录不存在或不属于当前工作区。"}, status_code=404)
    metrics = payload.get("metrics") or {}
    if not isinstance(metrics, dict):
        return JSONResponse({"error": "metrics 必须是指标字典。"}, status_code=400)
    try:
        normalized_metrics = {str(key): float(value) for key, value in metrics.items()}
    except (TypeError, ValueError):
        return JSONResponse({"error": "metrics 中的值必须是数字。"}, status_code=400)
    result = service.record_outcome(
        episode_id,
        metrics=normalized_metrics,
        success=payload.get("success"),
        observed_at=payload.get("observed_at"),
    )
    return JSONResponse(_json_safe(result))


@app.post("/api/v4/decision-memory/consolidate")
async def v4_decision_memory_consolidate(payload: dict[str, Any], request: Request) -> JSONResponse:
    from solodeck_v4.decision_memory import DecisionMemoryService

    project_id = _request_workspace(request, payload.get("workspace_id"))
    window_days = max(1, min(int(payload.get("window_days", 365)), 3650))
    return JSONResponse(_json_safe(DecisionMemoryService().run_consolidation(project_id, window_days)))


@app.get("/api/v4/states/{state_id}")
async def v4_get_analytical_state(state_id: str) -> JSONResponse:
    from solodeck_runtime import StateStore

    try:
        state = StateStore().restore(state_id)
    except KeyError:
        return JSONResponse({"error": "analytical state not found"}, status_code=404)
    return JSONResponse(_json_safe(state.to_dict()))


@app.post("/api/v4/states/{state_id}/branch")
async def v4_branch_analytical_state(state_id: str, payload: dict[str, Any]) -> JSONResponse:
    from solodeck_runtime import StateStore

    branch_id = str(payload.get("branch_id") or "").strip()
    if not branch_id:
        return JSONResponse({"error": "branch_id required"}, status_code=400)
    allowed = {"filters", "joins", "derived_variables", "hypotheses", "assumptions", "unresolved_questions"}
    changes = {key: value for key, value in payload.get("changes", {}).items() if key in allowed}
    try:
        state = StateStore().branch(state_id, branch_id, **changes)
    except KeyError:
        return JSONResponse({"error": "analytical state not found"}, status_code=404)
    return JSONResponse(_json_safe(state.to_dict()))


@app.post("/api/v4/states/{current_state_id}/rollback/{target_state_id}")
async def v4_rollback_analytical_state(current_state_id: str, target_state_id: str) -> JSONResponse:
    from solodeck_runtime import StateStore

    try:
        state = StateStore().rollback(current_state_id, target_state_id)
    except KeyError:
        return JSONResponse({"error": "analytical state not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse(_json_safe(state.to_dict()))


@app.get("/api/v4/states/diff/{left_state_id}/{right_state_id}")
async def v4_diff_analytical_states(left_state_id: str, right_state_id: str) -> JSONResponse:
    from solodeck_runtime import StateStore

    try:
        diff = StateStore().diff(left_state_id, right_state_id)
    except KeyError:
        return JSONResponse({"error": "analytical state not found"}, status_code=404)
    return JSONResponse(_json_safe({"left": left_state_id, "right": right_state_id, "diff": diff}))


@app.get("/api/v4/artifacts/{artifact_id}/lineage")
async def v4_artifact_lineage(artifact_id: str) -> JSONResponse:
    from solodeck_runtime import ArtifactRegistry

    try:
        lineage = ArtifactRegistry().lineage(artifact_id)
    except KeyError:
        return JSONResponse({"error": "artifact not found"}, status_code=404)
    return JSONResponse(_json_safe(lineage))


@app.get("/api/v4/voice/stacks")
async def v4_voice_stacks() -> JSONResponse:
    from solodeck_v4.voice.stacks import list_stacks

    return JSONResponse(_json_safe({"stacks": list_stacks(), "default": "pipecat"}))


@app.post("/api/v4/voice/turn")
async def v4_voice_turn(payload: dict[str, Any]) -> JSONResponse:
    """Text-in simulation: STT transcript → v4 chat → TTS word preview."""
    from solodeck_v4.voice.gateway import make_v4_runner, simulate_voice_turn, stack_wiring_notes
    from solodeck_v4.voice.stacks import get_stack

    transcript = (payload.get("transcript") or payload.get("text") or "").strip()
    if not transcript:
        return JSONResponse({"error": "transcript required"}, status_code=400)
    stack_id = payload.get("stack") or payload.get("stack_id") or "pipecat"
    stack = get_stack(stack_id)

    session_id = payload.get("session_id")
    if not session_id:
        try:
            did, _ = _get_df(payload.get("dataset_id"))
        except KeyError:
            return JSONResponse(
                {"error": "当前数据已不可用，请重新上传原文件后继续提问。"},
                status_code=409,
            )
        session = create_session(dataset_id=did, cost_budget=float(payload.get("cost_budget", 1.0)))
        session_id = session["session_id"]
        V4_SESSIONS[session_id] = did
    did = V4_SESSIONS.get(session_id) or payload.get("dataset_id")
    try:
        _, df = _get_df(did)
    except KeyError:
        return JSONResponse(
            {"error": "当前会话关联的数据已不可用，请重新上传原文件后继续提问。"},
            status_code=409,
        )

    runner = make_v4_runner(df, session_id, TEXTS.get(did or "", ""))
    columns = list(df.columns) if not df.empty else ["platform", "title_style", "consultations"]
    result = simulate_voice_turn(
        transcript,
        stack_id=stack.id,
        runner=runner,
        columns=columns,
        session={"session_id": session_id},
    )
    if not transcript.startswith("请再说一遍"):
        agent = run_v4_agent(transcript, df, session_id, text=TEXTS.get(did or "", ""))
        result["reply"] = agent.get("reply")
        result["user_artifact"] = agent.get("user_artifact")
        result["session_id"] = session_id
        result["tts_preview"] = (result.get("reply") or "")[:280].split()
    result["wiring_notes"] = stack_wiring_notes(stack)
    return JSONResponse(_json_safe(result))
