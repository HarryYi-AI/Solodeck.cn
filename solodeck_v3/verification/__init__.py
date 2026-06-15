from .artifact_validator import validate_artifact_completeness
from .causal_validator import validate_causal_claims
from .privacy_validator import validate_privacy
from .reward_validator import validate_rewards
from .statistical_validator import validate_statistics
from .trace_validator import validate_trace
from .output_format_validator import validate_output_format


def validate_all(state: dict) -> dict:
    checks = [
        validate_artifact_completeness(state.get("artifacts", []), state.get("final_report")),
        validate_statistics(state.get("artifacts", []), state.get("critique", {})),
        validate_causal_claims(state.get("artifacts", []), state.get("final_report"), state.get("critique", {})),
        validate_privacy(state.get("user_artifact", state.get("final_report", {}))),
        validate_trace(state.get("trace", [])),
        validate_output_format(state.get("user_artifact") or state.get("final_report", {}), state.get("developer_trace", {})),
    ]
    issues = [issue for check in checks for issue in check.get("issues", [])]
    block_output = any(check.get("block_output") for check in checks)
    return {"valid": not issues and not block_output, "checks": checks, "issues": issues, "block_output": block_output}
