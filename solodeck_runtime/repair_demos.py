from __future__ import annotations

from typing import Any

import pandas as pd

from .sources import DataFrameSourceAdapter
from .tools import DataToolRegistry
from .verifier import ActiveVerifier


def tool_failure_repair_demo() -> dict[str, Any]:
    """Repair a missing derived metric by inspecting schema and changing the tool call."""
    frame = pd.DataFrame({"content_type": ["教程", "案例"], "favorites": [20, 8], "views": [100, 80]})
    registry = DataToolRegistry(DataFrameSourceAdapter({"contents": frame}))
    failed = registry.call("run_python", {
        "source_id": "contents", "operation": "aggregate",
        "group_by": "content_type", "metric": "favorite_rate",
    })
    schema = registry.call("inspect_source", {"source_id": "contents"})
    repaired = registry.call("run_python", {
        "source_id": "contents", "operation": "rate", "group_by": "content_type",
        "numerator": "favorites", "denominator": "views",
    })
    validation = registry.call("validate_result", {"result": repaired.get("result")})
    return {
        "failure": failed,
        "critique": {"cause": "favorite_rate 不存在，但分子和分母可用", "repair": "改为 favorites / views 派生计算"},
        "schema_observation": schema["result_summary"],
        "repair": repaired,
        "validation": validation["result"],
        "repair_succeeded": repaired["status"] == "success" and validation["result"]["valid"],
    }


def silent_join_repair_demo() -> dict[str, Any]:
    """Detect a successful but analytically wrong many-to-many join and repair it."""
    left = pd.DataFrame({"content_id": ["a", "a", "b"], "views": [10, 20, 30]})
    right = pd.DataFrame({"content_id": ["a", "a", "b"], "revenue": [5, 7, 9]})
    verifier = ActiveVerifier()
    initial = left.merge(right, on="content_id", how="left")
    critique = verifier.inspect_join(left, right, left_on="content_id", right_on="content_id", result=initial)
    repaired_left = left.groupby("content_id", as_index=False)["views"].sum()
    repaired_right = right.groupby("content_id", as_index=False)["revenue"].sum()
    repaired = repaired_left.merge(repaired_right, on="content_id", how="left")
    validation = verifier.inspect_join(repaired_left, repaired_right, left_on="content_id", right_on="content_id", result=repaired)
    return {
        "initial_rows": len(initial),
        "critique": critique,
        "repair": "连接前按 content_id 聚合两侧数据",
        "repaired_rows": len(repaired),
        "validation": validation,
        "repair_succeeded": not critique["valid"] and validation["valid"],
    }
