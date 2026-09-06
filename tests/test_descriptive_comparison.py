from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi import UploadFile
from starlette.datastructures import Headers

from solodeck_v3.compiler.task_compiler import compile_user_goal
from solodeck_v3.planning.method_planner import generate_candidate_plans
from solodeck_v3.skills.descriptive_comparison_skill import DescriptiveComparisonSkill
from solodeck_v4.compiler.enhanced_compiler import compile_with_session
from solodeck_v4.retrieval.retrieval_router import classify_intent, route_sources
from solodeck_v4.risk.risk_router import assess_risk
from solodeck_v4.runtime.runner import _missing_estimand_fields
from solo_creator_agent.api_spa import _is_text_file
from solo_creator_agent.src.skills import DataMappingSkill


def platform_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "platform": ["美团", "拼多多", "淘宝", "京东", "抖音", "快手"],
            "conversion_rate": [4.0, 2.8, 2.7, 1.8, 1.5, 1.4],
            "visitors": [1000] * 6,
        }
    )


def test_plain_ranking_question_is_not_upgraded_to_causal() -> None:
    df = platform_data()
    spec = compile_with_session("哪个平台转化更好？", df)
    assert spec.task_type == "descriptive_analysis"
    assert spec.candidate_outcomes[0] == "conversion_rate"
    risk = assess_risk("哪个平台转化更好？", spec.to_dict(), {}, {"ready": True})
    assert risk["high_risk"] is False
    assert classify_intent("哪个平台转化更好？", spec.to_dict()) == "comparison_question"
    assert route_sources("comparison_question") == ["artifact", "schema", "session"]


def test_causal_wording_still_uses_causal_path() -> None:
    df = platform_data()
    spec = compile_with_session("美团转化高是因为平台本身导致的吗？", df)
    assert spec.task_type == "causal_effect_estimation"
    risk = assess_risk("美团转化高是因为平台本身导致的吗？", spec.to_dict(), {}, {"ready": True})
    assert risk["high_risk"] is True


def test_plain_title_strategy_comparison_stays_descriptive() -> None:
    df = pd.DataFrame({
        "content_id": ["a", "b", "c", "d", "e", "f"],
        "platform": ["xiaohongshu"] * 4 + ["douyin"] * 2,
        "title_style": ["pain_point", "pain_point", "tutorial", "tutorial", "pain_point", "tutorial"],
        "consultations": [20, 10, 5, 5, 1000, 2000],
    })
    message = "小红书痛点标题是不是比教程标题更能带来咨询？"
    spec = compile_with_session(message, df)
    risk = assess_risk(message, spec.to_dict(), {}, {"ready": True})
    output = DescriptiveComparisonSkill().run({"df": df, "task_spec": spec.to_dict(), "message": message})

    assert spec.task_type == "descriptive_analysis"
    assert risk["high_risk"] is False
    assert [row["group"] for row in output.content["ranking"]] == ["痛点型", "教程型"]
    assert output.content["ranking"][0]["value"] == 15
    assert output.content["aggregation"] == "平均值"
    assert output.content["sample_size"] == 4
    assert output.content["scope"] == {"platform": "小红书"}


def test_descriptive_skill_ranks_and_computes_ratio() -> None:
    df = platform_data()
    spec = compile_user_goal("哪个平台转化更好？", df).to_dict()
    output = DescriptiveComparisonSkill().run({"df": df, "task_spec": spec})
    assert output.valid is True
    assert output.content["best"]["group"] == "美团"
    assert output.content["worst"]["group"] == "快手"
    assert round(output.content["best_to_worst_ratio"], 1) == 2.9
    assert output.content["display_scale"] == 1.0


def test_descriptive_skill_derives_rate_from_counts() -> None:
    df = pd.DataFrame(
        {
            "platform": ["A", "B"],
            "visitors": [1000, 1000],
            "conversions": [40, 15],
        }
    )
    spec = compile_user_goal("哪个平台转化率更高？", df).to_dict()
    output = DescriptiveComparisonSkill().run({"df": df, "task_spec": spec})
    assert output.valid is True
    assert output.content["metric"] == "conversion_rate"
    assert output.content["display_scale"] == 100.0
    assert output.content["ranking"][0]["value"] == 0.04


def test_descriptive_plan_executes_real_comparison_skill() -> None:
    df = platform_data()
    spec = compile_user_goal("哪个平台转化更好？", df).to_dict()
    plans = generate_candidate_plans(spec, {}, {"max_plans": 1})
    assert "DescriptiveComparisonSkill" in plans[0]["skills"]


def test_csv_mime_is_not_misclassified_as_unstructured_text() -> None:
    upload = UploadFile(file=BytesIO(b"platform,conversion_rate"), filename="platforms.csv", headers=Headers({"content-type": "text/csv"}))
    assert _is_text_file(upload) is False


def test_missing_time_does_not_block_observational_effect_estimate() -> None:
    spec = {
        "task_type": "causal_effect_estimation",
        "candidate_treatments": ["title_style"],
        "candidate_outcomes": ["consultations"],
        "unit": "content_id",
        "time": None,
    }
    assert _missing_estimand_fields(spec) == []


def test_missing_rate_denominators_are_not_treated_as_zero() -> None:
    df = pd.DataFrame(
        {
            "platform": ["douyin", "wechat", "xiaohongshu"],
            "views": [0, 0, 0],
            "consultations": [0, 2, 0],
            "conversions": [0, 1, 0],
        }
    )
    spec = compile_user_goal("哪个平台转化更好？", df).to_dict()
    output = DescriptiveComparisonSkill().run({"df": df, "task_spec": spec})
    assert output.content["status"] == "insufficient_comparison"
    assert len(output.content["ranking"]) == 1
    assert output.content["ranking"][0]["group"] == "公众号/视频号"
    assert output.content["ranking"][0]["value"] == 0.5
    assert output.content["unavailable_groups"] == 2


def test_equal_zero_rates_do_not_produce_a_false_winner() -> None:
    df = pd.DataFrame(
        {
            "platform": ["A", "B"],
            "conversion_rate": [0.0, 0.0],
        }
    )
    spec = compile_user_goal("哪个平台转化更好？", df).to_dict()
    output = DescriptiveComparisonSkill().run({"df": df, "task_spec": spec})
    assert output.content["status"] == "tie"


def test_schema_mapping_preserves_missing_numeric_values() -> None:
    mapped = DataMappingSkill().run(pd.DataFrame({"platform": ["douyin"], "conversions": [0]}))["data"]
    assert pd.isna(mapped.loc[0, "conversion_rate"])
    assert mapped.loc[0, "conversions"] == 0
