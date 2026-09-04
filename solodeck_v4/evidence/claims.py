from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from uuid import uuid4


ClaimType = Literal["descriptive", "adjusted_association", "causal_hypothesis", "quasi_causal", "experimental", "action"]


@dataclass
class ClaimRecord:
    text: str
    claim_type: ClaimType
    evidence_level: int
    source_artifact_ids: list[str]
    calculation_method: str
    confidence: str
    limitations: str
    applicable_scope: str
    status: str = "proposed"
    claim_id: str = field(default_factory=lambda: f"claim_{uuid4().hex[:16]}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_claim_records(state: dict[str, Any]) -> list[dict[str, Any]]:
    report = state.get("final_report") or {}
    artifacts = {item.get("id"): item for item in state.get("artifacts") or [] if item.get("id")}
    claims: list[ClaimRecord] = []
    result = str(report.get("result") or "").strip()
    if result:
        claim_type, level, sources = _result_provenance(state, artifacts)
        claims.append(ClaimRecord(
            text=result[:1200],
            claim_type=claim_type,
            evidence_level=level,
            source_artifact_ids=sources,
            calculation_method=str(report.get("method") or "确定性 Python 计算")[:300],
            confidence=str(report.get("confidence") or "需要验证")[:120],
            limitations=str(report.get("limitation") or "")[:500],
            applicable_scope=_scope(state),
        ))
    for card in state.get("action_cards") or []:
        text = str(card.get("action") or card.get("next_step") or card.get("title") or "").strip()
        if not text:
            continue
        references = [ref for ref in card.get("references", []) if ref in artifacts]
        if not references:
            references = _default_sources(artifacts)
        claims.append(ClaimRecord(
            text=text[:800],
            claim_type="action",
            evidence_level=min(3, int(state.get("evidence_level") or 1)),
            source_artifact_ids=references,
            calculation_method="规则化行动生成",
            confidence=str(card.get("confidence") or report.get("confidence") or "需要验证")[:120],
            limitations=str(report.get("limitation") or "行动前需按卡片条件验证")[:500],
            applicable_scope=_scope(state),
        ))
    return [claim.to_dict() for claim in claims]


def validate_claim_records(state: dict[str, Any]) -> dict[str, Any]:
    artifacts = {item.get("id"): item for item in state.get("artifacts") or [] if item.get("id")}
    claims = state.get("claims") or []
    issues: list[str] = []
    warnings: list[str] = []
    for claim in claims:
        claim_id = claim.get("claim_id", "unknown")
        sources = claim.get("source_artifact_ids") or []
        missing = [source for source in sources if source not in artifacts]
        if missing:
            issues.append(f"{claim_id} 引用了不存在的工件: {', '.join(missing)}")
        numeric = bool(re.search(r"-?\d+(?:\.\d+)?%?", str(claim.get("text", ""))))
        calculated = any(
            artifacts[source].get("source_type") in {"python", "sql"}
            and artifacts[source].get("generated_by") not in {None, "ReportSkill", "WriterAgent"}
            for source in sources if source in artifacts
        )
        if numeric and not calculated:
            issues.append(f"{claim_id} 的数值没有绑定 Python/SQL 工件")
        if int(claim.get("evidence_level", 1)) <= 3 and re.search(r"证明|必然|一定导致|保证", str(claim.get("text", ""))):
            issues.append(f"{claim_id} 的措辞强于证据等级")
        if not claim.get("limitations"):
            warnings.append(f"{claim_id} 缺少限制说明")
        if not claim.get("applicable_scope"):
            warnings.append(f"{claim_id} 缺少适用范围")
    if not claims and state.get("final_report"):
        issues.append("报告尚未生成 Claim Ledger")
    return {"name": "claim_evidence", "valid": not issues, "issues": issues, "warnings": warnings, "blocking": bool(issues)}


def _result_provenance(state: dict[str, Any], artifacts: dict[str, dict[str, Any]]) -> tuple[ClaimType, int, list[str]]:
    if "descriptive_comparison" in artifacts:
        return "descriptive", 1, ["descriptive_comparison"]
    if any(artifacts.get(name) for name in ("did_effect", "iptw_effect", "fixed_effect_estimate")):
        sources = [name for name in ("did_effect", "iptw_effect", "fixed_effect_estimate", "causal_readiness") if name in artifacts]
        return "quasi_causal", 4, sources
    if "bootstrap_ci" in artifacts or "regression_effect" in artifacts:
        sources = [name for name in ("bootstrap_ci", "regression_effect", "causal_readiness") if name in artifacts]
        return "adjusted_association", 2, sources
    if "causal_context" in artifacts:
        return "causal_hypothesis", 3, ["causal_context"]
    return "descriptive", 1, _default_sources(artifacts)


def _default_sources(artifacts: dict[str, dict[str, Any]]) -> list[str]:
    preferred = ["descriptive_comparison", "bootstrap_ci", "regression_effect", "causal_readiness", "data_quality_report"]
    return [name for name in preferred if name in artifacts][:3]


def _scope(state: dict[str, Any]) -> str:
    spec = state.get("task_spec") or {}
    unit = spec.get("unit") or "当前记录"
    time = spec.get("time") or "当前上传数据周期"
    return f"分析单位：{unit}；观察范围：{time}"
