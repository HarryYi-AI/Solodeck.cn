from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from solodeck_v4.memory import MemoryItem, UnifiedMemory

from .models import AgentState, PlanStep, TaskSpec
from .sources import DataFrameSourceAdapter
from .tools import DataToolRegistry


FIELD_TERMS = {
    "platform": ("平台", "渠道", "platform"),
    "content_type": ("内容类型", "内容形式", "content type", "content_type"),
    "title_style": ("标题", "标题风格", "title style", "title_style"),
    "topic": ("主题", "topic"),
    "favorites": ("收藏", "favorites"),
    "views": ("播放", "阅读", "浏览", "views"),
    "consultations": ("咨询", "consultations"),
    "conversions": ("成交", "转化", "conversions"),
    "revenue": ("收入", "营收", "revenue"),
    "publish_time": ("日期", "时间", "发布", "date", "time", "publish_time"),
}


@dataclass
class CompiledDataTask:
    task: TaskSpec
    group_by: str | None
    metric: str | None
    numerator: str | None
    denominator: str | None
    filters: list[dict[str, Any]]


class InterviewDataAgent:
    """Compact Planner -> Executor -> Critic loop for interview demonstration."""

    def __init__(self, frame: pd.DataFrame, source_id: str, *, project_id: str = "solodeck", session_id: str = "") -> None:
        self.frame = frame
        self.source_id = source_id
        self.project_id = project_id
        self.session_id = session_id
        self.adapter = DataFrameSourceAdapter({source_id: frame}, {source_id: "当前数据集"})
        self.registry = DataToolRegistry(self.adapter)

    def run(self, user_goal: str) -> dict[str, Any]:
        compiled = self.compile(user_goal)
        state = AgentState(task=compiled.task, plan=self.plan(compiled), status="running")
        trace: list[dict[str, Any]] = []
        latest_result: dict[str, Any] = {}
        for index, step in enumerate(state.plan):
            state.current_step = index
            if step.operation == "validate_result":
                step.arguments = {"result": latest_result}
            definition = self.registry.load(step.operation)
            call = self.registry.call(step.operation, step.arguments)
            step.status = call["status"]
            step.observation = call.get("result_summary", "")
            trace.append({
                "step_id": step.step_id,
                "role": "Executor" if step.operation != "validate_result" else "Critic",
                "goal": step.goal,
                "selected_tool": step.operation,
                "jit_schema_loaded": list(definition["parameters"]),
                "arguments": _safe_arguments(step.arguments),
                "status": call["status"],
                "latency_ms": call["latency_ms"],
                "observation": call.get("result_summary"),
            })
            state.observations.append(call)
            if call["status"] == "error":
                state.critique = {"valid": False, "issues": [call.get("error")], "repair": "重新检查字段并改写计划"}
                state.revision_count += 1
                break
            latest_result = call.get("result") or {}
            if step.operation in {"run_python", "run_sql"}:
                state.artifacts.append({"artifact_type": "table", "producer_step": step.step_id, "tool": step.operation, "parameters": _safe_arguments(step.arguments), "summary": call["result_summary"]})
            if step.operation == "validate_result":
                state.critique = latest_result
        state.status = "completed" if state.critique.get("valid", True) else "needs_repair"
        memory_id = self._remember(user_goal, state, trace)
        return {
            "task_spec": compiled.task.to_dict(),
            "plan": [_safe_plan_step(step) for step in state.plan],
            "trace": trace,
            "critique": state.critique,
            "revision_count": state.revision_count,
            "status": state.status,
            "artifact_count": len(state.artifacts),
            "memory_update": memory_id,
            "tool_manifests": self.registry.manifests(),
        }

    def compile(self, user_goal: str) -> CompiledDataTask:
        lowered = user_goal.lower()
        columns = list(self.frame.columns)
        mentioned = [field for field, terms in FIELD_TERMS.items() if field in columns and any(term in lowered for term in terms)]
        group_by = next((field for field in ("content_type", "title_style", "platform", "topic") if field in mentioned), None)
        metric = next((field for field in ("revenue", "conversions", "consultations", "favorites", "views") if field in mentioned), None)
        numerator = denominator = None
        if ("收藏率" in user_goal or "favorites rate" in lowered or "favorite rate" in lowered) and {"favorites", "views"}.issubset(columns):
            numerator, denominator, metric = "favorites", "views", "favorite_rate"
        elif "转化率" in user_goal and "conversions" in columns:
            candidate = next((name for name in ("visitors", "clicks", "consultations", "views") if name in columns), None)
            if candidate: numerator, denominator, metric = "conversions", candidate, "conversion_rate"
        if not group_by:
            group_by = next((name for name in ("platform", "content_type", "title_style", "topic") if name in columns), None)
        if not metric:
            metric = next((name for name in ("revenue", "conversions", "consultations", "favorites", "views") if name in columns), None)
        filters: list[dict[str, Any]] = []
        month = _month(user_goal)
        date_column = next((name for name in ("date", "publish_time", "created_at") if name in columns), None)
        if month and date_column:
            filters.append({"column": date_column, "operator": "month", "value": month})
        operation = "rate" if numerator and denominator else "aggregate"
        task = TaskSpec(
            user_goal=user_goal,
            task_type="descriptive_analysis",
            project_id=self.project_id,
            session_id=self.session_id,
            required_data_sources=[self.source_id],
            candidate_tables=[self.source_id],
            candidate_columns=list(dict.fromkeys([name for name in (group_by, metric, numerator, denominator, date_column) if name])),
            dimensions=[group_by] if group_by else [],
            expected_output=["ranked_table", "validated_answer"],
            required_tools=["list_sources", "inspect_source", "search_source", "run_python", "validate_result"],
            constraints=["do_not_vectorize_structured_data", "validate_denominator"],
            confidence=0.9 if group_by and metric else 0.45,
            ambiguity=[] if group_by and metric else ["未能唯一确定分组或指标"],
        )
        return CompiledDataTask(task, group_by, metric, numerator, denominator, filters)

    def plan(self, compiled: CompiledDataTask) -> list[PlanStep]:
        source = self.source_id
        search_columns = list(dict.fromkeys([name for name in (compiled.group_by, compiled.metric, compiled.numerator, compiled.denominator) if name and name in self.frame.columns]))
        compute = {"source_id": source, "operation": "rate" if compiled.numerator else "aggregate", "group_by": compiled.group_by, "metric": compiled.metric, "numerator": compiled.numerator, "denominator": compiled.denominator, "filters": compiled.filters}
        return [
            PlanStep("发现工作区数据源", "list_sources", expected_output="source list", arguments={}),
            PlanStep("检查字段、类型与缺失率", "inspect_source", source, "schema profile", arguments={"source_id": source}),
            PlanStep("筛选问题相关记录", "search_source", source, "filtered rows", arguments={"source_id": source, "query": {"filters": compiled.filters, "columns": search_columns, "limit": 30}}),
            PlanStep("读取计算所需字段", "read_source", source, "selected columns", arguments={"source_id": source, "selection": {"columns": search_columns, "limit": 30}}),
            PlanStep("执行真实分组计算", "run_python", source, "ranked metric table", arguments=compute),
            PlanStep("检查空结果与分母", "validate_result", expected_output="validation report", arguments={"result": {}}),
        ]

    def _remember(self, goal: str, state: AgentState, trace: list[dict[str, Any]]) -> str | None:
        try:
            item = UnifiedMemory().write_memory(MemoryItem(
                memory_type="episode", project_id=self.project_id, session_id=self.session_id,
                task_id=state.task.task_id, source_type="data_agent", source_id=self.source_id,
                content_summary=f"完成数据任务：{goal[:180]}",
                structured_payload={"tools": [item["selected_tool"] for item in trace], "status": state.status, "critique": state.critique},
                quality_score=0.9 if state.status == "completed" else 0.5,
                retention_policy="project",
            ))
            return item.memory_id
        except Exception:
            return None


def build_agent_trace(user_goal: str, frame: pd.DataFrame, dataset_id: str, *, project_id: str, session_id: str) -> dict[str, Any]:
    return InterviewDataAgent(frame, dataset_id, project_id=project_id, session_id=session_id).run(user_goal)


def _safe_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in arguments.items() if key not in {"result", "rows", "data"}}


def _safe_plan_step(step: PlanStep) -> dict[str, Any]:
    value = step.to_dict()
    value["arguments"] = _safe_arguments(value.get("arguments") or {})
    return value


def _month(text: str) -> int | None:
    english = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
    for name, value in english.items():
        if name in text.lower(): return value
    match = re.search(r"(?:^|\D)(1[0-2]|0?[1-9])\s*月", text)
    return int(match.group(1)) if match else None
