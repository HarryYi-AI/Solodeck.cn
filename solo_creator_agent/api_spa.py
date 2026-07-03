from __future__ import annotations

import json
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile
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
from solodeck.workflows.data_agent_graph import run_data_agent_graph
from solodeck_v3.workflows.data_agent_graph import run_v3_data_agent
from solodeck_v4.runtime.runner import create_session, run_v4_agent
from solodeck_v4.tools.registry import list_tools
from solodeck_v4.session.store import get_session


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
    return mime.startswith("text/") or name.endswith((".txt", ".md", ".json"))


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
    df = _load_default()
    did = dataset_fingerprint(df)
    DATASETS[did] = df
    return did, df


def _run(dataset_id: str | None, question_id: str = "pain_point_title") -> dict[str, Any]:
    did, df = _get_df(dataset_id)
    key = f"{did}:{question_id}"
    if key not in ANALYSIS_CACHE:
        ANALYSIS_CACHE[key] = run_skill_pipeline(df, question_id=question_id)
    return ANALYSIS_CACHE[key]


def _run_agent(dataset_id: str | None, question_id: str = "pain_point_title") -> dict[str, Any]:
    did, df = _get_df(dataset_id)
    key = f"agent:{did}:{question_id}"
    if key not in ANALYSIS_CACHE:
        ANALYSIS_CACHE[key] = SoloDeckAgentWorkflow().run(df, question_id=question_id, unstructured_text=TEXTS.get(did, ""))
    return ANALYSIS_CACHE[key]


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "SoloDeck Skill API"}


@app.get("/api/demo")
def demo() -> JSONResponse:
    result = _run(None)
    return JSONResponse(_json_safe({"dataset_id": result["dataset_id"], "mapping": result["mapping"]}))


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(default=[]), text: str = Form(default="")) -> JSONResponse:
    frames = []
    notes = []
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
    df = pd.concat(frames, ignore_index=True, sort=False)
    did = dataset_fingerprint(df)
    DATASETS[did] = df
    TEXTS[did] = full_text
    for key in list(ANALYSIS_CACHE):
        if key.startswith(f"{did}:") or key.startswith(f"agent:{did}:"):
            ANALYSIS_CACHE.pop(key, None)
    result = _run(did)
    final_did = result["dataset_id"]
    DATASETS[final_did] = df
    TEXTS[final_did] = full_text
    payload = {
        "dataset_id": final_did,
        "mapping": result["mapping"],
        "notes": notes,
        "tasks": extracted_tasks,
        "trace": result["trace"][:1],
    }
    return JSONResponse(_json_safe(payload))


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
async def v4_create_session(payload: dict[str, Any]) -> JSONResponse:
    did, _ = _get_df(payload.get("dataset_id"))
    session = create_session(dataset_id=did, cost_budget=float(payload.get("cost_budget", 1.0)))
    V4_SESSIONS[session["session_id"]] = did
    return JSONResponse(_json_safe(session))


@app.get("/api/v4/session/{session_id}")
async def v4_get_session(session_id: str) -> JSONResponse:
    session = get_session(session_id)
    if not session:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return JSONResponse(_json_safe(session))


@app.get("/api/v4/tools")
async def v4_tools() -> JSONResponse:
    return JSONResponse(_json_safe({"tools": list_tools(), "version": "4.0.0"}))


@app.post("/api/v4/chat")
async def v4_chat(payload: dict[str, Any]) -> JSONResponse:
    message = (payload.get("message") or payload.get("task") or "").strip()
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)
    session_id = payload.get("session_id")
    if not session_id:
        did, _ = _get_df(payload.get("dataset_id"))
        session = create_session(dataset_id=did, cost_budget=float(payload.get("cost_budget", 1.0)))
        session_id = session["session_id"]
        V4_SESSIONS[session_id] = did
    did = V4_SESSIONS.get(session_id) or payload.get("dataset_id")
    _, df = _get_df(did)
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
        "cost_spent": result.get("cost_spent"),
        "session_cost_total": result.get("session_cost_total"),
        "version": result.get("version"),
    }
    return JSONResponse(_json_safe(safe))


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
async def v4_memory_trace(project_id: str = "solodeck", session_id: str | None = None) -> JSONResponse:
    from solodeck_v4.memory import UnifiedMemory

    rows = UnifiedMemory().export_memory_trace(project_id, session_id)
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
    return JSONResponse(_json_safe({"project_id": project_id, "session_id": session_id, "items": safe}))


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
        did, _ = _get_df(payload.get("dataset_id"))
        session = create_session(dataset_id=did, cost_budget=float(payload.get("cost_budget", 1.0)))
        session_id = session["session_id"]
        V4_SESSIONS[session_id] = did
    did = V4_SESSIONS.get(session_id) or payload.get("dataset_id")
    _, df = _get_df(did)

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
