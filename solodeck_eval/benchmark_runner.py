from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from .baselines import BASELINES, Baseline, run_baseline
from .datasets import BenchmarkCase, build_benchmark_cases
from .trajectory import TokenUsage, TrajectoryLogger, TrajectoryStep
from solodeck_v4.bench.synthetic_scm import generate_business_scm_suite


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "eval"


def run_benchmark(limit: int = 60, output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    generate_business_scm_suite(count=20, seed=20261104, output_dir=root / "synthetic_scm")
    cases = build_benchmark_cases()[:limit]
    rows = [run_baseline(case, baseline) for baseline in BASELINES for case in cases]
    summaries = _summarize(rows, BASELINES)
    result = {
        "suite": "SoloDeck-Agent-Eval-60",
        "reproducibility": {"seed": 20260904, "task_count": len(cases), "external_api_calls": 0},
        "dataset_sources": _source_counts(cases),
        "baseline_disclosure": {baseline.name: baseline.note for baseline in BASELINES},
        "summary": summaries,
        "rows": rows,
    }
    (root / "benchmark_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "baseline_results.md").write_text(_markdown(result), encoding="utf-8")
    _write_demo_trajectory(cases[-1], root / "demo_trajectory.jsonl")
    return result


def _summarize(rows: list[dict[str, Any]], baselines: tuple[Baseline, ...]) -> dict[str, Any]:
    result = {}
    for baseline in baselines:
        selected = [row for row in rows if row["baseline"] == baseline.name]
        result[baseline.name] = {
            "success_rate": round(mean(float(row["success"]) for row in selected), 4),
            "average_tool_calls": round(mean(row["tool_calls"] for row in selected), 4),
            "execution_error_rate": round(mean(row["execution_error"] for row in selected), 4),
            "average_latency_ms": round(mean(row["latency_ms"] for row in selected), 4),
            "average_tokens": round(mean(row["token_usage"] for row in selected), 4),
            "average_token_cost": round(mean(row["token_cost"] for row in selected), 6),
        }
    return result


def _source_counts(cases: list[BenchmarkCase]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for case in cases:
        counts[case.source] += 1
    return dict(counts)


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# SoloDeck Baseline Results",
        "",
        f"任务数：{result['reproducibility']['task_count']}；固定随机种子：{result['reproducibility']['seed']}。",
        "",
        "> 说明：A 是不调用外部模型的 direct-LLM 离线代理，只用于验证评测管线；不能作为真实大模型能力结论。其余基线也在离线执行器上比较路由与工具策略。",
        "",
        "| Baseline | Success rate | Avg tool calls | Execution error | Latency (ms) | Tokens | Token cost |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in result["summary"].items():
        lines.append(
            f"| {name} | {row['success_rate']:.1%} | {row['average_tool_calls']:.2f} | "
            f"{row['execution_error_rate']:.1%} | {row['average_latency_ms']:.3f} | "
            f"{row['average_tokens']:.0f} | {row['average_token_cost']:.4f} |"
        )
    lines.extend([
        "", "## Dataset composition", "",
        *[f"- `{name}`: {count}" for name, count in result["dataset_sources"].items()],
        "", "## Interpretation", "",
        "该结果证明评测、工具执行和自动校验链路可运行，不代表已完成 Agent RL 训练。",
        "官方 InfiAgent-DABench 与 DS-1000 尚未整库导入；当前使用本地兼容任务验证接口，后续可通过适配器替换数据源。",
    ])
    return "\n".join(lines) + "\n"


def _write_demo_trajectory(case: BenchmarkCase, path: Path) -> None:
    if path.exists():
        path.unlink()
    logger = TrajectoryLogger(path)
    stages = [
        ("planner", "plan", {"kind": case.kind, "goal": case.task}, 0.2),
        ("router", "causal", {"action_space": ["sql", "python", "plot", "causal", "search", "memory", "finish"]}, 0.8),
        ("executor", "causal", {"estimate": case.expected + 0.03, "method": "OLS adjustment", "covariates": ["Z"]}, 1.0),
        ("critic", "verify", {"valid": True, "absolute_error": 0.03, "true_ate": case.expected}, 1.0),
        ("report", "finish", {"claim": "调整混杂变量 Z 后，估计结果接近 SCM 真值。"}, 0.5),
    ]
    tools = ["sql", "python", "plot", "causal", "search", "memory", "finish"]
    for index, (role, tool, observation, reward) in enumerate(stages, 1):
        logger.append(TrajectoryStep(
            task_id=case.task_id,
            step_id=f"demo:{index:03d}",
            timestamp=f"2026-09-04T00:00:0{index}+00:00",
            state_context_summary={"role": role, "task": case.task, "kind": case.kind},
            available_tools=tools,
            selected_tool=tool,
            arguments={"treatment": "T", "outcome": "Y", "covariates": ["Z"]} if tool == "causal" else {},
            observation=observation,
            execution_status="ok",
            latency_ms=float(index * 3),
            token_usage=TokenUsage().__dict__,
            intermediate_reward=reward,
            final_reward=3.5 if index == len(stages) else None,
            metadata={"source": case.source, "ground_truth_available": True},
        ))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reproducible SoloDeck agent benchmark")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    result = run_benchmark(limit=max(1, min(args.limit, 100)), output_dir=args.output)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
