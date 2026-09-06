from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from solodeck_v4.bench.synthetic_scm import generate_business_scm_suite


@dataclass
class BenchmarkCase:
    task_id: str
    source: str
    kind: str
    task: str
    expected: float
    data: Any
    metadata: dict[str, Any] = field(default_factory=dict)


def build_benchmark_cases(seed: int = 20260904) -> list[BenchmarkCase]:
    """Build 60 deterministic tasks: 20 DABench-style, 20 DS-1000-style, 20 SCM."""
    return [*_business_cases(seed), *_array_cases(seed + 100), *_causal_cases(seed + 200)]


def _business_frame(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    size = 180
    platform = rng.choice(["xiaohongshu", "douyin", "bilibili", "wechat"], size=size)
    views = rng.integers(500, 35000, size=size)
    consultations = rng.binomial(views, np.select(
        [platform == "wechat", platform == "xiaohongshu", platform == "bilibili"],
        [0.012, 0.007, 0.005], default=0.004,
    ))
    conversions = rng.binomial(consultations, np.select(
        [platform == "wechat", platform == "xiaohongshu"], [0.38, 0.27], default=0.20,
    ))
    revenue = conversions * rng.choice([199, 499, 899, 1299], size=size)
    return pd.DataFrame({
        "platform": platform,
        "views": views,
        "consultations": consultations,
        "conversions": conversions,
        "revenue": revenue.astype(float),
    })


def _business_cases(seed: int) -> list[BenchmarkCase]:
    frame = _business_frame(seed)
    cases = []
    metrics = ["revenue", "views", "consultations", "conversions"]
    for index in range(20):
        metric = metrics[index % len(metrics)]
        aggregation = "sum" if index % 2 == 0 else "mean"
        grouped = frame.groupby("platform")[metric].agg(aggregation)
        expected = float(grouped.max())
        sql_agg = "SUM" if aggregation == "sum" else "AVG"
        sql = f"SELECT MAX(value) AS answer FROM (SELECT platform, {sql_agg}({metric}) AS value FROM data GROUP BY platform)"
        cases.append(BenchmarkCase(
            task_id=f"dabench_compat_{index + 1:03d}",
            source="InfiAgent-DABench-compatible-local",
            kind="sql" if index < 10 else "pandas",
            task=f"按平台计算{metric}的{aggregation}，返回最高的平台数值。",
            expected=expected,
            data=frame,
            metadata={"operation": "group_max", "metric": metric, "aggregation": aggregation, "sql": sql},
        ))
    return cases


def _array_cases(seed: int) -> list[BenchmarkCase]:
    rng = np.random.default_rng(seed)
    operations = ["mean", "median", "sum", "std", "max", "min", "p75", "nonzero", "variance", "range"]
    cases = []
    for index in range(20):
        values = rng.normal(loc=index % 5, scale=1 + (index % 3) * 0.4, size=40 + index).round(6)
        operation = operations[index % len(operations)]
        expected = _array_answer(values, operation)
        cases.append(BenchmarkCase(
            task_id=f"ds1000_compat_{index + 1:03d}",
            source="DS-1000-Pandas-Numpy-compatible-local",
            kind="numpy",
            task=f"使用 NumPy 计算数组的 {operation}。",
            expected=expected,
            data=values,
            metadata={"operation": operation},
        ))
    return cases


def _causal_cases(seed: int) -> list[BenchmarkCase]:
    tasks = generate_business_scm_suite(count=20, seed=seed)
    return [BenchmarkCase(
        task_id=task.task_id,
        source="SoloDeck-synthetic-SCM",
        kind="causal",
        task="控制混杂变量 Z 后，估计策略 T 对结果 Y 的 ATE。",
        expected=float(task.true_ate),
        data=task.data,
        metadata={"treatment": "T", "outcome": "Y", "confounders": ["Z"], "dag": task.dag},
    ) for task in tasks]


def _array_answer(values: np.ndarray, operation: str) -> float:
    operations = {
        "mean": lambda x: np.mean(x), "median": lambda x: np.median(x),
        "sum": lambda x: np.sum(x), "std": lambda x: np.std(x),
        "max": lambda x: np.max(x), "min": lambda x: np.min(x),
        "p75": lambda x: np.percentile(x, 75), "nonzero": lambda x: np.count_nonzero(x),
        "variance": lambda x: np.var(x), "range": lambda x: np.max(x) - np.min(x),
    }
    return float(operations[operation](values))
