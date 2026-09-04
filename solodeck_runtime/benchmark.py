from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Callable

import pandas as pd

from .grounding import DataGrounder
from .models import TaskSpec
from .verifier import ActiveVerifier
from .workflow import WorkflowCompiler, WorkflowValidator


@dataclass
class BenchmarkCaseResult:
    case_id: str
    category: str
    passed: bool
    latency_ms: float
    details: dict


def run_solodatabench_lite() -> dict:
    """Deterministic smoke benchmark for grounding, planning and silent errors."""
    cases: list[tuple[str, str, Callable[[], tuple[bool, dict]]]] = [
        ("grounding_alias_join", "data_grounding", _case_alias_join),
        ("workflow_causal_guard", "data_analysis", _case_causal_workflow),
        ("silent_join_inflation", "reliability", _case_join_inflation),
        ("zero_denominator", "reliability", _case_zero_denominator),
    ]
    results = []
    for case_id, category, execute in cases:
        started = perf_counter()
        try:
            passed, details = execute()
        except Exception as exc:
            passed, details = False, {"error": f"{type(exc).__name__}: {exc}"}
        results.append(BenchmarkCaseResult(
            case_id, category, passed, round((perf_counter() - started) * 1000, 3), details,
        ))
    passed = sum(item.passed for item in results)
    return {
        "suite": "SoloDataBench-lite",
        "summary": {"passed": passed, "total": len(results), "task_success": passed / max(1, len(results))},
        "results": [asdict(item) for item in results],
    }


def _case_alias_join() -> tuple[bool, dict]:
    datasets = {
        "orders": pd.DataFrame({"cust_id": ["u1", "u2"], "amount": [10, 20]}),
        "users": pd.DataFrame({"user_identifier": ["u1", "u2"], "segment": ["new", "old"]}),
    }
    result = DataGrounder().ground(TaskSpec("按用户分析收入", "data_analysis"), datasets)
    candidate = result.join_candidates[0] if result.join_candidates else {}
    passed = candidate.get("canonical_entity") == "customer_id" and candidate.get("confidence", 0) > 0.9
    return passed, candidate


def _case_causal_workflow() -> tuple[bool, dict]:
    data = pd.DataFrame({"treatment": [0, 1] * 8, "outcome": range(16)})
    task = TaskSpec("处理是否影响结果", "causal_effect_estimation", treatment="treatment", outcome="outcome")
    grounding = DataGrounder().ground(task, {"data": data})
    workflow = WorkflowCompiler().compile(task, grounding)
    validation = WorkflowValidator().validate(workflow, datasets={"data": data})
    operations = [node.operation_type for node in workflow.physical_nodes]
    passed = validation["valid"] and operations.index("CausalReadiness") < operations.index("ValidateClaim")
    return passed, {"operations": operations, "validation": validation}


def _case_join_inflation() -> tuple[bool, dict]:
    left = pd.DataFrame({"id": [1, 1], "revenue": [10, 20]})
    right = pd.DataFrame({"id": [1, 1], "label": ["a", "b"]})
    report = ActiveVerifier().inspect_join(left, right, left_on="id", right_on="id")
    return not report["valid"], report


def _case_zero_denominator() -> tuple[bool, dict]:
    frame = pd.DataFrame({"orders": [1, 0], "visitors": [0, 10], "conversion_rate": [0.0, 0.0]})
    report = ActiveVerifier().inspect_rate(frame, "orders", "visitors", frame["conversion_rate"])
    detected = report["probes"].get("zero_denominators") == 1 and bool(report.get("warnings"))
    return detected, report


if __name__ == "__main__":
    import json

    print(json.dumps(run_solodatabench_lite(), ensure_ascii=False, indent=2))
