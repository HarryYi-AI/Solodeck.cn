from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from statistics import pvariance
from typing import Any


WEIGHTS = {
    "task_grounding": 0.13,
    "route_confidence": 0.08,
    "artifact_integrity": 0.14,
    "statistical_validity": 0.14,
    "causal_validity": 0.13,
    "uncertainty_handling": 0.11,
    "actionability": 0.10,
    "privacy": 0.10,
    "traceability": 0.07,
}


@dataclass
class CriticDimension:
    name: str
    score: float
    weight: float
    evidence: str
    issues: list[str] = field(default_factory=list)


@dataclass
class CriticReport:
    overall_score: float
    decision: str
    dimensions: list[CriticDimension]
    failures: list[dict[str, Any]]
    repair_directives: list[dict[str, Any]]
    trajectory_informative: bool
    phase: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["dimensions"] = [asdict(item) for item in self.dimensions]
        return value


def evaluate_run(state: dict[str, Any], *, phase: str = "postwrite") -> CriticReport:
    """Deterministic multi-dimensional critic suitable for repair and offline policy learning."""
    dimensions = [
        _task_grounding(state),
        _route_confidence(state),
        _artifact_integrity(state),
        _statistical_validity(state),
        _causal_validity(state),
        _uncertainty_handling(state),
        _actionability(state, phase),
        _privacy(state),
        _traceability(state),
    ]
    active = [item for item in dimensions if not (phase == "prewrite" and item.name == "actionability")]
    total_weight = sum(item.weight for item in active) or 1.0
    overall = sum(item.score * item.weight for item in active) / total_weight
    failures = []
    directives = []
    for item in active:
        if item.score >= 0.7:
            continue
        failure_type = _failure_type(item.name)
        failures.append({"failure_type": failure_type, "dimension": item.name, "issues": item.issues})
        directives.append(_repair_directive(failure_type, item.issues))

    privacy_block = next(item for item in dimensions if item.name == "privacy").score == 0
    if privacy_block:
        decision = "block"
    elif overall < 0.72 or any(item.score < 0.35 for item in active):
        decision = "repair"
    else:
        decision = "pass"
    scores = [item.score for item in active]
    informative = 0.08 < overall < 0.96 and (pvariance(scores) if len(scores) > 1 else 0.0) > 0.015
    return CriticReport(
        overall_score=round(overall, 4),
        decision=decision,
        dimensions=dimensions,
        failures=failures,
        repair_directives=_dedupe_directives(directives),
        trajectory_informative=informative,
        phase=phase,
    )


def _task_grounding(state: dict[str, Any]) -> CriticDimension:
    spec = state.get("task_spec") or {}
    score = 0.0
    fields = [spec.get("task_type"), spec.get("objective"), spec.get("unit")]
    score += sum(bool(value) for value in fields) / len(fields) * 0.55
    if spec.get("candidate_outcomes"):
        score += 0.25
    if spec.get("candidate_treatments") or spec.get("task_type") in {"report_generation", "writing"}:
        score += 0.20
    issues = [] if score >= 0.7 else ["TaskSpec 未完整绑定任务、分析单位或目标指标"]
    return _dimension("task_grounding", score, "TaskSpec 字段完整度", issues)


def _route_confidence(state: dict[str, Any]) -> CriticDimension:
    route = state.get("semantic_route") or {}
    confidence = float(route.get("confidence", 0.55 if state.get("task_spec") else 0.0))
    confidence = max(0.0, min(1.0, confidence))
    issues = [] if confidence >= 0.48 else ["语义路由置信度偏低，应澄清或调用 L3 路由"]
    return _dimension("route_confidence", confidence, f"{route.get('layer', 'baseline')} 路由置信度 {confidence:.2f}", issues)


