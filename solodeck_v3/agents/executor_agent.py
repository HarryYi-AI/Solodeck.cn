from __future__ import annotations


class ExecutorAgent:
    name = "ExecutorAgent"

    def summarize_execution(self, selected_skills: list[str], artifacts: list[dict]) -> dict:
        return {
            "skills_executed": len(selected_skills),
            "artifact_count": len(artifacts),
            "last_artifacts": [a.get("id") for a in artifacts[-5:]],
        }

