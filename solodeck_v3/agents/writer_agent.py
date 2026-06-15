from __future__ import annotations


class WriterAgent:
    name = "WriterAgent"

    def polish_user_artifact(self, user_artifact: dict) -> dict:
        artifact = dict(user_artifact or {})
        artifact.setdefault("title", "可验证经营建议")
        artifact.setdefault("limitations", "当前建议基于已上传数据，证据不足时会自动降级为验证计划。")
        return artifact

