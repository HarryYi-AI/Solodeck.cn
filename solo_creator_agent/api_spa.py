from __future__ import annotations

import json
import re
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))

from src.agent_orchestrator import find_synthetic_data_dir
from src.agent_workflow import SoloDeckAgentWorkflow
from src.audit_log import read_audit
from src.data_loader import load_contents
from src.mock_data import generate_all
from src.skills import dataset_fingerprint, run_skill_pipeline
from solodeck.workflows.data_agent_graph import run_data_agent_graph
from solodeck_v3.workflows.data_agent_graph import run_v3_data_agent


app = FastAPI(title="SoloDeck Skill API", version="1.0")
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
    for file in files:
        data = await file.read()
        try:
            frames.append(_read_file(file, data))
        except Exception as exc:
            notes.append(f"{file.filename} 未能读取：{exc}")
    text_frame = _text_to_frame(text)
    if not text_frame.empty:
        frames.append(text_frame)
    if not frames:
        return JSONResponse({"error": "没有可读取的 CSV/Excel 文件或文字。", "notes": notes}, status_code=400)
    df = pd.concat(frames, ignore_index=True, sort=False)
    did = dataset_fingerprint(df)
    DATASETS[did] = df
    TEXTS[did] = text
    for key in list(ANALYSIS_CACHE):
        if key.startswith(f"{did}:") or key.startswith(f"agent:{did}:"):
            ANALYSIS_CACHE.pop(key, None)
    result = _run(did)
    final_did = result["dataset_id"]
    DATASETS[final_did] = df
    TEXTS[final_did] = text
    payload = {"dataset_id": final_did, "mapping": result["mapping"], "notes": notes, "trace": result["trace"][:1]}
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
