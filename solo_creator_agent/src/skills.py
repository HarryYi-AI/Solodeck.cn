from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LinearRegression, LogisticRegression


COLUMN_ALIASES = {
    "content_id": ["content_id", "内容id", "内容ID", "作品id", "id"],
    "platform": ["platform", "平台", "渠道"],
    "title": ["title", "标题", "内容标题"],
    "topic": ["topic", "主题", "选题"],
    "title_style": ["title_style", "标题风格"],
    "publish_time": ["publish_time", "发布时间", "date", "日期"],
    "views": ["views", "播放量", "阅读量", "浏览量"],
    "likes": ["likes", "点赞", "点赞数"],
    "favorites": ["favorites", "收藏", "收藏数"],
    "comments": ["comments", "评论", "评论数"],
    "new_followers": ["new_followers", "新增粉丝", "涨粉"],
    "consultations": ["consultations", "咨询", "咨询数"],
    "conversions": ["conversions", "成交", "成交数", "转化"],
    "conversion_rate": ["conversion_rate", "转化率", "成交率", "购买率"],
    "consultation_rate": ["consultation_rate", "咨询率", "线索率"],
    "favorite_rate": ["favorite_rate", "收藏率", "保存率"],
    "follow_rate": ["follow_rate", "转粉率", "涨粉率"],
    "visitors": ["visitors", "访客数", "访客", "访问人数"],
    "revenue": ["revenue", "收入", "收益", "amount", "金额"],
    "production_hours": ["production_hours", "制作时长", "制作小时"],
    "account_id": ["account_id", "账号", "账号id"],
    "series_id": ["series_id", "系列", "内容系列"],
}

NUMERIC_COLUMNS = [
    "views", "likes", "favorites", "comments", "new_followers", "consultations",
    "conversions", "conversion_rate", "consultation_rate", "favorite_rate",
    "follow_rate", "visitors", "revenue", "production_hours",
]

DISPLAY_NAMES = {
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "douyin": "抖音",
    "wechat": "公众号/视频号",
    "zhihu": "知乎",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "substack": "Substack",
    "x": "X/Twitter",
    "pain_point": "痛点型",
    "tutorial": "教程型",
    "number": "数字清单型",
    "story": "故事型",
    "contrast": "对比型",
    "result_oriented": "结果导向型",
    "question": "提问型",
    "consultations": "咨询数",
    "favorite_rate": "收藏率",
    "conversions": "成交数",
    "revenue": "收入",
    "views": "播放量",
}


def _display(value: Any) -> str:
    text = str(value)
    return DISPLAY_NAMES.get(text, text)


