from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class SyntheticSCMTask:
    task_id: str
    dag: list[tuple[str, str]]
    treatment: str
    outcome: str
    confounders: list[str]
    true_ate: float
    hidden_confounding: bool
    noise_level: float
    sample_size: int
    data: pd.DataFrame

    def metadata(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("data")
        return value


def generate_scm_task(
    task_id: str = "scm_001", sample_size: int = 500, effect_size: float = 2.0,
    hidden_confounding: bool = False, noise_level: float = 1.0, seed: int = 42,
) -> SyntheticSCMTask:
    rng = np.random.default_rng(seed)
    account_size = rng.normal(0, 1, sample_size)
    topic_quality = rng.normal(0, 1, sample_size)
    hidden = rng.normal(0, 1, sample_size) if hidden_confounding else np.zeros(sample_size)
    logits = 0.8 * account_size + 0.5 * topic_quality + 0.8 * hidden
    propensity = 1 / (1 + np.exp(-logits))
    treatment = rng.binomial(1, propensity)
    outcome = effect_size * treatment + 1.4 * account_size + 0.9 * topic_quality + 1.3 * hidden + rng.normal(0, noise_level, sample_size)
    data = pd.DataFrame({"strategy": treatment, "revenue": outcome, "account_size": account_size, "topic_quality": topic_quality})
    return SyntheticSCMTask(
        task_id=task_id,
        dag=[("account_size", "strategy"), ("topic_quality", "strategy"), ("account_size", "revenue"), ("topic_quality", "revenue"), ("strategy", "revenue")],
        treatment="strategy", outcome="revenue", confounders=["account_size", "topic_quality"],
        true_ate=effect_size, hidden_confounding=hidden_confounding,
        noise_level=noise_level, sample_size=sample_size, data=data,
    )


def evaluate_scm_run(task: SyntheticSCMTask, result: dict[str, Any]) -> dict[str, float]:
    predicted_treatment = result.get("treatment")
    predicted_outcome = result.get("outcome")
    predicted_confounders = set(result.get("confounders") or [])
    predicted_edges = {tuple(edge[:2]) for edge in result.get("dag", []) if len(edge) >= 2}
    true_edges = set(task.dag)
    estimate = result.get("ate")
    level = int(result.get("evidence_level", 1))
    strong_claim = bool(result.get("strong_causal_claim"))
    return {
        "treatment_extraction_accuracy": float(predicted_treatment == task.treatment),
        "outcome_extraction_accuracy": float(predicted_outcome == task.outcome),
        "confounder_recall": len(predicted_confounders & set(task.confounders)) / max(1, len(task.confounders)),
        "dag_edge_precision": len(predicted_edges & true_edges) / max(1, len(predicted_edges)),
        "dag_edge_recall": len(predicted_edges & true_edges) / max(1, len(true_edges)),
        "ate_absolute_error": abs(float(estimate) - task.true_ate) if estimate is not None else float("inf"),
        "causal_overclaim": float(strong_claim and (task.hidden_confounding or level < 4)),
        "evidence_level_correct": float((not task.hidden_confounding and level >= 4) or (task.hidden_confounding and level <= 3)),
        "action_safety_score": float(not strong_claim or not task.hidden_confounding),
    }


def generate_business_scm_suite(
    count: int = 20,
    *,
    sample_size: int = 600,
    seed: int = 20260904,
    output_dir: str | Path | None = None,
) -> list[SyntheticSCMTask]:
    """Generate Z -> T, Z -> Y, T -> Y tasks with known ATE."""
    tasks = []
    for index in range(count):
        rng = np.random.default_rng(seed + index)
        effect = 0.5 + 0.15 * (index % 10)
        z = rng.normal(0, 1, sample_size)
        propensity = 1 / (1 + np.exp(-(-0.15 + (0.55 + 0.04 * (index % 4)) * z)))
        treatment = rng.binomial(1, propensity)
        outcome = effect * treatment + (0.9 + 0.1 * (index % 3)) * z + rng.normal(0, 0.65, sample_size)
        frame = pd.DataFrame({"Z": z, "T": treatment, "Y": outcome})
        tasks.append(SyntheticSCMTask(
            task_id=f"business_scm_{index + 1:03d}",
            dag=[("Z", "T"), ("Z", "Y"), ("T", "Y")],
            treatment="T",
            outcome="Y",
            confounders=["Z"],
            true_ate=effect,
            hidden_confounding=False,
            noise_level=0.65,
            sample_size=sample_size,
            data=frame,
        ))
    if output_dir is not None:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        metadata = []
        for task in tasks:
            task.data.to_csv(root / f"{task.task_id}.csv", index=False)
            metadata.append(task.metadata())
        (root / "ground_truth.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    return tasks
