from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

from solodeck_eval.benchmark_runner import run_benchmark
from solodeck_eval.datasets import build_benchmark_cases
from solodeck_eval.router import ACTION_SPACE, route_tool
from solodeck_eval.trajectory import TrajectoryLogger, TrajectoryStep, TokenUsage
from solodeck_eval.verifier import EvaluationVerifier
from solodeck_v4.bench.synthetic_scm import generate_business_scm_suite


def test_router_has_replaceable_seven_action_interface() -> None:
    assert ACTION_SPACE == ("sql", "python", "plot", "causal", "search", "memory", "finish")
    assert route_tool({"task": "控制混杂后估计 ATE", "kind": "causal"}).action == "causal"
    external = route_tool({"task": "x"}, policy=lambda state, actions: {"action": "memory", "confidence": 0.9})
    assert external.action == "memory"


def test_trajectory_logger_writes_required_jsonl_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "trace.jsonl"
        logger = TrajectoryLogger(path)
        logger.append(TrajectoryStep(
            task_id="t1", step_id="s1", timestamp="2026-09-04T00:00:00+00:00",
            state_context_summary={"task": "test"}, available_tools=list(ACTION_SPACE),
            selected_tool="python", arguments={}, observation={"answer": 3},
            execution_status="ok", latency_ms=1.0, token_usage=TokenUsage().__dict__,
            intermediate_reward=1.0, final_reward=1.0,
        ))
        row = json.loads(path.read_text(encoding="utf-8"))
        required = json.loads((Path(__file__).parents[1] / "solodeck_eval" / "trajectory_schema.json").read_text())["required"]
        assert set(required).issubset(row)


def test_verifier_executes_python_sql_and_checks_consistency() -> None:
    verifier = EvaluationVerifier()
    python = verifier.python_correctness("answer = np.mean(values)", context={"values": [1, 2, 3]}, result_variable="answer", expected=2)
    assert python["valid"]
    sql = verifier.sql_correctness("SELECT SUM(value) AS total FROM data", {"data": pd.DataFrame({"value": [1, 2, 3]})})
    assert sql["valid"] and sql["details"]["result"][0]["total"] == 6
    frame = pd.DataFrame({"x": [1, 2]})
    assert verifier.dataframe_consistency(frame, frame.copy())["valid"]
    assert verifier.report_number_consistency("调整后增量为 1.25", [1.25])["valid"]


def test_scm_suite_and_benchmark_are_reproducible() -> None:
    suite = generate_business_scm_suite(count=20, seed=7)
    assert len(suite) == 20
    assert suite[0].dag == [("Z", "T"), ("Z", "Y"), ("T", "Y")]
    assert set(suite[0].data.columns) == {"Z", "T", "Y"}
    cases = build_benchmark_cases()
    assert len(cases) == 60
    assert {case.source for case in cases} == {
        "InfiAgent-DABench-compatible-local",
        "DS-1000-Pandas-Numpy-compatible-local",
        "SoloDeck-synthetic-SCM",
    }
    with tempfile.TemporaryDirectory() as tmp:
        result = run_benchmark(limit=6, output_dir=tmp)
        assert result["reproducibility"]["task_count"] == 6
        assert len(result["rows"]) == 24
        assert (Path(tmp) / "demo_trajectory.jsonl").exists()
