from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from solodeck_v4.bench import evaluate_scm_run, generate_scm_task
from solodeck_v4.evolution import SkillOptLite
from solodeck_v4.governance import govern_claims, run_governance_suite
from solodeck_v4.memory import MemoryItem, SQLiteMemoryBackend, UnifiedMemory
from solodeck_v4.runtime.checkpoint import CheckpointStore
from solodeck_v4.compiler.enhanced_compiler import compile_with_session
from solodeck_v4.tools.registry import call_tool


class UnifiedMemoryTests(unittest.TestCase):
    def test_crud_compact_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = UnifiedMemory(SQLiteMemoryBackend(Path(tmp) / "memory.db"))
            item = memory.write_memory(MemoryItem(
                memory_type="artifact", project_id="p1", session_id="s1", task_id="t1",
                source_type="python", source_id="a1", content_summary="收入指标重算",
                structured_payload={"revenue": 120.0}, quality_score=0.9,
            ))
            self.assertEqual(memory.read_memory(item.memory_id).structured_payload["revenue"], 120.0)
            updated = memory.update_memory(item.memory_id, {"content_summary": "收入指标已复核"})
            self.assertEqual(updated.version, 2)
            self.assertEqual(len(memory.retrieve_memory(query="收入", project_id="p1")), 1)
            self.assertEqual(len(memory.export_memory_trace("p1", "s1")), 1)
            self.assertTrue(memory.delete_memory(item.memory_id))


class GovernanceTests(unittest.TestCase):
    def _state(self) -> dict:
        return {
            "task_spec": {"task_type": "causal_effect_estimation", "candidate_treatments": ["strategy"], "candidate_outcomes": ["revenue"], "unit": "content", "time": "7d"},
            "schema_summary": {"columns": ["strategy", "revenue", "content_id", "date"]},
            "artifacts": [
                {"id": "causal_readiness", "type": "causal_readiness", "source_type": "python", "generated_by": "CausalReadinessSkill", "content": {"score": 85, "causal_claim_allowed": True}},
                {"id": "bootstrap_ci", "type": "bootstrap_result", "source_type": "python", "generated_by": "BootstrapSkill", "content": {"ate": 1.2, "ci_95": [-0.3, 2.4]}},
            ],
            "trace": [{"step": "CompileTask"}, {"step": "ExecuteSkills"}, {"step": "ValidateArtifacts"}],
            "action_cards": [{"title": "先验证当前策略"}],
        }

    def test_ci_crossing_zero_blocks_strong_claim(self) -> None:
        state = self._state()
        report = govern_claims(state, "数据证明了策略显著提升收入 1.2。")
        self.assertNotIn("证明了", report["answer"])
        self.assertTrue(any("置信区间穿过 0" in warning for warning in report["warnings"]))

    def test_numeric_claim_requires_python_artifact(self) -> None:
        state = self._state()
        state["artifacts"] = [{"id": "report", "generated_by": "ReportSkill", "source_type": "python", "content": {}}]
        state["draft_answer"] = "收入提升 20%。"
        report = run_governance_suite(state)
        self.assertIn("数值声明缺少 Python/SQL 计算工件", report["issues"])

    def test_privacy_gate_replaces_output(self) -> None:
        state = self._state()
        report = govern_claims(state, "请联系 13800138000 获取结果。")
        self.assertTrue(report["block_output"])
        self.assertNotIn("13800138000", report["answer"])

    def test_decimal_is_not_misclassified_as_phone(self) -> None:
        state = self._state()
        state["user_artifact"] = {"estimated_impact": -12.252144923627279}
        report = run_governance_suite(state)
        privacy = next(check for check in report["checks"] if check["name"] == "privacy")
        self.assertTrue(privacy["valid"])


class CompilerTests(unittest.TestCase):
    def test_compared_title_styles_rank_before_platform_context(self) -> None:
        import pandas as pd

        df = pd.DataFrame({
            "content_id": ["1", "2"], "platform": ["xiaohongshu"] * 2,
            "title_style": ["pain_point", "tutorial"], "consultations": [3, 2],
            "publish_time": ["2026-01-01", "2026-01-02"],
        })
        spec = compile_with_session("小红书痛点标题是否比教程标题更能带来咨询？", df)
        self.assertEqual(spec.candidate_treatments[0], "title_style")


class ToolValidationTests(unittest.TestCase):
    def test_unstable_interval_is_downgraded_before_validation(self) -> None:
        state = {
            "artifacts": [{"id": "bootstrap_ci", "content": {"ci_95": [-1.0, 2.0]}}],
            "trace": [
                {"step": "LoadSession"}, {"step": "RiskRoute"},
                {"step": "ExecuteSkills"}, {"step": "ToolCall"},
            ],
            "final_report": {}, "user_artifact": {},
        }
        result = call_tool("validate_artifacts", state, {})
        self.assertTrue(state["critique"]["downgraded_to_validation"])
        self.assertNotIn("区间不稳定但没有降级为验证建议", state["validation_report"]["issues"])


class BenchmarkAndEvolutionTests(unittest.TestCase):
    def test_scm_metrics(self) -> None:
        task = generate_scm_task(sample_size=100, effect_size=2.0)
        result = {"treatment": "strategy", "outcome": "revenue", "confounders": ["account_size", "topic_quality"], "dag": task.dag, "ate": 2.1, "evidence_level": 4}
        metrics = evaluate_scm_run(task, result)
        self.assertAlmostEqual(metrics["ate_absolute_error"], 0.1)
        self.assertEqual(metrics["confounder_recall"], 1.0)

    def test_skill_patch_requires_held_out_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = UnifiedMemory(SQLiteMemoryBackend(Path(tmp) / "memory.db"))
            opt = SkillOptLite(memory)
            patch = opt.propose([{"failure_type": "causal_overclaim", "failure_id": "f1"}])[0]
            accepted = opt.validate_patch(patch, [{"id": "h1"}], lambda tasks, candidate: 0.8 if candidate else 0.6)
            self.assertEqual(accepted["status"], "accepted")


class CheckpointTests(unittest.TestCase):
    def test_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(tmp)
            store.save("trace1", "input", {"trace_id": "trace1", "value": 1})
            store.save("trace1", "done", {"trace_id": "trace1", "value": 2})
            self.assertEqual(store.replay("trace1")["value"], 2)


if __name__ == "__main__":
    unittest.main()
