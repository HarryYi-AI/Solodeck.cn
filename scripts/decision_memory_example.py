from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solodeck_v4.decision_memory.evidence import causal_wording_allowed
from solodeck_v4.decision_memory.memory_service import DecisionMemoryService
from solodeck_v4.decision_memory.schemas import (
    DecisionContext,
    DecisionEpisode,
    DecisionOutcome,
    EpisodeDecision,
    EpisodeEvidence,
)
from solodeck_v4.decision_memory.store import SQLiteDecisionMemoryStore


ROWS = [
    ("question-title", 0.081, 0.053, True),
    ("question-title", 0.094, 0.062, True),
    ("statement-title", 0.060, 0.041, False),
    ("question-title", 0.091, 0.060, True),
    ("question-title", 0.088, 0.059, True),
]


def run_demo(database: str | Path | None = None) -> dict:
    path = Path(database) if database else Path(tempfile.mkdtemp()) / "decision-memory.db"
    service = DecisionMemoryService(SQLiteDecisionMemoryStore(path))
    for index, (strategy, ctr, save_rate, success) in enumerate(ROWS, start=1):
        episode = DecisionEpisode(
            episode_id=f"demo_episode_{index}", user_id="demo_user", project_id="xhs_agent_demo",
            decision_context=DecisionContext(platform="xiaohongshu", topic="Agent", content_format="technical_post"),
            evidence=EpisodeEvidence(
                metrics={"ctr": ctr, "save_rate": save_rate}, sample_size=1,
                evidence_level="observational", verifier_passed=True,
            ),
            decision=EpisodeDecision(strategy=strategy, reason="历史表现记录", confidence=0.6),
            outcome=DecisionOutcome(observed=True, metrics={"ctr": ctr, "save_rate": save_rate}, success=success),
        )
        service.record_decision(episode)
    consolidation = service.run_consolidation("xhs_agent_demo", persist=True)
    context = service.get_decision_context(
        "为什么我最近 Agent 技术内容的收藏率下降？",
        project_id="xhs_agent_demo",
        task_spec={"filters": {"topic": "Agent"}},
    )
    candidates = consolidation["strategy_skill_candidates"]
    return {
        "database": str(path),
        "episode_count": consolidation["episode_count"],
        "profile_candidate": consolidation["profile_updates"],
        "strategy_candidates": candidates,
        "memory_query_plan": context["query_plan"],
        "live_data_requirements": context["query_plan"]["live_data_requirements"],
        "causal_safety": {
            "evidence_level": "observational",
            "can_claim_causality": causal_wording_allowed("observational", False),
            "note": "历史观察可生成待验证策略候选，但不能自动声称因果。",
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
