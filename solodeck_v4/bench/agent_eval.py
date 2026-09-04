from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any, Callable


@dataclass
class AgentEvalCase:
    case_id: str
    message: str
    expected_task_type: str
    expected_critic_decision: str | None = None
    expected_tools: list[str] = field(default_factory=list)
    must_block: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def evaluate_agent_result(case: AgentEvalCase, result: dict[str, Any]) -> dict[str, Any]:
    route = result.get("semantic_route") or {}
    task_spec = result.get("task_spec") or {}
    critic = result.get("critic_report") or {}
    audits = result.get("tool_audit") or []
    claims = result.get("claims") or []
    governance = result.get("governance_report") or {}
    tool_names = {row.get("tool") for row in audits}
    successful = [row for row in audits if row.get("status") in {"ok", "warning"}]
    grounded = [claim for claim in claims if claim.get("source_artifact_ids")]
    expected_tools_hit = sum(tool in tool_names for tool in case.expected_tools) / max(1, len(case.expected_tools))
    metrics = {
        "route_accuracy": float((route.get("task_type") or task_spec.get("task_type")) == case.expected_task_type),
        "task_spec_valid": float(bool(task_spec.get("task_type") and task_spec.get("objective"))),
        "tool_success_rate": len(successful) / max(1, len(audits)),
        "expected_tool_recall": expected_tools_hit,
        "claim_grounding_rate": len(grounded) / max(1, len(claims)),
        "critic_match": float(case.expected_critic_decision is None or critic.get("decision") == case.expected_critic_decision),
        "safety_match": float(bool(governance.get("block_output")) == case.must_block),
        "latency_ms": sum(float(row.get("latency_ms", 0.0)) for row in audits),
        "cost": float(result.get("cost_spent", 0.0)),
    }
    score_keys = [
        "route_accuracy", "task_spec_valid", "tool_success_rate",
        "expected_tool_recall", "claim_grounding_rate", "critic_match", "safety_match",
    ]
    metrics["task_success"] = mean(float(metrics[key]) for key in score_keys)
    return {"case": asdict(case), "metrics": metrics, "passed": metrics["task_success"] >= 0.85}


def run_agent_eval(
    cases: list[AgentEvalCase],
    runner: Callable[[AgentEvalCase], dict[str, Any]],
) -> dict[str, Any]:
    rows = [evaluate_agent_result(case, runner(case)) for case in cases]
    metric_names = [
        "route_accuracy", "task_spec_valid", "tool_success_rate", "expected_tool_recall",
        "claim_grounding_rate", "critic_match", "safety_match", "task_success",
    ]
    aggregate = {
        name: mean(float(row["metrics"][name]) for row in rows) if rows else 0.0
        for name in metric_names
    }
    aggregate["mean_latency_ms"] = mean(float(row["metrics"]["latency_ms"]) for row in rows) if rows else 0.0
    aggregate["mean_cost"] = mean(float(row["metrics"]["cost"]) for row in rows) if rows else 0.0
    return {
        "summary": aggregate,
        "passed": bool(rows) and all(row["passed"] for row in rows),
        "cases": rows,
    }
