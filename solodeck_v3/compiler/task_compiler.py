from __future__ import annotations

from typing import Any

import pandas as pd

from .task_schema import ALL_SKILLS, TaskSpec


def compile_task(user_goal: str, data_sources: pd.DataFrame, memory_context: dict[str, Any] | None = None) -> TaskSpec:
    """Public v3 compiler API required by the runtime spec."""
    return compile_user_goal(user_goal, data_sources, previous_memory=memory_context)


def compile_user_goal(user_goal: str, structured_data: pd.DataFrame, unstructured_text: str = "", previous_memory: dict[str, Any] | None = None) -> TaskSpec:
    columns = list(structured_data.columns)
    goal = (user_goal or "").lower()
    outcome_priority = [
        ("conversion_rate", ["转化率", "成交率", "购买率", "conversion rate"]),
        ("consultation_rate", ["咨询率", "线索率", "consultation rate"]),
        ("favorite_rate", ["收藏率", "保存率", "favorite rate"]),
        ("follow_rate", ["转粉率", "涨粉率", "follow rate"]),
        ("consultations", ["咨询", "线索", "私信", "lead"]),
        ("conversions", ["成交", "转化", "购买", "订单"]),
        ("revenue", ["收入", "收益", "营收", "gmv", "money"]),
        ("favorites", ["收藏", "保存", "favorite"]),
        ("views", ["播放", "阅读", "曝光", "流量", "view"]),
    ]
    treatment_priority = [
        ("title_style", ["标题", "痛点", "教程", "title"]),
        ("platform", ["平台", "渠道", "小红书", "抖音", "b站", "youtube", "tiktok"]),
        ("topic", ["主题", "选题", "内容方向", "topic"]),
        ("publish_time", ["时间", "发布时间", "早上", "晚上", "hour"]),
        ("feature_tags", ["功能", "产品功能", "feature"]),
        ("production_hours", ["制作时间", "制作时长", "成本"]),
    ]
    outcomes = _rank_columns(columns, goal, outcome_priority, ["conversion_rate", "consultation_rate", "favorite_rate", "follow_rate", "revenue", "conversions", "consultations", "favorites", "views"])
    treatments = _rank_columns(columns, goal, treatment_priority, ["platform", "topic", "title_style", "publish_time", "production_hours", "feature_tags"])
    if any(w in goal for w in ["想法", "假设生成", "头脑风暴", "ideation"]):
        task_type = "ideation"
    elif goal.startswith("规划") or "planning" in goal:
        task_type = "planning"
    elif any(w in goal for w in ["实验设计", "设计实验", "experiment design"]):
        task_type = "experiment_design"
    elif any(w in goal for w in ["反事实", "what-if", "如果", "counterfactual", "模拟"]):
        task_type = "counterfactual_analysis"
    elif any(w in goal for w in ["因果", "净增量", "归因", "导致", "ate", "cate", "ab", "实验", "effect", "bootstrap", "置信", "区间", "稳定"]):
        task_type = "causal_effect_estimation"
    elif any(w in goal for w in ["知识图谱", "kg", "graph", "dag", "变量关系", "关系图"]):
        task_type = "causal_hypothesis_generation"
    elif any(w in goal for w in ["假设"]):
        task_type = "causal_hypothesis_generation"
    elif any(w in goal for w in ["计划", "规划", "排期", "planning"]):
        task_type = "planning"
    elif any(w in goal for w in ["写作", "改写", "文案", "writing"]):
        task_type = "writing"
    elif any(w in goal for w in ["数据分析", "分析数据", "data analysis"]):
        task_type = "data_analysis"
    elif any(w in goal for w in ["比较方法", "workflow", "debug", "调试"]):
        task_type = "workflow_debugging"
    elif any(w in goal for w in ["修复", "缺失", "质量", "验证失败", "失败"]):
        task_type = "data_quality_repair"
    elif any(w in goal for w in ["报告", "周报", "复盘"]):
        task_type = "report_generation"
    else:
        task_type = "descriptive_analysis"
    budget = "deep_path" if task_type in {"causal_effect_estimation", "counterfactual_analysis", "workflow_debugging", "causal_hypothesis_generation"} else "normal_path"
    if len(structured_data) < 30 and task_type.startswith("causal"):
        budget = "deep_path"
    expected_artifacts = ["schema_summary", "data_quality_report", "final_report"]
    if task_type in {"causal_hypothesis_generation", "causal_effect_estimation", "counterfactual_analysis", "experiment_design"}:
        expected_artifacts.extend(["kg_context", "causal_readiness", "bootstrap_ci"])
    if task_type == "counterfactual_analysis":
        expected_artifacts.append("counterfactual_simulation")
    return TaskSpec(
        task_type=task_type,
        objective=user_goal or "生成可验证经营行动建议",
        required_data=["structured_table"] + (["unstructured_text"] if unstructured_text.strip() else []),
        candidate_variables=treatments + outcomes,
        candidate_treatments=treatments,
        candidate_outcomes=outcomes or ["revenue"],
        constraints=[
            "KG 只用于解释和约束，不作为因果真相",
            "候选因果图只作为探索性假设",
            "最终建议必须通过隐私与因果有效性校验",
            "置信区间穿过 0 时只能建议验证，不能直接放大",
        ],
        allowed_skills=ALL_SKILLS,
        validation_rules=["artifact", "statistical", "causal", "privacy", "trace", "reward"],
        budget_level=budget,
        expected_artifacts=expected_artifacts,
        unit=_infer_unit(columns),
        time=_infer_time(columns),
        estimand=(f"ATE of {treatments[0]} on {(outcomes or ['revenue'])[0]}" if treatments else None),
    )


def _rank_columns(columns: list[str], goal: str, priorities: list[tuple[str, list[str]]], fallback: list[str]) -> list[str]:
    available = [c for c in fallback if c in columns]
    scored: list[tuple[int, str]] = []
    for idx, col in enumerate(available):
        keywords = next((words for name, words in priorities if name == col), [])
        hit = any(word in goal for word in keywords)
        scored.append((0 if hit else 1, f"{idx:03d}:{col}"))
    ranked = [item.split(":", 1)[1] for _, item in sorted(scored)]
    return ranked


def _infer_unit(columns: list[str]) -> str | None:
    for column in ("content_id", "product_id", "user_id", "account_id", "campaign_id"):
        if column in columns:
            return column
    return "row" if columns else None


def _infer_time(columns: list[str]) -> str | None:
    for column in ("publish_time", "date", "created_at", "timestamp"):
        if column in columns:
            return column
    return None
