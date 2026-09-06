from __future__ import annotations

import ast
import math
import re
import sqlite3
from typing import Any

import numpy as np
import pandas as pd


class EvaluationVerifier:
    """Executable checks used by the benchmark and trajectory reward layer."""

    def python_correctness(
        self,
        code: str,
        *,
        context: dict[str, Any] | None = None,
        result_variable: str | None = None,
        expected: Any = None,
    ) -> dict[str, Any]:
        """Execute trusted benchmark snippets in a restricted namespace."""
        try:
            tree = ast.parse(code)
            if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
                return _report(False, "评测代码不允许动态导入")
            compiled = compile(tree, "<benchmark>", "exec")
            namespace = {"np": np, "pd": pd, "len": len, "sum": sum, "min": min, "max": max, "abs": abs}
            namespace.update(context or {})
            exec(compiled, {"__builtins__": {}}, namespace)
            actual = namespace.get(result_variable) if result_variable else None
            if result_variable and result_variable not in namespace:
                return _report(False, f"Python 未生成结果变量：{result_variable}")
            if result_variable and expected is not None:
                comparison = self.numeric_tolerance(actual, expected)
                return _report(comparison["valid"], comparison["message"], actual=actual, comparison=comparison)
            return _report(True, "Python 代码执行成功", result=actual)
        except Exception as exc:
            return _report(False, f"Python 执行失败：{type(exc).__name__}: {exc}")

    def sql_correctness(self, sql: str, tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
        try:
            with sqlite3.connect(":memory:") as connection:
                for name, frame in tables.items():
                    frame.to_sql(name, connection, index=False)
                result = pd.read_sql_query(sql, connection)
            return _report(True, "SQL 执行成功", rows=len(result), result=result.to_dict("records")[:20])
        except Exception as exc:
            return _report(False, f"SQL 执行失败：{type(exc).__name__}: {exc}")

    def numeric_tolerance(self, actual: Any, expected: Any, *, atol: float = 1e-6, rtol: float = 1e-4) -> dict[str, Any]:
        try:
            valid = bool(np.allclose(np.asarray(actual, dtype=float), np.asarray(expected, dtype=float), atol=atol, rtol=rtol, equal_nan=True))
            error = float(np.max(np.abs(np.asarray(actual, dtype=float) - np.asarray(expected, dtype=float))))
            return _report(valid, "数值在容差内" if valid else "数值超出容差", max_abs_error=error, atol=atol, rtol=rtol)
        except Exception as exc:
            return _report(False, f"数值比较失败：{exc}")

    def dataframe_consistency(self, actual: pd.DataFrame, expected: pd.DataFrame, *, check_order: bool = False) -> dict[str, Any]:
        left, right = actual.copy(), expected.copy()
        if not check_order:
            columns = sorted(set(left.columns) | set(right.columns))
            if set(left.columns) != set(right.columns):
                return _report(False, "DataFrame 列不一致", actual_columns=list(left.columns), expected_columns=list(right.columns))
            left = left[columns].sort_values(columns).reset_index(drop=True)
            right = right[columns].sort_values(columns).reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(left, right, check_dtype=False, atol=1e-6, rtol=1e-4)
            return _report(True, "DataFrame 与期望结果一致", rows=len(left))
        except AssertionError as exc:
            return _report(False, f"DataFrame 结果不一致：{str(exc)[:240]}")

    def report_number_consistency(self, report: str, artifact_numbers: list[float], *, tolerance: float = 0.02) -> dict[str, Any]:
        mentioned = [float(item.replace(",", "")) for item in re.findall(r"(?<![A-Za-z_])-?\d+(?:,\d{3})*(?:\.\d+)?", report or "")]
        unmatched = [value for value in mentioned if not any(math.isclose(value, expected, abs_tol=tolerance, rel_tol=tolerance) for expected in artifact_numbers)]
        return _report(not unmatched, "报告数字均可追溯" if not unmatched else "报告包含无法追溯的数字", mentioned=mentioned, unmatched=unmatched)

    def causal_ground_truth(self, estimate: float, true_ate: float, *, tolerance: float = 0.35, ci: list[float] | None = None) -> dict[str, Any]:
        absolute_error = abs(float(estimate) - float(true_ate))
        relative_error = absolute_error / max(abs(float(true_ate)), 1e-9)
        covered = bool(ci and len(ci) == 2 and float(ci[0]) <= true_ate <= float(ci[1]))
        valid = absolute_error <= tolerance or relative_error <= tolerance
        return _report(valid, "ATE 接近 SCM 真值" if valid else "ATE 偏离 SCM 真值", absolute_error=absolute_error, relative_error=relative_error, ci_covers_truth=covered)


def _report(valid: bool, message: str, **details: Any) -> dict[str, Any]:
    return {"valid": bool(valid), "message": message, "details": details}
