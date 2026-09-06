from __future__ import annotations

import sqlite3
import json

import pandas as pd

from solodeck_runtime.data_agent import InterviewDataAgent
from solodeck_runtime.sources import DataFrameSourceAdapter, FileSourceAdapter
from solodeck_runtime.tools import DataToolRegistry
from solodeck_runtime.repair_demos import silent_join_repair_demo, tool_failure_repair_demo


def test_dataframe_agent_runs_discover_inspect_search_analyze_verify(tmp_path, monkeypatch):
    frame = pd.DataFrame({
        "date": ["2026-08-01", "2026-08-04", "2026-07-04"],
        "content_type": ["教程", "案例", "教程"],
        "views": [100, 100, 50],
        "favorites": [20, 10, 20],
    })
    result = InterviewDataAgent(frame, "content.csv", project_id="test", session_id="s1").run(
        "Which content types improved favorites rate the most in August?"
    )

    assert result["status"] == "completed"
    assert result["critique"]["valid"] is True
    assert [item["selected_tool"] for item in result["trace"]] == [
        "list_sources", "inspect_source", "search_source", "read_source", "run_python", "validate_result"
    ]
    assert result["task_spec"]["candidate_columns"] == ["content_type", "favorite_rate", "favorites", "views", "date"]
    assert result["plan"][2]["arguments"]["query"]["filters"][0]["value"] == 8
    assert all("rows" not in item["arguments"] for item in result["trace"])
    assert '"rows"' not in json.dumps(result, ensure_ascii=False)


def test_tool_registry_uses_progressive_disclosure():
    registry = DataToolRegistry(DataFrameSourceAdapter({"d1": pd.DataFrame({"x": [1]})}))
    manifests = registry.manifests()
    assert {item["name"] for item in manifests} >= {"list_sources", "inspect_source", "search_source", "read_source", "run_python", "run_sql", "retrieve_memory", "validate_result"}
    assert "parameters" not in manifests[0]
    assert registry.load("inspect_source")["parameters"] == {"source_id": "string"}


def test_file_adapter_dispatches_csv_text_and_sqlite(tmp_path):
    pd.DataFrame({"platform": ["A", "B"], "revenue": [10, 20]}).to_csv(tmp_path / "sales.csv", index=False)
    (tmp_path / "notes.md").write_text("# 复盘\n八月收入增长\n退款风险", encoding="utf-8")
    with sqlite3.connect(tmp_path / "orders.db") as db:
        db.execute("CREATE TABLE orders(id INTEGER, amount REAL)")
        db.execute("INSERT INTO orders VALUES (1, 30)")

    adapter = FileSourceAdapter(tmp_path)
    assert {item.source_type for item in adapter.list_sources()} == {"csv", "text", "sqlite"}
    assert adapter.inspect_source("sales.csv")["rows"] == 2
    assert adapter.search_source("notes.md", {"text": "收入"})["matches"][0]["line"] == 2
    sql = adapter.search_source("orders.db", {"sql": "SELECT SUM(amount) AS total FROM orders"})
    assert sql["rows"][0]["total"] == 30


def test_missing_column_becomes_explicit_tool_failure():
    registry = DataToolRegistry(DataFrameSourceAdapter({"d": pd.DataFrame({"views": [1]})}))
    call = registry.call("run_python", {"source_id": "d", "operation": "aggregate", "group_by": "platform", "metric": "views"})
    assert call["status"] == "error"
    assert "missing columns" in call["error"]


def test_two_real_repair_demos_detect_and_fix_failures():
    assert tool_failure_repair_demo()["repair_succeeded"] is True
    joined = silent_join_repair_demo()
    assert joined["critique"]["probes"]["row_inflation"] > 1.2
    assert joined["repair_succeeded"] is True
