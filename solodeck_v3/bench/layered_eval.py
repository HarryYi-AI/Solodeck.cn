"""Layered evaluation for SoloDeck v3 — complements FARS bench, does not replace it.

Layers (from prior architecture analysis):
  L1 FARS / domain validators — causal, statistical, artifact, privacy
  L2 RAGAS-shaped retrieval quality — when KG / memory context is used
  L3 G-Eval-shaped writer quality — action cards and report readability
  L4 Workbench outcomes — scope, handoff, acceptance (lesson 41)

Stdlib only. No RAGAS / DeepEval dependency required.
"""

from __future__ import annotations

import re
from typing import Any


LAYER_FARS = "fars_domain"
LAYER_RAGAS = "ragas_retrieval"
LAYER_GEVAL = "geval_writer"
LAYER_WORKBENCH = "workbench_harness"


def route_layers(task_type: str, result: dict[str, Any]) -> list[str]:
    """Pick which evaluation layers apply to this run."""
    layers = [LAYER_FARS]
    kg = result.get("kg_context") or {}
    if kg.get("nodes") or task_type in {"ideation", "planning", "causal_hypothesis_generation"}:
        layers.append(LAYER_RAGAS)
    if result.get("user_artifact") or result.get("action_cards") or result.get("final_report"):
        layers.append(LAYER_GEVAL)
    if result.get("trace") and len(result.get("trace", [])) >= 4:
        layers.append(LAYER_WORKBENCH)
    return layers


def evaluate_fars_domain(result: dict[str, Any]) -> dict[str, Any]:
    validation = result.get("validation_report", {})
    checks = validation.get("checks", [])
    check_map = {c.get("name"): c for c in checks}
    return {
        "layer": LAYER_FARS,
        "valid": bool(validation.get("valid")),
        "artifact_validity": _check_ok(check_map, "artifact_completeness"),
        "causal_validity": _check_ok(check_map, "causal_validity"),
        "statistical_validity": _check_ok(check_map, "statistical_validity"),
        "privacy_validity": _check_ok(check_map, "privacy"),
        "trace_validity": _check_ok(check_map, "trace"),
        "issues": validation.get("issues", []),
    }


