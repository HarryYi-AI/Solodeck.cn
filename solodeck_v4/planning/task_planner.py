from __future__ import annotations

from typing import Any


def plan_task_steps(task_spec: dict[str, Any], risk_profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Orchestrated multi-step plan — tools mapped per step."""
    task_type = task_spec.get("task_type", "descriptive_analysis")
    fast = risk_profile.get("budget_level") == "fast_path"
    reuse = risk_profile.get("reuse_cache", False)

    steps = [
        {"id": "s1", "phase": "understand", "tool": "retrieve_memory", "goal": "加载压缩会话与经营记忆"},
        {"id": "s2", "phase": "understand", "tool": "compile_task", "goal": "编译 TaskSpec 并链接实体"},
    ]

    if reuse:
        steps.append({"id": "s3", "phase": "analyze", "tool": "execute_analysis", "goal": "复用缓存产物（低成本）"})
    else:
        steps.extend([
            {"id": "s4", "phase": "analyze", "tool": "execute_analysis", "goal": "执行 Python Skills 计算"},
        ])

    if not fast:
        steps.append({"id": "s5", "phase": "verify", "tool": "validate_artifacts", "goal": "统计/因果/隐私校验"})

    steps.append({"id": "s6", "phase": "write", "tool": "compose_response", "goal": "编排生成行动卡片与报告"})
    return [s for s in steps if not s.get("skip")]


def default_tool_sequence(risk_profile: dict[str, Any]) -> list[str]:
    if risk_profile.get("needs_clarification"):
        return ["clarify"]
    if risk_profile.get("reuse_cache"):
        return ["retrieve_memory", "compile_task", "execute_analysis", "compose_response"]
    fast = risk_profile.get("budget_level") == "fast_path"
    seq = ["retrieve_memory", "compile_task", "execute_analysis"]
    if not fast:
        seq.append("validate_artifacts")
    seq.append("compose_response")
    return seq