def _artifact_integrity(state: dict[str, Any]) -> CriticDimension:
    artifacts = state.get("artifacts") or []
    expected = set((state.get("task_spec") or {}).get("expected_artifacts") or [])
    produced = {item.get("id") for item in artifacts}
    valid_ratio = sum(item.get("valid", True) is not False for item in artifacts) / max(1, len(artifacts))
    required = {item for item in expected if item not in {"final_report", "kg_context"}}
    coverage = len(required & produced) / max(1, len(required)) if required else 1.0
    score = 0.55 * valid_ratio + 0.45 * coverage if artifacts else 0.0
    missing = sorted(required - produced)
    issues = ([f"缺少期望工件：{', '.join(missing)}"] if missing else []) + (["没有可验证的计算工件"] if not artifacts else [])
    return _dimension("artifact_integrity", score, f"工件 {len(artifacts)} 个，期望覆盖率 {coverage:.2f}", issues)


def _statistical_validity(state: dict[str, Any]) -> CriticDimension:
    causal = _is_causal(state)
    comparison = _artifact(state, "descriptive_comparison")
    estimate = _artifact(state, "bootstrap_ci") or _artifact(state, "regression_effect") or _artifact(state, "did_effect")
    if not causal:
        score = 1.0 if comparison or any(item.get("source_type") in {"python", "sql"} for item in state.get("artifacts", [])) else 0.35
        issues = [] if score >= 0.7 else ["描述性结论缺少 Python/SQL 计算工件"]
        return _dimension("statistical_validity", score, "描述性计算工件检查", issues)
    if not estimate:
        return _dimension("statistical_validity", 0.0, "未找到效果估计", ["因果任务缺少效果估计工件"])
    n = int(estimate.get("sample_size") or 0)
    score = 0.45 + min(0.35, n / 100) + (0.20 if estimate.get("ci_95") else 0.0)
    issues = [] if n >= 20 else ["效果估计样本量偏小"]
    return _dimension("statistical_validity", score, f"样本量 {n}，区间={'有' if estimate.get('ci_95') else '无'}", issues)


def _causal_validity(state: dict[str, Any]) -> CriticDimension:
    if not _is_causal(state):
        return _dimension("causal_validity", 1.0, "当前不是因果任务", [])
    readiness = _artifact(state, "causal_readiness")
    if not readiness:
        return _dimension("causal_validity", 0.0, "缺少因果就绪度工件", ["未检查处理组、结果变量、混杂和重叠性"])
    raw = float(readiness.get("score", readiness.get("readiness_score", 0.0)))
    score = raw / 100 if raw > 1 else raw
    score = max(0.0, min(1.0, score))
    issues = list(readiness.get("warnings") or []) if score < 0.8 else []
    return _dimension("causal_validity", score, f"因果就绪度 {score:.2f}", issues)


def _uncertainty_handling(state: dict[str, Any]) -> CriticDimension:
    if not _is_causal(state):
        return _dimension("uncertainty_handling", 1.0, "描述性任务不要求效果区间", [])
    estimate = _artifact(state, "bootstrap_ci") or _artifact(state, "did_effect") or _artifact(state, "regression_effect")
    ci = estimate.get("ci_95") if estimate else None
    if not ci or len(ci) != 2 or any(value is None for value in ci):
        return _dimension("uncertainty_handling", 0.0, "缺少 95% 区间", ["因果效果没有报告不确定性"])
    crosses = float(ci[0]) <= 0 <= float(ci[1])
    cards = state.get("action_cards") or []
    asks_to_scale = any("放大" in str(card.get("title", "")) for card in cards)
    quasi_or_experimental = any(
        item.get("id") in {"did_effect", "iptw_effect", "fixed_effect_estimate"}
        or item.get("type") == "ab_test_result"
        or item.get("experimental") is True
        for item in state.get("artifacts") or []
    )
    unsafe = asks_to_scale and (crosses or not quasi_or_experimental)
    score = 0.25 if unsafe else 0.72 if crosses else 1.0
    if unsafe:
        issues = ["当前证据尚不足以支持直接放大，应改为小范围延续验证"]
    else:
        issues = ["区间穿过 0，只能建议继续验证"] if crosses else []
    return _dimension("uncertainty_handling", score, f"95% 区间 {ci}", issues)


