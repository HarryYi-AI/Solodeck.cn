from __future__ import annotations

from typing import Any


def build_result_view(state: dict[str, Any]) -> dict[str, Any]:
    """Convert internal artifacts into display-safe table/chart payloads."""
    artifacts = state.get("artifacts") or []
    comparison = _artifact(artifacts, "descriptive_comparison")
    if comparison.get("ranking"):
        scale = float(comparison.get("display_scale") or 1.0)
        limit = max(1, min(int(comparison.get("requested_limit") or 12), 20))
        rows = [{
            "name": row.get("group"),
            "value": round(float(row.get("value", 0)) * scale, 3),
            "sample_size": int(row.get("sample_size", 0)),
        } for row in comparison["ranking"][:limit]]
        suffix = "%" if comparison.get("is_rate") else ""
        return {
            "kind": "ranking",
            "title": f"{comparison.get('group_label', '分组')} · {comparison.get('metric_label', '指标')}",
            "columns": ["name", "value", "sample_size"],
            "column_labels": {"name": comparison.get("group_label", "分组"), "value": comparison.get("metric_label", "数值"), "sample_size": "样本量"},
            "rows": rows,
            "chart": {"type": "bar", "x": "name", "y": "value", "suffix": suffix, "data": rows},
        }
    effect = _artifact(artifacts, "bootstrap_ci") or _artifact(artifacts, "regression_effect")
    if effect:
        estimate = _first(effect, "adjusted_effect", "effect_estimate", "ate")
        ci = effect.get("ci_95") or [effect.get("ci_low"), effect.get("ci_high")]
        rows = [
            {"metric": "调整后估计", "value": estimate},
            {"metric": "区间下限", "value": ci[0] if len(ci) == 2 else None},
            {"metric": "区间上限", "value": ci[1] if len(ci) == 2 else None},
            {"metric": "样本量", "value": effect.get("sample_size")},
        ]
        return {
            "kind": "estimate", "title": "策略效果估计",
            "columns": ["metric", "value"], "column_labels": {"metric": "指标", "value": "结果"},
            "rows": rows, "chart": {"type": "interval", "estimate": estimate, "ci": ci},
        }
    insights = _artifact(artifacts, "auto_insights")
    if insights.get("observations"):
        rows = [{"finding": item} for item in insights["observations"]]
        return {
            "kind": "insights", "title": "自动数据洞察",
            "columns": ["finding"], "column_labels": {"finding": "发现"},
            "rows": rows, "chart": None,
        }
    quality = _artifact(artifacts, "data_quality_report")
    if quality:
        rows = [
            {"field": field, "missing_rate": round(float(rate) * 100, 2)}
            for field, rate in (quality.get("missing_rate") or {}).items()
        ]
        return {
            "kind": "quality", "title": "字段缺失检查",
            "columns": ["field", "missing_rate"],
            "column_labels": {"field": "字段", "missing_rate": "缺失率（%）"},
            "rows": rows, "chart": {"type": "bar", "x": "field", "y": "missing_rate", "suffix": "%", "data": rows[:12]},
        }
    report = state.get("user_artifact") or {}
    return {
        "kind": "report", "title": report.get("title") or "分析结果",
        "columns": [], "column_labels": {}, "rows": [], "chart": None,
    }


def _artifact(artifacts: list[dict[str, Any]], artifact_id: str) -> dict[str, Any]:
    item = next((row for row in artifacts if row.get("id") == artifact_id), {})
    return item.get("content", item) if item else {}


def _first(value: dict[str, Any], *keys: str) -> Any:
    return next((value.get(key) for key in keys if value.get(key) is not None), None)
