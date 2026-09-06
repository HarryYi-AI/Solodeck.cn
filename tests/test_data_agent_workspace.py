from __future__ import annotations

import pandas as pd

from solodeck_runtime.result_view import build_result_view
from solodeck_runtime.workspace import DataWorkspaceRepository, profile_dataframe
from solodeck_v3.compiler.task_compiler import compile_user_goal
from solodeck_v3.skills.descriptive_comparison_skill import DescriptiveComparisonSkill
from solodeck_v3.skills.report_skill import ReportSkill


def test_workspace_catalog_isolated_and_persistent(tmp_path):
    database = tmp_path / "workspace.db"
    frame = pd.DataFrame({"platform": ["小红书", "抖音"], "conversions": [3, 5]})
    repository = DataWorkspaceRepository(database)
    dataset = repository.register_dataset("workspace_a", "dataset_12345678", "orders.csv", "文件上传", tmp_path / "orders.csv", frame)

    assert dataset["row_count"] == 2
    assert repository.list_datasets("workspace_b") == []
    assert DataWorkspaceRepository(database).get_dataset("workspace_a", "dataset_12345678")["name"] == "orders.csv"


def test_workspace_run_keeps_display_safe_result(tmp_path):
    repository = DataWorkspaceRepository(tmp_path / "workspace.db")
    result = {
        "session_id": "session-1",
        "state_id": "state-1",
        "task_spec": {"task_type": "descriptive_comparison"},
        "tool_calls": [{"tool": "Describe"}, {"tool": "ValidateClaim"}],
        "validation_report": {"block_output": False},
        "reply": "小红书转化率最高。",
    }
    view = {"kind": "ranking", "rows": [{"name": "小红书", "value": 4.0}]}
    saved = repository.save_run("workspace_a", "dataset_12345678", "哪个平台转化更好", result, view, 12.5)

    assert saved["status"] == "completed"
    assert saved["selected_tools"] == ["Describe", "ValidateClaim"]
    assert repository.list_runs("workspace_a")[0]["result_view"] == view


def test_profile_and_result_view_are_computed_from_artifacts():
    frame = pd.DataFrame({"platform": ["小红书", "抖音", "抖音"], "rate": [0.04, 0.02, None]})
    profile = profile_dataframe(frame)
    state = {
        "artifacts": [{
            "id": "descriptive_comparison",
            "content": {
                "group_label": "平台",
                "metric_label": "转化率",
                "is_rate": True,
                "display_scale": 100,
                "ranking": [
                    {"group": "小红书", "value": 0.04, "sample_size": 1},
                    {"group": "抖音", "value": 0.02, "sample_size": 2},
                ],
            },
        }],
    }
    view = build_result_view(state)

    assert profile["missing_cells"] == 1
    assert view["kind"] == "ranking"
    assert view["rows"][0]["value"] == 4.0
    assert view["chart"]["suffix"] == "%"


def test_general_data_question_uses_requested_metric_and_entity():
    frame = pd.DataFrame({
        "content_id": ["a", "b", "c"],
        "title": ["内容甲", "内容乙", "内容丙"],
        "platform": ["小红书", "抖音", "抖音"],
        "revenue": [20, 80, 40],
        "conversions": [1, 9, 4],
    })
    message = "收入最高的2条内容是什么？"
    spec = compile_user_goal(message, frame).to_dict()
    output = DescriptiveComparisonSkill().run({"df": frame, "task_spec": spec, "message": message})

    assert output.content["group_by"] == "title"
    assert output.content["metric"] == "revenue"
    assert output.content["ranking"][0]["group"] == "内容乙"
    assert output.content["requested_limit"] == 2


def test_data_quality_report_does_not_fall_back_to_causal_effect():
    state = {
        "task_spec": {"task_type": "data_quality_repair", "objective": "检查数据质量"},
        "artifacts": [{
            "id": "data_quality_report",
            "content": {"rows": 3, "columns": 2, "missing_rate": {"revenue": 1 / 3}, "warnings": []},
        }],
    }
    report = ReportSkill().run(state).content

    assert "3 行、2 列" in report["result"]
    assert "增量" not in report["result"]
