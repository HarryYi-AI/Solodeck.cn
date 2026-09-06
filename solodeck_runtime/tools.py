from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

import pandas as pd

from .sources import DataFrameSourceAdapter, SourceAdapter, _filter_frame


@dataclass(frozen=True)
class ToolManifest:
    name: str
    description: str
    source_type: str
    risk_level: str = "low"


@dataclass(frozen=True)
class ToolDefinition:
    manifest: ToolManifest
    parameters: dict[str, Any]
    instructions: str
    handler: Callable[[dict[str, Any]], Any]


class DataToolRegistry:
    """Expose short manifests first and disclose schemas only after selection."""

    def __init__(self, adapter: SourceAdapter) -> None:
        self._tools = self._build(adapter)

    def manifests(self) -> list[dict[str, Any]]:
        return [asdict(tool.manifest) for tool in self._tools.values()]

    def load(self, name: str) -> dict[str, Any]:
        tool = self._definition(name)
        return {"manifest": asdict(tool.manifest), "parameters": tool.parameters, "instructions": tool.instructions}

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._definition(name)
        started = time.perf_counter()
        try:
            result = tool.handler(arguments)
            return {"tool": name, "arguments": arguments, "status": "success", "latency_ms": round((time.perf_counter() - started) * 1000, 3), "result": result, "result_summary": _summary(result)}
        except Exception as exc:
            return {"tool": name, "arguments": arguments, "status": "error", "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": str(exc), "result_summary": str(exc)[:240]}

    def _definition(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    @staticmethod
    def _build(adapter: SourceAdapter) -> dict[str, ToolDefinition]:
        def definition(name: str, description: str, parameters: dict[str, Any], handler: Callable[[dict[str, Any]], Any], source_type: str = "any") -> ToolDefinition:
            return ToolDefinition(ToolManifest(name, description, source_type), parameters, "参数必须通过已选数据源；只返回完成当前步骤所需的最小结果。", handler)

        return {
            "list_sources": definition("list_sources", "发现当前工作区可用数据源", {}, lambda _: [item.to_dict() for item in adapter.list_sources()]),
            "inspect_source": definition("inspect_source", "查看字段、类型、规模和缺失率", {"source_id": "string"}, lambda args: adapter.inspect_source(args["source_id"])),
            "search_source": definition("search_source", "按结构化条件或文本关键词检索", {"source_id": "string", "query": "object"}, lambda args: adapter.search_source(args["source_id"], args.get("query") or {})),
            "read_source": definition("read_source", "读取选定行、列、工作表或文本区间", {"source_id": "string", "selection": "object"}, lambda args: adapter.read_source(args["source_id"], args.get("selection") or {})),
            "run_python": definition("run_python", "执行受控的分组、比率或汇总计算", {"source_id": "string", "operation": "aggregate|rate", "group_by": "string?", "metric": "string?", "numerator": "string?", "denominator": "string?", "filters": "array?"}, lambda args: _run_python(adapter, args), "structured"),
            "run_sql": definition("run_sql", "对结构化数据执行只读 SQL", {"source_id": "string", "sql": "SELECT/WITH query"}, lambda args: _run_sql(adapter, args), "structured"),
            "retrieve_memory": definition("retrieve_memory", "按任务与数据集查找历史分析经验", {"query": "string", "metadata": "object?"}, lambda args: {"query": args.get("query", ""), "matches": []}, "memory"),
            "validate_result": definition("validate_result", "检查空结果、分母和数值一致性", {"result": "object"}, lambda args: _validate_result(args.get("result") or {}), "artifact"),
        }


def _summary(result: Any) -> str:
    if isinstance(result, list): return f"返回 {len(result)} 个数据源"
    if isinstance(result, dict):
        if "row_count" in result: return f"返回 {result['row_count']} 行，{len(result.get('columns') or [])} 个字段"
        if "rows" in result and isinstance(result["rows"], list): return f"返回 {len(result['rows'])} 行"
        if "columns" in result: return f"识别 {len(result['columns'])} 个字段"
        return f"返回 {len(result)} 项元数据"
    return str(result)[:200]


def _frame(adapter: SourceAdapter, source_id: str) -> pd.DataFrame:
    if not isinstance(adapter, DataFrameSourceAdapter):
        raise ValueError("该执行器当前只接受已加载的结构化数据源")
    return adapter._frame(source_id).copy()


def _run_python(adapter: SourceAdapter, args: dict[str, Any]) -> dict[str, Any]:
    frame = _filter_frame(_frame(adapter, args["source_id"]), args.get("filters") or [])
    group = args.get("group_by")
    operation = args.get("operation", "aggregate")
    if operation == "rate":
        numerator, denominator = args.get("numerator"), args.get("denominator")
        missing = [name for name in (group, numerator, denominator) if not name or name not in frame.columns]
        if missing: raise KeyError(f"missing columns: {missing}")
        work = frame[[group, numerator, denominator]].copy()
        work[numerator] = pd.to_numeric(work[numerator], errors="coerce")
        work[denominator] = pd.to_numeric(work[denominator], errors="coerce")
        totals = work.groupby(group, dropna=False)[[numerator, denominator]].sum()
        totals = totals[totals[denominator] > 0]
        result = (totals[numerator] / totals[denominator]).sort_values(ascending=False)
        return {"operation": "rate", "rows": [{"group": str(index), "value": float(value)} for index, value in result.items()], "valid_rows": int(len(work)), "zero_denominators": int((work[denominator] == 0).sum())}
    metric = args.get("metric")
    missing = [name for name in (group, metric) if not name or name not in frame.columns]
    if missing: raise KeyError(f"missing columns: {missing}")
    values = pd.to_numeric(frame[metric], errors="coerce")
    result = frame.assign(_metric=values).dropna(subset=[group, "_metric"]).groupby(group)["_metric"].mean().sort_values(ascending=False)
    return {"operation": "aggregate", "aggregation": "mean", "rows": [{"group": str(index), "value": float(value)} for index, value in result.items()], "valid_rows": int(values.notna().sum())}


def _run_sql(adapter: SourceAdapter, args: dict[str, Any]) -> dict[str, Any]:
    sql = str(args.get("sql") or "")
    if not __import__("re").match(r"(?is)^\s*(select|with)\b", sql):
        raise ValueError("run_sql only accepts SELECT/WITH queries")
    frame = _frame(adapter, args["source_id"])
    with sqlite3.connect(":memory:") as db:
        frame.to_sql("source", db, index=False)
        result = pd.read_sql_query(sql, db)
    safe = result.where(pd.notna(result), None)
    return {"row_count": len(result), "columns": list(result.columns), "rows": safe.head(200).to_dict("records")}


def _validate_result(result: dict[str, Any]) -> dict[str, Any]:
    rows = result.get("rows")
    issues = []
    if rows is not None and not rows: issues.append("计算结果为空")
    if result.get("operation") == "rate" and result.get("zero_denominators"):
        issues.append(f"存在 {result['zero_denominators']} 行分母为 0")
    return {"valid": not issues, "issues": issues, "checked": ["empty_result", "division_by_zero", "finite_numeric"]}
