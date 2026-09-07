from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from solo_creator_agent import api_spa
from solo_creator_agent.src import auth
import solodeck_v4.decision_memory as decision_memory_package
from solodeck_v4.decision_memory.evidence import causal_wording_allowed, can_promote_to_skill
from solodeck_v4.decision_memory.memory_service import DecisionMemoryService
from solodeck_v4.decision_memory.query_planner import plan_memory_query
from solodeck_v4.decision_memory.schemas import (
    BusinessRegime,
    DecisionContext,
    DecisionEpisode,
    DecisionOutcome,
    EpisodeDecision,
    EpisodeEvidence,
    StrategyEvidence,
)
from solodeck_v4.decision_memory.store import SQLiteDecisionMemoryStore


def _service(tmp_path):
    return DecisionMemoryService(SQLiteDecisionMemoryStore(tmp_path / "decision.db"))


def _episode(index, *, strategy="question-title", platform="xiaohongshu", success=True, level="observational"):
    return DecisionEpisode(
        episode_id=f"episode_{index}", user_id="user_1", project_id="project_1",
        decision_context=DecisionContext(platform=platform, topic="Agent", content_format="technical_post"),
        evidence=EpisodeEvidence(
            metrics={"ctr": 0.08 + index / 1000, "save_rate": 0.05 + index / 1000},
            sample_size=20, evidence_level=level, verifier_passed=True,
        ),
        decision=EpisodeDecision(strategy=strategy, reason="structured result", confidence=0.65),
        outcome=DecisionOutcome(observed=True, metrics={"save_rate": 0.06}, success=success),
    )


def test_single_episode_does_not_update_long_term_profile(tmp_path):
    service = _service(tmp_path)
    service.record_decision(_episode(1))
    result = service.run_consolidation("project_1")
    assert result["profile_updates"] == {}
    assert result["strategy_skill_candidates"] == []


def test_repeated_evidence_creates_profile_and_candidate(tmp_path):
    service = _service(tmp_path)
    for index in range(1, 4):
        service.record_decision(_episode(index))
    result = service.run_consolidation("project_1")
    assert result["profile_updates"]["evidence_count"]["episodes"] == 3
    assert result["profile_updates"]["effective_topics"] == ["Agent"]
    assert result["strategy_skill_candidates"][0]["status"] == "candidate"
    service.run_consolidation("project_1")
    assert len(service.store.list_candidates("project_1")) == 1


def test_new_regime_historizes_old_regime(tmp_path):
    service = _service(tmp_path)
    old = BusinessRegime(
        project_id="project_1", scope={"platform": "xiaohongshu", "topic": "Agent"},
        description="长教程表现更好", valid_from="2026-05-01T00:00:00+00:00",
        evidence_episode_ids=["old"], confidence=0.7,
    )
    new = BusinessRegime(
        project_id="project_1", scope={"platform": "xiaohongshu", "topic": "Agent"},
        description="短图文表现更好", valid_from="2026-08-01T00:00:00+00:00",
        evidence_episode_ids=["new"], confidence=0.8,
    )
    service.activate_business_regime(old)
    result = service.activate_business_regime(new)
    regimes = service.store.list_regimes("project_1")
    assert result["historized_regime_ids"] == [old.regime_id]
    assert next(item for item in regimes if item.regime_id == old.regime_id).status == "historical"
    assert next(item for item in regimes if item.regime_id == new.regime_id).status == "active"


def test_observational_candidate_cannot_claim_causality_or_become_skill(tmp_path):
    service = _service(tmp_path)
    for index in range(1, 4):
        service.record_decision(_episode(index, level="observational"))
    candidate = service.run_consolidation("project_1")["strategy_skill_candidates"][0]
    assert candidate["evidence_level"] == "observational"
    assert causal_wording_allowed("observational", False) is False
    assert can_promote_to_skill("observational", verifier_passed=True, human_approved=True, evidence_count=3) is False


def test_current_metric_query_requires_live_data():
    plan = plan_memory_query("为什么最近小红书收藏率下降？")
    assert plan.requires_live_data is True
    assert "recent save_rate" in plan.live_data_requirements
    assert "topic mix" in plan.live_data_requirements


def test_platform_evidence_is_not_transferred_without_match(tmp_path):
    service = _service(tmp_path)
    service.record_decision(_episode(1, platform="xiaohongshu"))
    service.record_decision(_episode(2, platform="douyin"))
    context = service.get_decision_context("小红书过去用过什么策略？", project_id="project_1")
    assert context["similar_episodes"]
    assert {item["decision_context"]["platform"] for item in context["similar_episodes"]} == {"xiaohongshu"}


def test_insufficient_evidence_is_explicit(tmp_path):
    service = _service(tmp_path)
    service.record_decision(_episode(1))
    service.record_decision(_episode(2))
    result = service.run_consolidation("project_1")
    assert result["insufficient_evidence"][0]["reason"].startswith("证据不足")


def test_historical_failure_is_retrieved_for_risk_context(tmp_path):
    service = _service(tmp_path)
    service.record_decision(_episode(1, success=False))
    context = service.get_decision_context("为什么小红书 Agent 内容下降，下一步怎么做？", project_id="project_1")
    assert context["historical_failures"]
    assert context["historical_failures"][0]["outcome"]["success"] is False


def test_consolidation_flags_temporal_strategy_drift(tmp_path):
    service = _service(tmp_path)
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    strategies = ["long-form"] * 3 + ["short-visual"] * 3
    for index, strategy in enumerate(strategies):
        service.store.save_strategy_evidence(StrategyEvidence(
            project_id="project_1", source_episode_id=f"drift_{index}", strategy=strategy,
            context={"platform": "xiaohongshu", "topic": "Agent", "content_format": "post"},
            success=True, confidence=0.6, evidence_level="observational",
            created_at=(start + timedelta(days=index * 20)).isoformat(),
        ))
    result = service.run_consolidation("project_1")
    assert result["temporal_drift"][0]["historical_strategy"] == "long-form"
    assert result["temporal_drift"][0]["recent_strategy"] == "short-visual"


def test_decision_memory_api_is_scoped_to_authenticated_workspace(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth, "SOLODECK_AUTH_DB_PATH", auth_path)
    monkeypatch.setitem(api_spa.register_user.__globals__, "SOLODECK_AUTH_DB_PATH", auth_path)
    service = _service(tmp_path)
    monkeypatch.setattr(decision_memory_package, "DecisionMemoryService", lambda: service)

    owner = TestClient(api_spa.app)
    registration = owner.post("/api/auth/register", json={
        "email": "owner@example.com", "password": "secret12", "display_name": "Owner",
    }).json()
    episode = _episode(1)
    episode.project_id = registration["workspace_id"]
    service.record_decision(episode)

    context = owner.get("/api/v4/decision-memory/context", params={
        "workspace_id": "workspace_attacker", "query": "小红书过去用过什么策略？",
    })
    assert context.status_code == 200
    assert context.json()["similar_episodes"][0]["episode_id"] == episode.episode_id

    outsider = TestClient(api_spa.app)
    outsider.post("/api/auth/register", json={
        "email": "other@example.com", "password": "secret12", "display_name": "Other",
    })
    denied = outsider.post("/api/v4/decision-memory/outcomes", json={
        "episode_id": episode.episode_id, "metrics": {"save_rate": 0.08}, "success": True,
    })
    assert denied.status_code == 404
    accepted = owner.post("/api/v4/decision-memory/outcomes", json={
        "episode_id": episode.episode_id, "metrics": {"save_rate": 0.08}, "success": True,
    })
    assert accepted.status_code == 200
    assert accepted.json()["recorded"] is True
