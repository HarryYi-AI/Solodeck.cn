from __future__ import annotations


def validate_trace(trace: list[dict]) -> dict:
    steps = [event.get("step") for event in trace]
    required_v3 = ["CompileTask", "LoadMemory", "BuildOrRetrieveKG", "GenerateHypothesisTree", "RouteTools", "PlanWorkflow", "ExecuteSkills", "ValidateArtifacts"]
    required_v4 = ["LoadSession", "RiskRoute", "PostWriterValidate"]
    if all(step in steps for step in required_v3):
        return {"name": "trace", "valid": True, "issues": []}
    if all(step in steps for step in required_v4) and "ToolCall" in steps:
        return {"name": "trace", "valid": True, "issues": []}
    missing = [step for step in required_v3 if step not in steps]
    return {"name": "trace", "valid": False, "issues": [f"缺少步骤：{step}" for step in missing]}
