from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any


TASK_TYPES = {
    "ideation", "planning", "experiment_design", "data_analysis",
    "descriptive_analysis", "causal_hypothesis_generation",
    "causal_effect_estimation", "counterfactual_analysis",
    "data_quality_repair", "report_generation", "writing",
    "method_comparison", "workflow_debugging",
}

ROUTE_EXAMPLES: dict[str, tuple[str, ...]] = {
    "descriptive_analysis": (
        "哪个平台转化更好", "把各渠道收入排个名", "谁的咨询率最高",
        "比较不同标题的平均收藏数", "痛点标题比教程标题更能带来咨询吗", "看看当前数据发生了什么",
    ),
    "causal_effect_estimation": (
        "我想分个组看看效果", "控制混杂后这个策略的净增量是多少", "这个标题是否直接导致更多咨询",
        "控制账号差异后功能升级有多少增量", "估计策略对收入的影响",
        "用处理组和对照组计算提升效果",
    ),
    "experiment_design": (
        "帮我设计一个分组实验", "下周怎么做对照测试", "设计AB实验和停止规则",
        "需要多少样本才能验证这个方案",
    ),
    "counterfactual_analysis": (
        "如果把内容换到另一个平台会怎样", "模拟增加预算后的收入",
        "做一个反事实策略模拟", "如果没有使用这个功能结果会怎样",
    ),
    "causal_hypothesis_generation": (
        "生成变量关系图", "构建候选因果图", "哪些变量可能是混杂因素",
        "用知识图谱约束DAG",
    ),
    "data_quality_repair": (
        "检查缺失值和异常字段", "这份数据为什么无法分析", "修复表格质量问题",
    ),
    "report_generation": (
        "生成经营周报", "导出策略复盘", "总结本周分析结果",
    ),
    "planning": (
        "下一步应该做什么", "安排下周行动", "根据结果制定执行计划",
    ),
    "writing": (
        "帮我改写标题", "生成内容文案", "写一份品牌合作介绍",
    ),
    "workflow_debugging": (
        "为什么这次分析失败", "检查工具调用流程", "调试Agent工作流",
    ),
}

L1_MARKERS: dict[str, tuple[str, ...]] = {
    "counterfactual_analysis": ("反事实", "what-if", "模拟干预"),
    "experiment_design": ("实验设计", "设计实验", "停止规则", "样本量建议"),
    "causal_hypothesis_generation": ("知识图谱", "候选dag", "因果图", "混杂变量"),
    "causal_effect_estimation": ("因果", "归因", "ate", "cate", "置信区间", "增量效果"),
    "data_quality_repair": ("缺失值", "数据质量", "异常字段", "修复数据"),
    "report_generation": ("周报", "复盘报告", "导出报告", "总结这份数据", "三个发现", "数据洞察"),
    "workflow_debugging": ("调试", "工具报错", "工作流失败"),
    "writing": ("改写文案", "生成文案", "写标题"),
}


@dataclass
class HybridRouteDecision:
    task_type: str
    layer: str
    confidence: float
    rationale: str
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    task_spec_patch: dict[str, Any] = field(default_factory=dict)
    backend: str = "rules"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def route_task_intent(
    message: str,
    columns: list[str],
    *,
    baseline_task_type: str = "descriptive_analysis",
    allow_llm: bool | None = None,
) -> HybridRouteDecision:
    """Three-level router: exact rules -> vector retrieval -> guarded LLM JSON."""
    l1 = _route_l1(message)
    if l1 and l1.confidence >= 0.84:
        return l1

    l2 = _route_l2(message)
    if l2.confidence >= 0.48:
        if l1 and l1.task_type != l2.task_type:
            l2.warnings.append(f"L1 候选为 {l1.task_type}，已由更高覆盖的语义路由复核")
        return l2

    enabled = allow_llm if allow_llm is not None else os.getenv("SOLODECK_ENABLE_LLM_ROUTER", "true").lower() == "true"
    if enabled:
        l3 = _route_l3(message, columns, baseline_task_type, l1, l2)
        if l3 is not None:
            return l3

    candidates = [candidate for candidate in (l1, l2) if candidate is not None]
    best = max(candidates, key=lambda item: item.confidence, default=None)
    if best and best.confidence >= 0.25:
        best.warnings.append("路由置信度偏低，保留编译器基线并要求后续 Critic 复核")
        if best.task_type != baseline_task_type:
            best.task_spec_patch = {}
            best.task_type = baseline_task_type
        return best
    return HybridRouteDecision(
        task_type=baseline_task_type,
        layer="fallback",
        confidence=0.2,
        rationale="三级路由均未获得可靠匹配，保留确定性编译器结果。",
        warnings=["低置信路由"],
    )


def apply_route_to_spec(spec: Any, decision: HybridRouteDecision, columns: list[str]) -> Any:
    """Apply only schema-valid L2/L3 patches; never trust free-form model fields."""
    if decision.task_type in TASK_TYPES and decision.confidence >= 0.48:
        spec.task_type = decision.task_type
        if decision.task_type in {
            "causal_effect_estimation", "counterfactual_analysis",
            "causal_hypothesis_generation", "experiment_design",
        }:
            spec.budget_level = "deep_path"
    patch = decision.task_spec_patch or {}
    treatments = _valid_columns(patch.get("candidate_treatments"), columns)
    outcomes = _valid_columns(patch.get("candidate_outcomes"), columns)
    if treatments:
        spec.candidate_treatments = list(dict.fromkeys(treatments + spec.candidate_treatments))
    if outcomes:
        spec.candidate_outcomes = list(dict.fromkeys(outcomes + spec.candidate_outcomes))
    unit = patch.get("unit")
    time = patch.get("time")
    if unit in columns:
        spec.unit = unit
    if time in columns:
        spec.time = time
    spec.constraints.append(f"hybrid_route:{decision.layer}:{decision.confidence:.2f}")
    return spec


