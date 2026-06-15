from __future__ import annotations

from typing import Any


def route_model(task_type: str, risk_level: str = "normal") -> dict[str, Any]:
    """Route LLM calls across configured SoloDeck model profiles without exposing keys."""
    if task_type in {"report_polish", "causal_explanation", "critical_review"} or risk_level == "high":
        return {"profile": "advanced", "reason": "关键解释或高风险结论使用高级模型复核。"}
    return {"profile": "basic", "reason": "普通抽取、摘要和低风险建议使用低成本长上下文模型。"}


def call_routed_llm(system_prompt: str, payload: dict[str, Any] | str, task_type: str, risk_level: str = "normal", language: str = "中文") -> dict[str, Any]:
    route = route_model(task_type, risk_level)
    try:
        from solo_creator_agent.src.llm_agent import call_llm

        text = call_llm(system_prompt, payload, language=language, profile=route["profile"])
        return {"ok": True, "profile": route["profile"], "text": text, "reason": route["reason"]}
    except Exception as exc:
        return {"ok": False, "profile": route["profile"], "text": "", "reason": route["reason"], "error": str(exc)}

