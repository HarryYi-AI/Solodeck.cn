from __future__ import annotations

import re
from enum import IntEnum
from typing import Any


class EvidenceLevel(IntEnum):
    DESCRIPTIVE = 1
    ADJUSTED_ASSOCIATION = 2
    EXPLORATORY_CAUSAL_HYPOTHESIS = 3
    QUASI_CAUSAL = 4
    EXPERIMENTAL = 5


LEVEL_LABELS = {
    1: "描述性现象", 2: "调整后关联", 3: "探索性因果假设",
    4: "准因果估计", 5: "实验性证据",
}


def run_governance_suite(state: dict[str, Any]) -> dict[str, Any]:
    checks = [
        _schema_validator(state), _estimand_validator(state), _causal_readiness_validator(state),
        _estimator_validity_validator(state), _uncertainty_validator(state),
        _graph_plausibility_validator(state), _claim_validator(state),
        _action_safety_validator(state), _privacy_validator(state), _trace_completeness_validator(state),
    ]
    issues = [issue for check in checks for issue in check["issues"]]
    warnings = [warning for check in checks for warning in check["warnings"]]
    level = _evidence_level(state, checks)
    return {
        "valid": not any(check["blocking"] for check in checks),
        "block_output": any(check["name"] == "privacy" and check["blocking"] for check in checks),
        "checks": checks, "issues": issues, "warnings": warnings,
        "evidence_level": int(level), "evidence_level_label": LEVEL_LABELS[int(level)],
        "safe_next_step": _safe_next_step(level, issues, warnings),
    }


def govern_claims(state: dict[str, Any], draft: str) -> dict[str, Any]:
    report = run_governance_suite({**state, "draft_answer": draft})
    revised = draft
    strong = r"(证明了|必然|一定会|导致了|保证|显著提升)"
    if report["evidence_level"] < EvidenceLevel.QUASI_CAUSAL and re.search(strong, revised):
        revised = re.sub(strong, "观察到与之相关", revised)
        report["warnings"].append("强因果措辞已自动降级")
    suffix = f"\n证据等级：{report['evidence_level_label']}。"
    if report["evidence_level"] <= EvidenceLevel.EXPLORATORY_CAUSAL_HYPOTHESIS:
        suffix += report["safe_next_step"]
    if "证据等级" not in revised:
        revised += suffix
    claim_issues = next((check["issues"] for check in report["checks"] if check["name"] == "claim"), [])
    if claim_issues:
        revised = f"当前没有可复核的计算工件，因此暂不展示数值结论。请先运行指标计算。\n证据等级：{report['evidence_level_label']}。"
    if report.get("block_output"):
        revised = "输出中检测到可能的敏感信息，已停止展示。请移除手机号、邮箱或密钥后重新分析。"
    return {**report, "answer": revised}


def _check(name: str, issues: list[str] | None = None, warnings: list[str] | None = None, blocking: bool = False) -> dict[str, Any]:
    return {"name": name, "valid": not issues, "issues": issues or [], "warnings": warnings or [], "blocking": blocking}


def _schema_validator(state: dict[str, Any]) -> dict[str, Any]:
    columns = set((state.get("schema_summary") or {}).get("columns") or [])
    if not columns and state.get("df") is not None:
        columns = set(getattr(state["df"], "columns", []))
    return _check("schema", [] if columns else ["缺少可验证的数据字段"], blocking=not columns)


def _estimand_validator(state: dict[str, Any]) -> dict[str, Any]:
    spec = state.get("task_spec") or {}
    causal = spec.get("task_type") in {"causal_effect_estimation", "counterfactual_analysis"}
    if not causal:
        return _check("estimand")
    missing = []
    if not spec.get("candidate_treatments"): missing.append("处理变量未定义")
    if not spec.get("candidate_outcomes"): missing.append("结果变量未定义")
    unit = spec.get("unit") or _artifact_value(state, "causal_readiness", "unit")
    time = spec.get("time") or _artifact_value(state, "causal_readiness", "time")
    if not unit: missing.append("分析单位未定义")
    if not time: missing.append("观察时间未定义")
    return _check("estimand", missing, blocking=bool(missing))


def _causal_readiness_validator(state: dict[str, Any]) -> dict[str, Any]:
    if not _is_causal(state):
        return _check("causal_readiness")
    readiness = _artifact(state, "causal_readiness")
    if not readiness:
        return _check("causal_readiness", ["缺少因果就绪度证据"], blocking=_is_causal(state))
    score = readiness.get("score", readiness.get("readiness_score", 0))
    normalized_score = float(score) / 100 if float(score) > 1 else float(score)
    ready = readiness.get("ready", readiness.get("causal_claim_allowed", normalized_score >= 0.7))
    return _check("causal_readiness", [] if ready else ["数据尚不满足稳健因果估计条件"], readiness.get("warnings", []), blocking=False)


def _estimator_validity_validator(state: dict[str, Any]) -> dict[str, Any]:
    estimates = [a for a in state.get("artifacts", []) if a.get("type") in {"effect_estimate", "bootstrap_result", "did_result"} or a.get("id") in {"bootstrap_ci", "regression_effect", "did_effect"}]
    if not _is_causal(state): return _check("estimator_validity")
    if not estimates: return _check("estimator_validity", ["缺少统计估计工件"], blocking=True)
    return _check("estimator_validity")