def _route_l1(message: str) -> HybridRouteDecision | None:
    text = (message or "").lower()
    scored: list[tuple[int, str, list[str]]] = []
    for task_type, markers in L1_MARKERS.items():
        hits = [marker for marker in markers if marker in text]
        if hits:
            scored.append((len(hits), task_type, hits))
    if not scored:
        return None
    scored.sort(reverse=True)
    count, task_type, hits = scored[0]
    confidence = min(0.97, 0.82 + 0.05 * (count - 1))
    return HybridRouteDecision(
        task_type=task_type,
        layer="L1",
        confidence=confidence,
        rationale=f"命中高精度业务标记：{', '.join(hits)}。",
        backend="keyword_rules",
    )


def _route_l2(message: str) -> HybridRouteDecision:
    labels: list[str] = []
    examples: list[str] = []
    for task_type, rows in ROUTE_EXAMPLES.items():
        for row in rows:
            labels.append(task_type)
            examples.append(row)
    similarities, backend = _semantic_similarities(message, examples)
    by_label: dict[str, float] = {}
    for label, score in zip(labels, similarities):
        by_label[label] = max(by_label.get(label, 0.0), float(score))
    ranked = sorted(by_label.items(), key=lambda item: item[1], reverse=True)
    task_type, top = ranked[0] if ranked else ("descriptive_analysis", 0.0)
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = max(0.0, top - second)
    confidence = max(0.0, min(0.92, 0.65 * top + 0.35 * min(1.0, margin * 3)))
    return HybridRouteDecision(
        task_type=task_type,
        layer="L2",
        confidence=confidence,
        rationale=f"与任务样例的向量相似度为 {top:.3f}，领先次选 {margin:.3f}。",
        alternatives=[{"task_type": label, "score": round(score, 4)} for label, score in ranked[:3]],
        backend=backend,
    )


def _semantic_similarities(message: str, examples: list[str]) -> tuple[list[float], str]:
    if os.getenv("SOLODECK_USE_SENTENCE_TRANSFORMERS", "false").lower() == "true":
        try:
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity

            model_name = os.getenv("SOLODECK_ROUTER_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
            vectors = SentenceTransformer(model_name).encode([message, *examples], normalize_embeddings=True)
            return cosine_similarity(vectors[:1], vectors[1:])[0].tolist(), f"sentence_transformers:{model_name}"
        except Exception:
            pass
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    matrix = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1).fit_transform([message, *examples])
    return cosine_similarity(matrix[:1], matrix[1:])[0].tolist(), "char_tfidf_vector_fallback"


def _route_l3(
    message: str,
    columns: list[str],
    baseline: str,
    l1: HybridRouteDecision | None,
    l2: HybridRouteDecision,
) -> HybridRouteDecision | None:
    try:
        from solo_creator_agent.src.llm_agent import call_llm, llm_configured

        if not llm_configured():
            return None
        prompt = """
你是 SoloDeck 的任务编译路由器。根据用户目标和可用列名，只输出一个 JSON 对象。
字段：task_type、confidence、candidate_treatments、candidate_outcomes、unit、time、rationale。
task_type 必须从给定列表中选择。字段名必须来自 columns，不得虚构。不要计算数据，不要输出 Markdown。
描述性排序使用 descriptive_analysis；只有明确询问导致、影响、增量或反事实时才使用因果任务。
"""
        payload = {
            "user_goal": message[:1200],
            "columns": columns[:120],
            "allowed_task_types": sorted(TASK_TYPES),
            "baseline": baseline,
            "L1": l1.to_dict() if l1 else None,
            "L2": l2.to_dict(),
        }
        raw = call_llm(prompt, payload, language="中文", temperature=0.0, profile="advanced")
        value = _extract_json(raw)
        task_type = value.get("task_type")
        if task_type not in TASK_TYPES:
            return None
        confidence = float(value.get("confidence", 0.0))
        if not math.isfinite(confidence):
            return None
        patch = {
            "candidate_treatments": _valid_columns(value.get("candidate_treatments"), columns),
            "candidate_outcomes": _valid_columns(value.get("candidate_outcomes"), columns),
            "unit": value.get("unit") if value.get("unit") in columns else None,
            "time": value.get("time") if value.get("time") in columns else None,
        }
        return HybridRouteDecision(
            task_type=task_type,
            layer="L3",
            confidence=max(0.0, min(0.95, confidence)),
            rationale=str(value.get("rationale") or "高级语义路由完成受约束 TaskSpec 补全。")[:300],
            task_spec_patch=patch,
            backend="llm_guarded_json",
        )
    except Exception as exc:
        l2.warnings.append(f"L3 路由不可用，已安全回退：{type(exc).__name__}")
        return None


def _valid_columns(values: Any, columns: list[str]) -> list[str]:
    if not isinstance(values, list):
        return []
    allowed = set(columns)
    return [str(value) for value in values if str(value) in allowed]


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("router output must be an object")
    return value