def _safe_div(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def _clean_number(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        if pd.isna(value):
            return float("nan")
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        value = value.replace(",", "").replace("¥", "").replace("%", "").strip()
        if not value:
            return float("nan")
    try:
        return float(value)
    except Exception:
        return float("nan")


def dataset_fingerprint(df: pd.DataFrame) -> str:
    payload = pd.util.hash_pandas_object(df.fillna(""), index=True).values.tobytes()
    return hashlib.sha256(payload).hexdigest()[:16]


class DataMappingSkill:
    """Map uploaded tables to SoloDeck canonical creator schema."""

    def run(self, df: pd.DataFrame) -> dict[str, Any]:
        normalized = df.copy()
        original_cols = list(normalized.columns)
        rename: dict[str, str] = {}
        lower_map = {str(c).strip().lower(): c for c in original_cols}
        for canonical, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                key = alias.strip().lower()
                if key in lower_map:
                    rename[lower_map[key]] = canonical
                    break
        normalized = normalized.rename(columns=rename)
        for col in COLUMN_ALIASES:
            if col not in normalized.columns:
                normalized[col] = ""
        for col in NUMERIC_COLUMNS:
            normalized[col] = normalized[col].map(_clean_number)
        if "publish_time" in normalized.columns:
            normalized["publish_time"] = pd.to_datetime(normalized["publish_time"], errors="coerce")
        if normalized["content_id"].astype(str).str.len().eq(0).all():
            normalized["content_id"] = [f"U{idx + 1:04d}" for idx in range(len(normalized))]
        mapped = sorted(set(rename.values()))
        confidence = round(len(mapped) / max(1, len(COLUMN_ALIASES)), 2)
        missing = [c for c in COLUMN_ALIASES if c not in mapped and c not in {"content_id"}]
        return {
            "data": normalized,
            "summary": {
                "rows": int(len(normalized)),
                "mapped_fields": mapped,
                "missing_fields": missing[:8],
                "mapping_confidence": confidence,
                "dataset_id": dataset_fingerprint(normalized),
            },
        }


class MetricSkill:
    """Compute creator metrics deterministically."""

    def run(self, df: pd.DataFrame) -> dict[str, Any]:
        views = float(df["views"].sum()) if "views" in df else 0.0
        favorites = float(df["favorites"].sum()) if "favorites" in df else 0.0
        consultations = float(df["consultations"].sum()) if "consultations" in df else 0.0
        conversions = float(df["conversions"].sum()) if "conversions" in df else 0.0
        revenue = float(df["revenue"].sum()) if "revenue" in df else 0.0
        kpis = {
            "total_views": views,
            "favorite_rate": _safe_div(favorites, views),
            "consultation_rate": _safe_div(consultations, views),
            "conversion_rate": _safe_div(conversions, max(consultations, 1)),
            "revenue": revenue,
            "rpm": _safe_div(revenue, views) * 1000,
        }
        scored = df.copy()
        scored["favorite_rate"] = np.where(scored["views"] > 0, scored["favorites"] / scored["views"], 0)
        scored["consultation_rate"] = np.where(scored["views"] > 0, scored["consultations"] / scored["views"], 0)
        scored["content_value_score"] = (
            scored["favorite_rate"].rank(pct=True).fillna(0) * 25
            + scored["consultation_rate"].rank(pct=True).fillna(0) * 25
            + scored["conversions"].rank(pct=True).fillna(0) * 20
            + scored["revenue"].rank(pct=True).fillna(0) * 30
        ).round(1)
        return {"kpis": kpis, "scored": scored}


class SimilaritySkill:
    """Detect duplicated content and possible series fatigue."""

    def run(self, df: pd.DataFrame) -> dict[str, Any]:
        if df.empty:
            return {"series": [], "duplication_risk": 0.0, "warning": ""}
        text = (df["title"].fillna("").astype(str) + " " + df["topic"].fillna("").astype(str)).tolist()
        duplication_risk = 0.0
        if len(text) > 1:
            try:
                matrix = TfidfVectorizer(max_features=600, token_pattern=r"(?u)\b\w+\b").fit_transform(text)
                sim = (matrix @ matrix.T).toarray()
                np.fill_diagonal(sim, 0)
                duplication_risk = float(np.max(sim))
            except Exception:
                duplication_risk = 0.0
        series_rows = []
        if "series_id" in df.columns:
            for sid, group in df[df["series_id"].astype(str).str.len().gt(0)].groupby("series_id"):
                if len(group) < 3:
                    continue
                ordered = group.sort_values("publish_time")
                first = float(ordered["views"].head(2).mean())
                last = float(ordered["views"].tail(2).mean())
                fatigue = last < first * 0.78 if first else False
                series_rows.append({"series_id": str(sid), "content_count": int(len(group)), "fatigue_warning": fatigue, "view_change": last - first})
        return {
            "series": series_rows[:5],
            "duplication_risk": round(duplication_risk, 3),
            "warning": "存在重复或疲劳风险，建议换角度验证。" if duplication_risk >= 0.72 else "",
        }


class CausalHypothesisGraphSkill:
    """Generate candidate causal priors; never treated as ground truth."""

    def run(self, question: str, columns: list[str]) -> dict[str, Any]:
        confounders = [c for c in ["platform", "topic", "account_id", "production_hours", "publish_time"] if c in columns]
        return {
            "hypothesis_only": True,
            "nodes": ["strategy", "outcome", *confounders],
            "candidate_confounders": confounders,
            "warning": "这是候选因果先验，不是自动发现的因果真相。",
        }


class DecisionQuestionSkill:
    """Convert a user-friendly question into treatment/control/outcome."""

    QUESTIONS = {
        "pain_point_title": ("title_style", "pain_point", "consultations", "痛点标题是否提升咨询"),
        "platform_conversion": ("platform", None, "conversions", "哪个平台更适合转化"),
        "series_continue": ("series_id", None, "revenue", "这个系列是否继续"),
        "favorite_to_product": ("title_style", "tutorial", "revenue", "高收藏内容是否值得产品化"),
    }

    def run(self, question_id: str, df: pd.DataFrame) -> dict[str, Any]:
        treatment, treatment_value, outcome, label = self.QUESTIONS.get(question_id, self.QUESTIONS["pain_point_title"])
        if treatment_value is None and treatment in df.columns and not df.empty:
            treatment_value = str(df.groupby(treatment)[outcome].mean().sort_values(ascending=False).index[0]) if outcome in df.columns else str(df[treatment].dropna().iloc[0])
        return {
            "question_id": question_id,
            "label": label,
            "treatment": treatment,
            "treatment_value": treatment_value,
            "control": f"not {treatment_value}",
            "outcome": outcome,
            "covariates": [c for c in ["platform", "topic", "account_id", "production_hours"] if c in df.columns and c != treatment],
        }


class CausalReadinessSkill:
    """Check whether the dataset can support a causal-style claim."""

    def run(self, df: pd.DataFrame, query: dict[str, Any]) -> dict[str, Any]:
        warnings = []
        score = 0
        treatment = query["treatment"]
        outcome = query["outcome"]
        if treatment in df.columns and df[treatment].nunique(dropna=True) >= 2:
            score += 25
        else:
            warnings.append("缺少清晰的实验组/对照组。")
        if outcome in df.columns and pd.api.types.is_numeric_dtype(df[outcome]):
            score += 25
        else:
            warnings.append("结果指标不是可计算数值。")
        if len(df) >= 30:
            score += 20
        else:
            warnings.append("样本偏少，优先看 bootstrap 区间，不要直接放大。")
        if query.get("covariates"):
            score += 20
        else:
            warnings.append("缺少可控制的混杂变量。")
        if "publish_time" in df.columns:
            score += 10
        risk = "低" if score >= 75 else "中" if score >= 50 else "高"
        return {"readiness_score": score, "risk_level": risk, "can_make_causal_claim": score >= 75, "warnings": warnings}


@dataclass
class EffectResult:
    naive_effect: float
    relative_lift: float
    ci_low: float
    ci_high: float
    adjusted_effect: float
    treated_n: int
    control_n: int
    sample_size: int
    cate: list[dict[str, Any]]
    warnings: list[str]


class EffectEstimationSkill:
    """ATE/CATE, bootstrap CI, fixed effects and optional IPTW."""

    def bootstrap_ci(self, treated: np.ndarray, control: np.ndarray, n_boot: int = 1200) -> tuple[float, float]:
        if len(treated) == 0 or len(control) == 0:
            return 0.0, 0.0
        rng = np.random.default_rng(42)
        diffs = []
        for _ in range(n_boot):
            t = rng.choice(treated, size=len(treated), replace=True)
            c = rng.choice(control, size=len(control), replace=True)
            diffs.append(float(np.mean(t) - np.mean(c)))
        return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))

    def fixed_effect(self, df: pd.DataFrame, treatment_flag: str, outcome: str, covariates: list[str]) -> float:
        if df[treatment_flag].nunique() < 2:
            return 0.0
        x = pd.concat([df[[treatment_flag]].astype(float), pd.get_dummies(df[covariates], drop_first=True).fillna(0)], axis=1)
        y = df[outcome].astype(float)
        return float(LinearRegression().fit(x, y).coef_[0])

    def iptw(self, df: pd.DataFrame, treatment_flag: str, outcome: str, covariates: list[str]) -> float | None:
        if not covariates or df[treatment_flag].nunique() < 2:
            return None
        x = pd.get_dummies(df[covariates], drop_first=True).fillna(0)
        if x.empty:
            return None
        t = df[treatment_flag].astype(int)
        try:
            ps = np.clip(LogisticRegression(max_iter=1000).fit(x, t).predict_proba(x)[:, 1], 0.03, 0.97)
        except Exception:
            return None
        y = df[outcome].astype(float).to_numpy()
        t_arr = t.to_numpy()
        return float(np.sum(t_arr * y / ps) / np.sum(t_arr / ps) - np.sum((1 - t_arr) * y / (1 - ps)) / np.sum((1 - t_arr) / (1 - ps)))

    def run(self, df: pd.DataFrame, query: dict[str, Any]) -> dict[str, Any]:
        treatment = query["treatment"]
        outcome = query["outcome"]
        value = query.get("treatment_value")
        data = df.dropna(subset=[treatment, outcome]).copy()
        data["_treated"] = data[treatment].eq(value).astype(int)
        treated = data[data["_treated"].eq(1)][outcome].astype(float).to_numpy()
        control = data[data["_treated"].eq(0)][outcome].astype(float).to_numpy()
        naive = float(np.mean(treated) - np.mean(control)) if len(treated) and len(control) else 0.0
        baseline = float(np.mean(control)) if len(control) else 0.0
        ci_low, ci_high = self.bootstrap_ci(treated, control)
        covariates = [c for c in query.get("covariates", []) if c in data.columns]
        adjusted = self.fixed_effect(data, "_treated", outcome, covariates) if len(data) else 0.0
        iptw_effect = self.iptw(data, "_treated", outcome, covariates)
        warnings = []
        if ci_low <= 0 <= ci_high:
            warnings.append("置信区间穿过 0，结果还不稳，建议先小范围验证。")
        if len(treated) < 10 or len(control) < 10:
            warnings.append("实验组或对照组样本少于 10，区间会更不稳定。")
        cate = []
        for segment in ["platform", "topic"]:
            if segment in data.columns:
                for name, group in data.groupby(segment):
                    if len(group) >= 6 and group["_treated"].nunique() == 2:
                        t = group[group["_treated"].eq(1)][outcome].astype(float).mean()
                        c = group[group["_treated"].eq(0)][outcome].astype(float).mean()
                        cate.append({"segment": segment, "value": str(name), "effect": float(t - c), "sample_size": int(len(group))})
        explanation = "这个区间表示效果是否稳定。如果区间穿过 0，说明当前结果还不够稳；大多数数值高于 0，才更像正向效果。"
        return {
            "ate": naive,
            "adjusted_effect": adjusted,
            "relative_lift": _safe_div(naive, abs(baseline)),
            "ci_95": [ci_low, ci_high],
            "treated_n": int(len(treated)),
            "control_n": int(len(control)),
            "sample_size": int(len(data)),
            "iptw_effect": iptw_effect,
            "cate": cate[:8],
            "warnings": warnings,
            "explanation": explanation,
        }