def _uncertainty_validator(state: dict[str, Any]) -> dict[str, Any]:
    estimate = _artifact(state, "bootstrap_ci") or _artifact(state, "did_effect") or _artifact(state, "regression_effect")
    if not estimate: return _check("uncertainty", warnings=["尚无区间估计"])
    ci = estimate.get("ci_95") or [estimate.get("ci_low"), estimate.get("ci_high")]
    if not ci or len(ci) != 2 or None in ci: return _check("uncertainty", ["效果估计缺少置信区间"])
    crosses = float(ci[0]) <= 0 <= float(ci[1])
    return _check("uncertainty", warnings=["95% 置信区间穿过 0，禁止强改善结论"] if crosses else [])


def _graph_plausibility_validator(state: dict[str, Any]) -> dict[str, Any]:
    graph = state.get("causal_context") or {}
    edges = graph.get("edges") or (graph.get("exploratory_causal_graph") or {}).get("edges") or []
    forbidden = [e for e in edges if e.get("relation") == "forbidden_direction" and e.get("selected")]
    return _check("graph_plausibility", ["候选图违反已知时间或方向约束"] if forbidden else [], ["候选图仅是探索性因果假设图，不代表真实因果结构"] if graph else [])


def _claim_validator(state: dict[str, Any]) -> dict[str, Any]:
    text = _all_text(state)
    numeric = bool(re.search(r"-?\d+(?:\.\d+)?%?", text))
    python_artifact = any(
        a.get("source_type") in {"python", "sql"}
        and a.get("generated_by") not in {None, "ReportSkill", "WriterAgent"}
        for a in state.get("artifacts", [])
    )
    issues = ["数值声明缺少 Python/SQL 计算工件"] if numeric and not python_artifact else []
    return _check("claim", issues, blocking=bool(issues))


def _action_safety_validator(state: dict[str, Any]) -> dict[str, Any]:
    estimate = _artifact(state, "bootstrap_ci")
    cards = state.get("action_cards") or []
    if not estimate or not cards: return _check("action_safety")
    ci = estimate.get("ci_95") or [0, 0]
    unsafe = float(ci[0]) <= 0 <= float(ci[1]) and any("放大" in str(c.get("title", "")) for c in cards)
    return _check("action_safety", ["不稳定区间对应了直接放大建议"] if unsafe else [], blocking=unsafe)


def _privacy_validator(state: dict[str, Any]) -> dict[str, Any]:
    text = _all_text(state)
    hit = bool(re.search(r"(?:1[3-9]\d{9})|(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})|(?:QC-[A-Za-z0-9-]{16,})", text))
    return _check("privacy", ["输出可能包含手机号、邮箱或密钥"] if hit else [], blocking=hit)


def _trace_completeness_validator(state: dict[str, Any]) -> dict[str, Any]:
    trace = state.get("trace") or []
    required = {"CompileTask", "ExecuteSkills", "ValidateArtifacts"}
    names = {row.get("node") or row.get("step") for row in trace}
    missing = sorted(required - names)
    return _check("trace_completeness", [f"追踪缺少步骤: {', '.join(missing)}"] if missing else [], blocking=bool(missing))


def _evidence_level(state: dict[str, Any], checks: list[dict[str, Any]]) -> EvidenceLevel:
    artifacts = state.get("artifacts") or []
    if any(a.get("type") == "ab_test_result" or a.get("experimental") is True for a in artifacts):
        return EvidenceLevel.EXPERIMENTAL
    if any(a.get("id") in {"did_effect", "iptw_effect", "fixed_effect_estimate"} for a in artifacts) and not _issues(checks, "causal_readiness"):
        return EvidenceLevel.QUASI_CAUSAL
    if state.get("causal_context"):
        return EvidenceLevel.EXPLORATORY_CAUSAL_HYPOTHESIS
    if any(a.get("id") in {"regression_effect", "bootstrap_ci"} for a in artifacts):
        return EvidenceLevel.ADJUSTED_ASSOCIATION
    return EvidenceLevel.DESCRIPTIVE


def _safe_next_step(level: EvidenceLevel, issues: list[str], warnings: list[str]) -> str:
    if level == EvidenceLevel.DESCRIPTIVE:
        return "先把它作为现状描述；若要判断策略效果，再补充对照数据。"
    if level == EvidenceLevel.ADJUSTED_ASSOCIATION:
        return "可用于筛选方向，但应先做小范围对照验证。"
    if level == EvidenceLevel.EXPLORATORY_CAUSAL_HYPOTHESIS:
        return "先验证关键假设，不建议直接全面放大。"
    if level >= EvidenceLevel.QUASI_CAUSAL and not issues:
        return "可小范围执行，并继续记录结果以复核稳定性。"
    if issues or warnings:
        return "先补齐对照组和观察时间，进行小范围验证。"
    return "先做低成本对照实验，再决定是否扩大投入。"


def _artifact(state: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    art = next((a for a in state.get("artifacts", []) if a.get("id") == artifact_id), {})
    return art.get("content", art) if art else {}


def _artifact_value(state: dict[str, Any], artifact_id: str, key: str) -> Any:
    return _artifact(state, artifact_id).get(key)


def _is_causal(state: dict[str, Any]) -> bool:
    return (state.get("task_spec") or {}).get("task_type") in {"causal_effect_estimation", "counterfactual_analysis"}


def _issues(checks: list[dict[str, Any]], name: str) -> list[str]:
    return next((c["issues"] for c in checks if c["name"] == name), [])


def _all_text(state: dict[str, Any]) -> str:
    return " ".join(str(state.get(key, "")) for key in ("draft_answer", "final_answer", "user_artifact", "final_report"))