def _actionability(state: dict[str, Any], phase: str) -> CriticDimension:
    if phase == "prewrite":
        return _dimension("actionability", 1.0, "写作前阶段暂不评分", [])
    cards = state.get("action_cards") or (state.get("user_artifact") or {}).get("action_cards") or []
    if not cards:
        return _dimension("actionability", 0.0, "没有行动卡", ["缺少用户可执行的下一步"])
    actionable = sum(bool(card.get("action") or card.get("next_step") or card.get("title")) for card in cards)
    score = actionable / len(cards)
    issues = [] if score >= 0.7 else ["行动卡缺少明确动作"]
    return _dimension("actionability", score, f"{actionable}/{len(cards)} 张卡具备动作", issues)


def _privacy(state: dict[str, Any]) -> CriticDimension:
    report = state.get("governance_report") or state.get("validation_report") or {}
    checks = report.get("checks") or []
    privacy = next((item for item in checks if item.get("name") == "privacy"), {})
    blocked = bool(privacy.get("blocking") or report.get("block_output"))
    return _dimension("privacy", 0.0 if blocked else 1.0, "隐私门禁", ["检测到敏感信息"] if blocked else [])


def _traceability(state: dict[str, Any]) -> CriticDimension:
    names = {item.get("step") or item.get("node") for item in state.get("trace") or []}
    required = {"CompileTask", "ExecuteSkills", "ValidateArtifacts"}
    missing = sorted(required - names)
    score = 1.0 - len(missing) / len(required)
    return _dimension("traceability", score, f"追踪步骤：{sorted(name for name in names if name)}", [f"缺少追踪步骤：{', '.join(missing)}"] if missing else [])


def _dimension(name: str, score: float, evidence: str, issues: list[str]) -> CriticDimension:
    if not math.isfinite(float(score)):
        score = 0.0
    return CriticDimension(name=name, score=round(max(0.0, min(1.0, float(score))), 4), weight=WEIGHTS[name], evidence=evidence, issues=issues)


def _artifact(state: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    item = next((row for row in state.get("artifacts") or [] if row.get("id") == artifact_id), {})
    return item.get("content", item) if item else {}


def _is_causal(state: dict[str, Any]) -> bool:
    return (state.get("task_spec") or {}).get("task_type") in {"causal_effect_estimation", "counterfactual_analysis", "experiment_design"}


def _failure_type(dimension: str) -> str:
    return {
        "task_grounding": "task_grounding_error",
        "route_confidence": "routing_ambiguity",
        "artifact_integrity": "artifact_missing",
        "statistical_validity": "estimator_misuse",
        "causal_validity": "causal_overclaim",
        "uncertainty_handling": "uncertainty_ignored",
        "actionability": "unsafe_action",
        "privacy": "privacy_error",
        "traceability": "trace_incomplete",
    }[dimension]


def _repair_directive(failure_type: str, issues: list[str]) -> dict[str, Any]:
    actions = {
        "task_grounding_error": "重新编译 TaskSpec，并明确处理变量、结果变量和分析单位",
        "routing_ambiguity": "调用 L3 受约束路由；仍不明确时向用户提出一个澄清问题",
        "artifact_missing": "补跑缺失的 Python Skill，不允许 Writer 自行补数字",
        "estimator_misuse": "回退到描述性比较或更换满足数据条件的估计器",
        "causal_overclaim": "降级证据等级并补跑 CausalReadinessSkill",
        "uncertainty_ignored": "补跑 Bootstrap；区间跨零时改为小范围验证",
        "unsafe_action": "重写为包含范围、周期、指标和停止条件的行动卡",
        "privacy_error": "阻断输出并清除手机号、邮箱或密钥",
        "trace_incomplete": "补写编译、执行和校验追踪事件",
    }
    return {"failure_type": failure_type, "action": actions[failure_type], "issues": issues}


def _dedupe_directives(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output = []
    for row in rows:
        key = row["failure_type"]
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output