class ActionTestSkill:
    def run(self, query: dict[str, Any], effect: dict[str, Any]) -> dict[str, Any]:
        stable_positive = effect["ci_95"][0] > 0
        decision = "小幅放大" if stable_positive else "下周验证"
        return {
            "decision": decision,
            "duration": "10-14 天",
            "sample_size": "每组至少 6 条内容；数据少时延长周期。",
            "primary_metric": query["outcome"],
            "steps": [
                "固定同一平台和同一主题，避免平台差异干扰。",
                "每条内容只改变一个策略变量。",
                "发布后 24h、72h、7d 固定记录结果。",
                "若 95% 区间仍高于 0，再进入下一批放大。",
            ],
        }


class ReportSkill:
    def run(self, observations: list[dict[str, str]], effect: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, str]]:
        first = observations[0] if observations else {"title": "保留当前有效方向", "detail": "当前数据显示存在可继续观察的方向。"}
        return [
            {
                "type": "继续放大",
                "recommendation": first["title"],
                "evidence": first["detail"],
                "risk": "这是经营模式观察，不直接等同因果。",
                "next_step": "保留 1-2 条同方向内容，并继续记录 72 小时结果。",
                "metric_to_watch": "咨询数",
            },
            {
                "type": "减少投入",
                "recommendation": "减少重复题材和低收益制作",
                "evidence": "相似内容或高制作时长内容容易占用精力。",
                "risk": "如果不减少，可能造成系列疲劳和机会成本。",
                "next_step": "把重复主题改成案例、清单或问答，不再原样复刻。",
                "metric_to_watch": "收藏率",
            },
            {
                "type": "下周验证",
                "recommendation": plan["decision"],
                "evidence": f"调整后增量 {effect['adjusted_effect']:.2f}，95% 区间 [{effect['ci_95'][0]:.2f}, {effect['ci_95'][1]:.2f}]。",
                "risk": "区间穿过 0 时不要直接放大。",
                "next_step": "；".join(plan["steps"][:2]),
                "metric_to_watch": _display(plan["primary_metric"]),
            },
        ]


