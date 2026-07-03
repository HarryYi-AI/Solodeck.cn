from __future__ import annotations

import re
from typing import Any


def validate_retrieval_evidence(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure final answers cite grounded evidence and flag unsafe causal/numeric claims."""
    pack = state.get("evidence_pack") or state.get("retrieved_memory") or {}
    evidence = pack.get("evidence") or []
    evidence_index = {item.get("source_id"): item for item in evidence if item.get("source_id")}

    issues: list[str] = []
    warnings: list[str] = list(pack.get("warnings") or [])
    actions: list[str] = []

    user = state.get("user_artifact") or {}
    report = _text(user)
    citations = _extract_citations(report)
    for cite in citations:
        if cite not in evidence_index:
            issues.append(f"终稿引用了未检索到的证据: {cite}")

    task_spec = state.get("task_spec") or {}
    intent = (pack.get("retrieval_plan") or "").split(" ->")[0].strip()
    is_causal = intent == "causal_question" or task_spec.get("task_type") in {
        "causal_effect_estimation",
        "counterfactual_analysis",
    }

    source_types = {item.get("source_type") for item in evidence}
    if is_causal and source_types <= {"text", "session"}:
        warnings.append("因果问题仅依赖文本/会话证据")
        actions.append("force_causal_readiness_check")
        state["force_causal_readiness"] = True

    numeric_claim = bool(re.search(r"\d+\.?\d*%?", report))
    has_calculation_evidence = any(
        item.get("source_type") in {"python", "sql"}
        or (
            item.get("source_type") == "artifact"
            and (item.get("structured_payload") or item.get("meta") or {}).get("generated_by") not in {None, "ReportSkill", "WriterAgent", "llm"}
        )
        for item in evidence
    )
    has_calculation_evidence = has_calculation_evidence or any(
        artifact.get("source_type") in {"python", "sql"}
        and artifact.get("generated_by") not in {None, "ReportSkill", "WriterAgent", "llm"}
        for artifact in state.get("artifacts", [])
    )
    if numeric_claim and not has_calculation_evidence:
        issues.append("数值结论缺少 Python/SQL 计算证据")
        actions.append("require_python_skill_or_mark_unavailable")
        if user:
            warning = "数值结论需 Python 技能重算或标记为不可用"
            if warning not in (user.get("limitations") or ""):
                user["limitations"] = ((user.get("limitations") or "") + "；" + warning).strip("；")
            state["user_artifact"] = user

    valid = not issues
    return {
        "name": "retrieval_evidence",
        "valid": valid,
        "issues": issues,
        "warnings": warnings,
        "actions": actions,
        "evidence_count": len(evidence),
        "cited_sources": citations,
    }


def _extract_citations(text: str) -> list[str]:
    bracket = re.findall(r"\[(schema|kg|artifact|session|text):[^\]]+\]", text, re.I)
    inline = re.findall(r"(schema:[\w.-]+|kg:[^\s]+|artifact:[\w.-]+|session:[\w.-]+|text:[\w.-]+)", text, re.I)
    return list(dict.fromkeys(bracket + inline))


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values())
    return str(value)
