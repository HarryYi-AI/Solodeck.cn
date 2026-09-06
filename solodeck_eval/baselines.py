from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from .datasets import BenchmarkCase
from .router import route_tool
from .verifier import EvaluationVerifier


@dataclass(frozen=True)
class Baseline:
    name: str
    mode: str
    note: str


BASELINES = (
    Baseline("A_direct_llm", "direct", "离线确定性代理；未调用外部 LLM，不作为模型能力结论"),
    Baseline("B_react_tools", "react", "逐步选择工具，失败时允许一次回退"),
    Baseline("C_plan_tools", "plan", "先生成显式工具计划，再顺序执行"),
    Baseline("D_solodeck_current", "solodeck", "当前路由、执行与 verifier 的离线评测入口"),
)


def run_baseline(case: BenchmarkCase, baseline: Baseline) -> dict[str, Any]:
    started = perf_counter()
    tool_calls = 0
    execution_errors = 0
    selected_tools = []
    route_metadata: dict[str, Any] = {}
    try:
        if baseline.mode == "direct":
            actual = _direct_proxy(case)
            route_metadata = {"policy": "offline_direct_proxy"}
        elif baseline.mode == "plan":
            action = _planned_tool(case)
            route_metadata = {"policy": "explicit_plan", "action": action}
            selected_tools.append(action)
            tool_calls += 1
            actual = execute_tool(case, action)
        elif baseline.mode == "solodeck":
            from solodeck_v4.routing.hybrid_router import route_task_intent

            columns = list(case.data.columns) if isinstance(case.data, pd.DataFrame) else ["values"]
            semantic = route_task_intent(case.task, columns, allow_llm=False)
            decision = route_tool({"task": case.task, "kind": case.kind, "semantic_route": semantic.to_dict()})
            route_metadata = {"semantic_route": semantic.to_dict(), "physical_route": decision.to_dict()}
            selected_tools.append(decision.action)
            tool_calls += 1
            actual = execute_tool(case, decision.action)
        else:
            decision = route_tool({"task": case.task, "kind": case.kind})
            route_metadata = decision.to_dict()
            selected_tools.append(decision.action)
            tool_calls += 1
            actual = execute_tool(case, decision.action)
            if baseline.mode == "react" and actual is None:
                selected_tools.append("python")
                tool_calls += 1
                actual = execute_tool(case, "python")
        if actual is None:
            raise ValueError("no executable answer")
    except Exception as exc:
        actual = float("nan")
        execution_errors = 1
        error = f"{type(exc).__name__}: {exc}"
    else:
        error = None

    tolerance = 0.35 if case.kind == "causal" else 1e-5
    if case.kind == "causal":
        verification = EvaluationVerifier().causal_ground_truth(actual, case.expected, tolerance=tolerance)
    else:
        verification = EvaluationVerifier().numeric_tolerance(actual, case.expected, atol=tolerance, rtol=1e-5)
    return {
        "task_id": case.task_id,
        "source": case.source,
        "baseline": baseline.name,
        "success": bool(verification["valid"] and not execution_errors),
        "answer": actual,
        "expected": case.expected,
        "tool_calls": tool_calls,
        "selected_tools": selected_tools,
        "route_metadata": route_metadata,
        "execution_error": execution_errors,
        "error": error,
        "latency_ms": round((perf_counter() - started) * 1000, 3),
        "token_usage": 0,
        "token_cost": 0.0,
        "verification": verification,
    }


def execute_tool(case: BenchmarkCase, tool: str) -> float | None:
    if tool == "causal":
        return _adjusted_ate(case.data, case.metadata["treatment"], case.metadata["outcome"], case.metadata["confounders"])
    if tool == "sql" and case.metadata.get("sql"):
        report = EvaluationVerifier().sql_correctness(case.metadata["sql"], {"data": case.data})
        if not report["valid"]:
            return None
        return float(report["details"]["result"][0]["answer"])
    if tool == "python":
        return _python_answer(case)
    return None


def _planned_tool(case: BenchmarkCase) -> str:
    if case.kind == "causal":
        return "causal"
    if case.kind == "sql":
        return "sql"
    return "python"


def _direct_proxy(case: BenchmarkCase) -> float | None:
    if case.kind == "causal":
        frame = case.data
        treatment, outcome = case.metadata["treatment"], case.metadata["outcome"]
        return float(frame.loc[frame[treatment] == 1, outcome].mean() - frame.loc[frame[treatment] == 0, outcome].mean())
    return _python_answer(case)


def _python_answer(case: BenchmarkCase) -> float:
    if isinstance(case.data, pd.DataFrame):
        operation = case.metadata["operation"]
        if operation == "group_max":
            values = case.data.groupby("platform")[case.metadata["metric"]].agg(case.metadata["aggregation"])
            return float(values.max())
    values = np.asarray(case.data)
    operation = case.metadata["operation"]
    functions = {
        "mean": np.mean, "median": np.median, "sum": np.sum, "std": np.std,
        "max": np.max, "min": np.min, "p75": lambda x: np.percentile(x, 75),
        "nonzero": np.count_nonzero, "variance": np.var, "range": lambda x: np.max(x) - np.min(x),
    }
    return float(functions[operation](values))


def _adjusted_ate(frame: pd.DataFrame, treatment: str, outcome: str, confounders: list[str]) -> float:
    columns = [treatment, *confounders]
    x = frame[columns].astype(float).to_numpy()
    x = np.column_stack([np.ones(len(x)), x])
    y = frame[outcome].astype(float).to_numpy()
    coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
    return float(coefficients[1])