def evaluate_ragas_retrieval(result: dict[str, Any], task: str = "") -> dict[str, Any]:
    """RAGAS-shaped metrics without external NLI — numeric / keyword alignment."""
    artifacts = result.get("artifacts", [])
    report = result.get("user_artifact") or result.get("final_report") or {}
    report_text = _text(report)
    artifact_text = " ".join(_text(a.get("content", {})) for a in artifacts)
    kg = result.get("kg_context") or {}
    kg_labels = [str(n.get("label", "")) for n in kg.get("nodes", []) if n.get("label")]

    faithfulness = _overlap_ratio(_numbers(report_text), _numbers(artifact_text))
    answer_relevancy = _keyword_relevancy(task, report_text)
    context_precision = _overlap_ratio(set(kg_labels[:20]), set(re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z]{3,}", report_text)))
    expected = set(result.get("task_spec", {}).get("expected_artifacts", []))
    produced = {a.get("type") for a in artifacts}
    context_recall = len(expected & produced) / max(len(expected), 1)

    scores = {
        "faithfulness": round(faithfulness, 3),
        "answer_relevancy": round(answer_relevancy, 3),
        "context_precision": round(context_precision, 3),
        "context_recall": round(context_recall, 3),
    }
    return {
        "layer": LAYER_RAGAS,
        "scores": scores,
        "valid": all(v >= 0.4 for v in scores.values()),
        "note": "Heuristic RAGAS proxy; swap with ragas library in CI when needed.",
    }


def evaluate_geval_writer(result: dict[str, Any]) -> dict[str, Any]:
    """G-Eval-shaped rubric for action cards — stdlib heuristics."""
    cards = result.get("action_cards") or (result.get("user_artifact") or {}).get("action_cards") or []
    report = result.get("user_artifact") or result.get("final_report") or {}
    report_text = _text(report)

    actionability = 0.0
    if cards:
        filled = 0
        for card in cards:
            fields = ["where", "what", "when", "success_metric", "title", "action"]
            hits = sum(1 for f in fields if card.get(f))
            filled += hits / len(fields)
        actionability = filled / len(cards)

    clarity = min(1.0, len(report_text.split()) / 120) if report_text else 0.0
    no_overclaim = 0.0 if re.search(r"已证明|必然|guarantee", report_text, re.I) else 1.0
    uncertainty = 1.0 if re.search(r"置信|区间|验证|样本", report_text) else 0.5

    scores = {
        "actionability": round(actionability, 3),
        "clarity": round(clarity, 3),
        "no_overclaim": round(no_overclaim, 3),
        "uncertainty_reported": round(uncertainty, 3),
    }
    total = sum(scores.values()) / len(scores)
    return {
        "layer": LAYER_GEVAL,
        "scores": scores,
        "total": round(total, 3),
        "valid": total >= 0.55,
        "note": "Heuristic G-Eval proxy; use DeepEval in CI for LLM-judge scoring.",
    }


def evaluate_workbench_harness(result: dict[str, Any]) -> dict[str, Any]:
    """Lesson 41 five outcomes adapted for SoloDeck data-agent runs."""
    trace = result.get("trace", [])
    validation = result.get("validation_report", {})
    memory = result.get("memory_updates") or []

    tests_run = any(e.get("step") == "ValidateArtifacts" for e in trace)
    acceptance_met = bool(validation.get("valid"))
    scope_ok = not validation.get("block_output")
    handoff_quality = "full" if result.get("developer_trace") and result.get("trace_id") else "partial"
    reviewer_total = min(10, sum(1 for c in validation.get("checks", []) if c.get("valid")) * 2)

    return {
        "layer": LAYER_WORKBENCH,
        "tests_actually_run": tests_run,
        "acceptance_met": acceptance_met,
        "files_outside_scope": 0,
        "handoff_quality": handoff_quality,
        "reviewer_total": reviewer_total,
        "memory_updated": bool(memory),
        "valid": tests_run and acceptance_met and scope_ok,
    }


def run_layered_eval(result: dict[str, Any], task: str = "", task_type: str = "") -> dict[str, Any]:
    task_type = task_type or (result.get("task_spec") or {}).get("task_type", "descriptive_analysis")
    layers = route_layers(task_type, result)
    evaluators = {
        LAYER_FARS: lambda: evaluate_fars_domain(result),
        LAYER_RAGAS: lambda: evaluate_ragas_retrieval(result, task),
        LAYER_GEVAL: lambda: evaluate_geval_writer(result),
        LAYER_WORKBENCH: lambda: evaluate_workbench_harness(result),
    }
    layer_results = {name: evaluators[name]() for name in layers}
    all_valid = all(r.get("valid") for r in layer_results.values())
    return {
        "layers_applied": layers,
        "all_valid": all_valid,
        "layer_results": layer_results,
        "summary": _summarize(layer_results),
    }


def _summarize(layer_results: dict[str, dict]) -> dict[str, Any]:
    out: dict[str, Any] = {"layer_count": len(layer_results)}
    if LAYER_FARS in layer_results:
        out["domain_valid"] = layer_results[LAYER_FARS].get("valid")
    if LAYER_RAGAS in layer_results:
        out["ragas_avg"] = round(
            sum(layer_results[LAYER_RAGAS]["scores"].values()) / 4, 3
        )
    if LAYER_GEVAL in layer_results:
        out["geval_total"] = layer_results[LAYER_GEVAL].get("total")
    if LAYER_WORKBENCH in layer_results:
        out["workbench_acceptance"] = layer_results[LAYER_WORKBENCH].get("acceptance_met")
    return out


def _check_ok(check_map: dict, name: str) -> int:
    check = check_map.get(name)
    return 1 if check and check.get("valid") else 0


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values())
    return str(value)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"-?\d+\.?\d*", text))


def _overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.5 if not a and not b else 0.0
    return len(a & b) / len(a | b)


def _keyword_relevancy(task: str, report: str) -> float:
    task_tokens = set(re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z]{3,}", (task or "").lower()))
    report_tokens = set(re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z]{3,}", (report or "").lower()))
    if not task_tokens:
        return 0.7
    return len(task_tokens & report_tokens) / len(task_tokens)
