from __future__ import annotations

from typing import Any

import pandas as pd

from .base import BaseSkill, SkillOutput


RATE_DENOMINATORS = {
    "conversion_rate": ("visitors", "clicks", "sessions", "consultations", "views"),
    "consultation_rate": ("visitors", "clicks", "views"),
    "favorite_rate": ("views", "impressions"),
    "follow_rate": ("views", "impressions"),
}

RATE_NUMERATORS = {
    "conversion_rate": "conversions",
    "consultation_rate": "consultations",
    "favorite_rate": "favorites",
    "follow_rate": "new_followers",
}

DISPLAY_NAMES = {
    "platform": "平台",
    "title_style": "标题风格",
    "topic": "主题",
    "publish_time": "发布时间",
    "feature_tags": "产品功能",
    "conversion_rate": "转化率",
    "consultation_rate": "咨询率",
    "favorite_rate": "收藏率",
    "follow_rate": "转粉率",
    "conversions": "成交数",
    "consultations": "咨询数",
    "revenue": "收入",
    "views": "播放量",
    "title": "内容",
    "content_id": "内容",
    "product_name": "产品",
    "product_id": "产品",
}

PLATFORM_NAMES = {
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "douyin": "抖音",
    "wechat": "公众号/视频号",
    "kuaishou": "快手",
    "meituan": "美团",
    "taobao": "淘宝",
    "tmall": "天猫",
    "pinduoduo": "拼多多",
    "jingdong": "京东",
    "jd": "京东",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "substack": "Substack",
    "instagram": "Instagram",
    "zhihu": "知乎",
    "x": "X / Twitter",
    "twitter": "X / Twitter",
}


