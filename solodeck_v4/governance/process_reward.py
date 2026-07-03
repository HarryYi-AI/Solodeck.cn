from __future__ import annotations

from typing import Any


def score_process(state: dict[str, Any], governance: dict[str, Any]) -> dict[str, Any]:
    spec = state.get("task_spec") or {}
    artifacts = state.get("artifacts") or []
    checks = {check["name"]: check for check in governance.get("checks", [])}
    events: list[dict[str, Any]] = []

    def add(points: int, rule: str, passed: bool) -> None:
        if passed:
            events.append({"points": points, "rule": rule})

    estimand_defined = bool(spec.get("candidate_treatments") and spec.get("candidate_outcomes") and spec.get("unit") and spec.get("time"))
    add(1, "处理、结果、单位和时间已定义", estimand_defined)
    add(-1, "必需字段缺失", not estimand_defined)
    add(1, "检索了与任务匹配的记忆源", bool((state.get("evidence_pack") or {}).get("evidence")))
    numeric_backed = any(a.get("source_type") in {"python", "sql"} and a.get("generated_by") not in {"ReportSkill", "WriterAgent"} for a in artifacts)
    add(1, "数值声明有 Python/SQL 工件", numeric_backed)
    downgraded = governance.get("evidence_level", 1) <= 3 and any("因果" in warning or "区间" in warning for warning in governance.get("warnings", []))
    add(1, "不支持的因果声明已降级", downgraded)
    add(1, "报告了不确定性", not checks.get("uncertainty", {}).get("issues"))
    add(1, "生成了安全验证计划", bool(governance.get("safe_next_step")))
    add(-2, "存在无支持的因果声明", bool(checks.get("causal_readiness", {}).get("blocking")))
    ignored_zero = any("穿过 0" in warning for warning in governance.get("warnings", [])) and checks.get("action_safety", {}).get("blocking")
    add(-2, "忽略置信区间穿过零", ignored_zero)
    text_numeric = bool(checks.get("claim", {}).get("issues"))
    add(-2, "文本证据被当作数值证据", text_numeric)
    add(-3, "发生隐私泄漏", bool(checks.get("privacy", {}).get("blocking")))
    return {"total": sum(event["points"] for event in events), "events": events}
