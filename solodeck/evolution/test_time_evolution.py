from __future__ import annotations

import time
from typing import Any

import pandas as pd

from solodeck.runtime.method_scheduler import select_method
from solodeck.runtime.skill_runtime import BootstrapSkill, CausalDiscoverySkill, KGConstructionSkill, RegressionSkill
from solodeck.verification.validators import validate_final_artifacts
from solodeck.evolution.process_reward import assign_process_rewards


def generate_and_evaluate_plans(task_spec: Any, df: pd.DataFrame | None = None, query: dict[str, Any] | None = None, n_plans: int = 3) -> dict[str, Any]:
    spec = task_spec.to_dict() if hasattr(task_spec, "to_dict") else dict(task_spec)
    candidate_methods = ["bootstrap", "regression", "dag_then_bootstrap"]
    plans = []
    history: list[dict[str, Any]] = []
    for index in range(n_plans):
        started = time.time()
        method_info = select_method(candidate_methods, history, uncertainty=0.65 if spec.get("task_type") == "causal_strategy" else 0.25)
        method = method_info["method"]
        artifacts: dict[str, Any] = {"selected_method": method, "method_entropy": method_info["entropy"]}
        trace = [{"step": "PlanStart", "method": method}]
        if df is not None and query is not None:
            kg = KGConstructionSkill().run(df)
            dag = CausalDiscoverySkill().run(df, kg)
            effect = BootstrapSkill().run(df, query) if method != "regression" else RegressionSkill().run(df, query)
            artifacts.update({"knowledge_graph": kg, "candidate_dag": dag, "effect": effect, "bootstrap_ci": effect.get("ci_95")})
            trace.extend([{"step": "KGConstructionSkill"}, {"step": "CausalDiscoverySkill"}, {"step": "BootstrapSkill" if method != "regression" else "RegressionSkill"}])
        validation = validate_final_artifacts(artifacts, [a for a in spec.get("required_artifacts", []) if a not in {"schema", "quality_report", "action_cards"}], trace)
        rewards = assign_process_rewards(trace, validation)
        latency = time.time() - started
        score = rewards["total_reward"] + (2 if validation["valid"] else -1) - latency * 0.01
        plan = {"plan_id": f"plan_{index + 1}", "method": method, "artifacts": artifacts, "validation": validation, "reward": rewards, "latency": round(latency, 4), "score": round(score, 4)}
        history.append({"method": method, "valid": validation["valid"]})
        plans.append(plan)
    selected = sorted(plans, key=lambda x: x["score"], reverse=True)[0]
    return {"plans": plans, "selected_plan": selected, "pseudo_label": {"task_type": spec.get("task_type"), "method": selected["method"], "score": selected["score"]}}