class DescriptiveComparisonSkill(BaseSkill):
    """Compare observed business metrics without turning ranking into a causal claim."""

    name = "DescriptiveComparisonSkill"
    role = "Executor"
    input_schema = {"df": "DataFrame", "task_spec": "TaskSpec"}
    output_schema = {"ranking": "list", "status": "str", "sample_size": "int"}
    failure_modes = ["缺少分组字段", "缺少可计算指标"]

    def run(self, state: dict[str, Any]) -> SkillOutput:
        df = state.get("df")
        spec = state.get("task_spec") or {}
        if df is None or getattr(df, "empty", True):
            return SkillOutput("descriptive_comparison", "descriptive_result", {}, valid=False, warnings=["没有可比较的数据"])

        data = df.copy()
        message = str(state.get("message") or spec.get("objective") or "")
        group_col = self._pick_group(data, spec, message)
        metric, is_rate, numerator, denominator = self._pick_metric(data, spec, message)
        if not group_col or not metric:
            return SkillOutput(
                "descriptive_comparison",
                "descriptive_result",
                {},
                valid=False,
                warnings=["缺少分组字段或可计算指标"],
            )
        data, scope = self._filter_context(data, group_col, message)
        data = self._filter_requested_groups(data, group_col, message)
        strategy_group = group_col in {"title_style", "topic", "publish_time", "hour", "feature_tags"}

        if numerator and denominator:
            grouped, usable = self._aggregate_derived_rate(data, group_col, numerator, denominator)
        else:
            data[metric] = pd.to_numeric(data[metric], errors="coerce")
            usable = data.dropna(subset=[group_col, metric]).copy()
            aggregation = "mean" if is_rate or strategy_group or any(word in message for word in ("平均", "均值", "每条")) else "sum"
            grouped = usable.groupby(group_col, dropna=False)[metric].agg([aggregation, "count"]).rename(columns={aggregation: "mean"}).sort_values("mean", ascending=False)

        ranking = [
            {
                "rank": index + 1,
                "group": self._display_group(group),
                "raw_group": str(group),
                "value": float(row["mean"]),
                "sample_size": int(row["count"]),
            }
            for index, (group, row) in enumerate(grouped.iterrows())
        ]
        total_groups = int(data[group_col].nunique(dropna=True))
        unavailable_groups = max(total_groups - len(ranking), 0)
        scale = self._rate_scale([row["value"] for row in ranking]) if is_rate else 1.0
        common = {
            "question_type": "descriptive_comparison",
            "evidence_label": "直接观察",
            "group_by": group_col,
            "group_label": DISPLAY_NAMES.get(group_col, group_col),
            "metric": metric,
            "metric_label": DISPLAY_NAMES.get(metric, metric),
            "is_rate": is_rate,
            "display_scale": scale,
            "ranking": ranking,
            "unavailable_groups": unavailable_groups,
            "denominator": denominator,
            "sample_size": int(len(usable)),
            "aggregation": "比率" if numerator and denominator else ("平均值" if is_rate or strategy_group or any(word in message for word in ("平均", "均值", "每条")) else "合计"),
            "requested_limit": self._requested_limit(message),
            "scope": scope,
        }

        if len(ranking) < 2:
            return SkillOutput(
                "descriptive_comparison",
                "descriptive_result",
                {**common, "status": "insufficient_comparison"},
                warnings=["只有一个或没有分组具备有效分母，暂时不能跨平台排名"],
            )

        best, runner_up, worst = ranking[0], ranking[1], ranking[-1]
        ratio = best["value"] / worst["value"] if worst["value"] != 0 else None
        tied = all(abs(row["value"] - best["value"]) < 1e-12 for row in ranking)
        content = {
            **common,
            "status": "tie" if tied else "comparable",
            "best": best,
            "runner_up": runner_up,
            "worst": worst,
            "absolute_gap": float(best["value"] - runner_up["value"]),
            "best_to_worst_ratio": float(ratio) if ratio is not None else None,
            "interpretation": "这是对已上传数据的直接比较，可以回答当前谁更高；它不用于证明平台本身造成了差异。",
        }
        return SkillOutput("descriptive_comparison", "descriptive_result", content)

    @staticmethod
    def _aggregate_derived_rate(
        data: pd.DataFrame,
        group_col: str,
        numerator: str,
        denominator: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        data[numerator] = pd.to_numeric(data[numerator], errors="coerce")
        data[denominator] = pd.to_numeric(data[denominator], errors="coerce")
        usable = data.dropna(subset=[group_col, numerator, denominator]).copy()
        totals = usable.groupby(group_col, dropna=False)[[numerator, denominator]].sum()
        totals = totals[totals[denominator] > 0]
        counts = usable.groupby(group_col, dropna=False).size().reindex(totals.index)
        grouped = pd.DataFrame({"mean": totals[numerator] / totals[denominator], "count": counts})
        return grouped.sort_values("mean", ascending=False), usable

    @staticmethod
    def _pick_group(df: pd.DataFrame, spec: dict[str, Any], message: str = "") -> str | None:
        if any(word in message for word in ("内容", "作品", "帖子", "视频")):
            for column in ("title", "content_id"):
                if column in df.columns and df[column].nunique(dropna=True) >= 2:
                    return column
        if any(word in message for word in ("产品", "商品", "款式")):
            for column in ("product_name", "product_id", "feature_tags"):
                if column in df.columns and df[column].nunique(dropna=True) >= 2:
                    return column
        candidates = list(spec.get("candidate_treatments") or []) + ["platform", "topic", "title_style"]
        for column in candidates:
            if column in df.columns and df[column].nunique(dropna=True) >= 2:
                return column
        return None

    @staticmethod
    def _pick_metric(df: pd.DataFrame, spec: dict[str, Any], message: str = "") -> tuple[str | None, bool, str | None, str | None]:
        requested = list(spec.get("candidate_outcomes") or [])
        explicit_rates = []
        for metric, markers in {
            "conversion_rate": ("转化率", "成交率", "购买率", "转化更好"),
            "consultation_rate": ("咨询率", "线索率"),
            "favorite_rate": ("收藏率", "保存率"),
            "follow_rate": ("转粉率", "涨粉率"),
        }.items():
            if any(marker in message.lower() for marker in markers):
                explicit_rates.append(metric)
        preferred = ["conversion_rate", "consultation_rate", "favorite_rate", "follow_rate"]
        candidates = list(dict.fromkeys(explicit_rates + requested + preferred + ["revenue", "conversions", "consultations", "views"]))
        for metric in candidates:
            if metric in df.columns and pd.to_numeric(df[metric], errors="coerce").notna().any():
                return metric, metric.endswith("_rate"), None, None
            numerator = RATE_NUMERATORS.get(metric)
            if numerator and numerator in df.columns:
                denominator = next(
                    (
                        name
                        for name in RATE_DENOMINATORS[metric]
                        if name in df.columns and pd.to_numeric(df[name], errors="coerce").fillna(0).gt(0).any()
                    ),
                    None,
                )
                if denominator:
                    return metric, True, numerator, denominator
        return None, False, None, None

    @staticmethod
    def _rate_scale(values: list[float]) -> float:
        return 1.0 if max((abs(v) for v in values), default=0.0) > 1 else 100.0

    @staticmethod
    def _display_group(value: Any) -> str:
        raw = str(value)
        return {
            **PLATFORM_NAMES,
            "pain_point": "痛点型",
            "tutorial": "教程型",
            "numbered": "数字型",
            "question": "提问型",
        }.get(raw.lower(), raw)

    @staticmethod
    def _requested_limit(message: str) -> int:
        import re

        match = re.search(r"(?:前|top\s*)(\d{1,2})|([1-9]\d?)\s*条", message.lower())
        if not match:
            return 6
        return max(1, min(int(match.group(1) or match.group(2)), 20))

    @staticmethod
    def _filter_requested_groups(df: pd.DataFrame, group_col: str, message: str) -> pd.DataFrame:
        if group_col != "title_style":
            return df
        requested: list[set[str]] = []
        aliases = {
            "痛点": {"pain_point", "pain-point", "痛点", "痛点型"},
            "教程": {"tutorial", "教程", "教程型"},
            "数字": {"number", "numbered", "数字", "数字型", "listicle"},
            "提问": {"question", "提问", "疑问型"},
        }
        for mention, values in aliases.items():
            if mention in message:
                requested.append(values)
        if len(requested) < 2:
            return df
        allowed = set().union(*requested)
        normalized = df[group_col].astype(str).str.lower()
        filtered = df[normalized.isin({value.lower() for value in allowed})]
        return filtered if filtered[group_col].nunique(dropna=True) >= 2 else df

    @staticmethod
    def _filter_context(df: pd.DataFrame, group_col: str, message: str) -> tuple[pd.DataFrame, dict[str, str]]:
        """Apply an explicitly named platform as scope when platform is not the comparison axis."""
        if group_col == "platform" or "platform" not in df.columns:
            return df, {}
        aliases = {
            "小红书": {"小红书", "xiaohongshu", "rednote"},
            "B站": {"b站", "bilibili"},
            "抖音": {"抖音", "douyin"},
            "公众号/视频号": {"公众号", "视频号", "wechat", "weixin"},
            "快手": {"快手", "kuaishou"},
            "淘宝": {"淘宝", "taobao"},
            "美团": {"美团", "meituan"},
        }
        lowered_message = message.lower()
        normalized = df["platform"].astype(str).str.strip().str.lower()
        for label, values in aliases.items():
            if any(mention.lower() in lowered_message for mention in values):
                filtered = df[normalized.isin({value.lower() for value in values})]
                if not filtered.empty:
                    return filtered, {"platform": label}
        return df, {}