def run_skill_pipeline(df: pd.DataFrame, question_id: str = "pain_point_title") -> dict[str, Any]:
    mapping = DataMappingSkill().run(df)
    data = mapping["data"]
    metric = MetricSkill().run(data)
    data = metric["scored"]
    similarity = SimilaritySkill().run(data)
    query = DecisionQuestionSkill().run(question_id, data)
    graph = CausalHypothesisGraphSkill().run(query["label"], list(data.columns))
    readiness = CausalReadinessSkill().run(data, query)
    effect = EffectEstimationSkill().run(data, query)
    plan = ActionTestSkill().run(query, effect)
    observations = _observations(data, metric["kpis"], similarity)
    cards = ReportSkill().run(observations, effect, plan)
    return {
        "dataset_id": mapping["summary"]["dataset_id"],
        "mapping": mapping["summary"],
        "kpis": metric["kpis"],
        "observations": observations[:3],
        "decision": {"query": query, "readiness": readiness, "effect": effect, "hypothesis_graph": graph},
        "action_cards": cards,
        "trace": ["DataMappingSkill", "MetricSkill", "SimilaritySkill", "CausalHypothesisGraphSkill", "DecisionQuestionSkill", "CausalReadinessSkill", "EffectEstimationSkill", "ActionTestSkill", "ReportSkill"],
    }


