from __future__ import annotations


def validate_trace(trace: list[dict]) -> dict:
    required = ["CompileTask", "LoadMemory", "BuildOrRetrieveKG", "GenerateHypothesisTree", "RouteTools", "PlanWorkflow", "ExecuteSkills", "ValidateArtifacts"]
    steps = [event.get("step") for event in trace]
    missing = [step for step in required if step not in steps]
    return {"name": "trace", "valid": not missing, "issues": [f"缺少步骤：{step}" for step in missing]}