def _observations(data: pd.DataFrame, kpis: dict[str, float], similarity: dict[str, Any]) -> list[dict[str, str]]:
    obs = []
    if "platform" in data.columns and not data.empty:
        table = data.groupby("platform").agg(revenue=("revenue", "sum"), conversions=("conversions", "sum"), views=("views", "sum")).reset_index()
        top = table.sort_values(["revenue", "conversions"], ascending=False).iloc[0]
        obs.append({"title": f"{_display(top['platform'])} 是当前更强的商业渠道", "detail": f"收入 {top['revenue']:.0f}，成交 {top['conversions']:.0f}。"})
    if "title_style" in data.columns and not data.empty:
        style = data.groupby("title_style").agg(consultations=("consultations", "mean"), views=("views", "count")).reset_index()
        top = style.sort_values("consultations", ascending=False).iloc[0]
        obs.append({"title": f"{_display(top['title_style'])}标题带来更多咨询", "detail": f"平均咨询 {top['consultations']:.2f}，样本 {int(top['views'])} 条。"})
    if similarity.get("warning"):
        obs.append({"title": "存在内容重复或疲劳风险", "detail": similarity["warning"]})
    else:
        obs.append({"title": "当前内容重复风险可控", "detail": "可以继续围绕高价值主题做小规模验证。"})
    return obs[:3]
