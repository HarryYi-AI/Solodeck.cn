from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .schemas import (
    BusinessRegime,
    CreatorProfile,
    DecisionContext,
    DecisionEpisode,
    DecisionFact,
    DecisionOutcome,
    EpisodeDecision,
    EpisodeEvidence,
    StrategyEvidence,
    StrategySkillCandidate,
    utc_now,
)


class DecisionMemoryStore(ABC):
    @abstractmethod
    def save_episode(self, episode: DecisionEpisode) -> DecisionEpisode: ...

    @abstractmethod
    def list_episodes(self, project_id: str, **filters: Any) -> list[DecisionEpisode]: ...


class SQLiteDecisionMemoryStore(DecisionMemoryStore):
    """SQLite implementation with explicit columns that map cleanly to PostgreSQL."""

    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.path = Path(path or root / "data" / "solodeck_decision_memory.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS decision_episodes (
                  episode_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                  user_id TEXT NOT NULL, project_id TEXT NOT NULL, trace_id TEXT,
                  platform TEXT, topic TEXT, account_stage TEXT, content_format TEXT,
                  time_window TEXT, context_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                  decision_json TEXT NOT NULL, outcome_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_episode_project_time ON decision_episodes(project_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_episode_context ON decision_episodes(project_id, platform, topic, content_format);

                CREATE TABLE IF NOT EXISTS decision_facts (
                  fact_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                  source_episode_id TEXT NOT NULL, fact_key TEXT NOT NULL,
                  fact_value_json TEXT NOT NULL, confidence REAL NOT NULL,
                  valid_from TEXT NOT NULL, valid_to TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_fact_project_key ON decision_facts(project_id, fact_key, valid_from DESC);

                CREATE TABLE IF NOT EXISTS business_regimes (
                  regime_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                  platform TEXT, topic TEXT, content_format TEXT, scope_json TEXT NOT NULL,
                  description TEXT NOT NULL, valid_from TEXT NOT NULL, valid_to TEXT,
                  evidence_episode_ids_json TEXT NOT NULL, confidence REAL NOT NULL,
                  status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_regime_active ON business_regimes(project_id, status, valid_from DESC);
                CREATE INDEX IF NOT EXISTS idx_regime_scope ON business_regimes(project_id, platform, topic, content_format);

                CREATE TABLE IF NOT EXISTS creator_profiles (
                  project_id TEXT PRIMARY KEY, profile_json TEXT NOT NULL,
                  version INTEGER NOT NULL, updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS strategy_evidence (
                  evidence_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                  source_episode_id TEXT NOT NULL, strategy TEXT NOT NULL,
                  platform TEXT, topic TEXT, content_format TEXT,
                  context_json TEXT NOT NULL, metric_before_json TEXT NOT NULL,
                  metric_after_json TEXT NOT NULL, success INTEGER,
                  confidence REAL NOT NULL, evidence_level TEXT NOT NULL,
                  causal_methods_json TEXT NOT NULL, confounder_checked INTEGER NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_strategy_scope ON strategy_evidence(project_id, strategy, platform, topic, content_format);
                CREATE INDEX IF NOT EXISTS idx_strategy_created ON strategy_evidence(project_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS strategy_skill_candidates (
                  candidate_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                  name TEXT NOT NULL, applicability_json TEXT NOT NULL,
                  procedure_json TEXT NOT NULL, evidence_episode_ids_json TEXT NOT NULL,
                  success_count INTEGER NOT NULL, failure_count INTEGER NOT NULL,
                  evidence_level TEXT NOT NULL, confidence REAL NOT NULL,
                  status TEXT NOT NULL, verifier_passed INTEGER NOT NULL,
                  human_approved INTEGER NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_candidate_status ON strategy_skill_candidates(project_id, status, created_at DESC);
                """
            )

    def save_episode(self, episode: DecisionEpisode) -> DecisionEpisode:
        context = episode.decision_context
        with self._connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO decision_episodes VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode.episode_id, episode.timestamp, episode.user_id, episode.project_id,
                    episode.trace_id, context.platform, context.topic, context.account_stage,
                    context.content_format, context.time_window, _json(context.to_dict()),
                    _json(episode.evidence.to_dict()), _json(episode.decision.to_dict()),
                    _json(episode.outcome.to_dict()),
                ),
            )
        return episode

    def get_episode(self, episode_id: str) -> DecisionEpisode | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM decision_episodes WHERE episode_id = ?", (episode_id,)).fetchone()
        return _episode(row) if row else None

    def list_episodes(self, project_id: str, **filters: Any) -> list[DecisionEpisode]:
        allowed = {"platform", "topic", "content_format", "user_id"}
        clauses, values = ["project_id = ?"], [project_id]
        for key, value in filters.items():
            if key in allowed and value:
                clauses.append(f"{key} = ?")
                values.append(value)
        limit = max(1, min(int(filters.get("limit", 100)), 500))
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM decision_episodes WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        return [_episode(row) for row in rows]

    def update_outcome(self, episode_id: str, outcome: DecisionOutcome) -> DecisionEpisode | None:
        with self._connect() as db:
            db.execute("UPDATE decision_episodes SET outcome_json = ? WHERE episode_id = ?", (_json(outcome.to_dict()), episode_id))
        return self.get_episode(episode_id)

    def save_facts(self, facts: list[DecisionFact]) -> list[DecisionFact]:
        with self._connect() as db:
            db.executemany(
                "INSERT OR REPLACE INTO decision_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(
                    fact.fact_id, fact.project_id, fact.source_episode_id, fact.fact_key,
                    _json(fact.fact_value), fact.confidence, fact.valid_from, fact.valid_to,
                ) for fact in facts],
            )
        return facts

    def list_facts(self, project_id: str, fact_key: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        sql = "SELECT * FROM decision_facts WHERE project_id = ?"
        values: list[Any] = [project_id]
        if fact_key:
            sql += " AND fact_key = ?"
            values.append(fact_key)
        sql += " ORDER BY valid_from DESC LIMIT ?"
        values.append(max(1, min(limit, 500)))
        with self._connect() as db:
            rows = db.execute(sql, values).fetchall()
        return [{**dict(row), "fact_value": json.loads(row["fact_value_json"])} for row in rows]

    def save_regime(self, regime: BusinessRegime) -> BusinessRegime:
        scope = regime.scope
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO business_regimes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    regime.regime_id, regime.project_id, scope.get("platform", ""), scope.get("topic", ""),
                    scope.get("content_format", ""), _json(scope), regime.description, regime.valid_from,
                    regime.valid_to, _json(regime.evidence_episode_ids), regime.confidence, regime.status,
                ),
            )
        return regime

    def list_regimes(self, project_id: str, status: str | None = None, limit: int = 100) -> list[BusinessRegime]:
        sql, values = "SELECT * FROM business_regimes WHERE project_id = ?", [project_id]
        if status:
            sql += " AND status = ?"
            values.append(status)
        sql += " ORDER BY valid_from DESC LIMIT ?"
        values.append(max(1, min(limit, 300)))
        with self._connect() as db:
            rows = db.execute(sql, values).fetchall()
        return [_regime(row) for row in rows]

    def close_active_regimes(self, project_id: str, scope: dict[str, str], valid_to: str) -> list[str]:
        clauses, values = ["project_id = ?", "status = 'active'"], [project_id]
        for key in ("platform", "topic", "content_format"):
            clauses.append(f"{key} = ?")
            values.append(scope.get(key, ""))
        with self._connect() as db:
            rows = db.execute(f"SELECT regime_id FROM business_regimes WHERE {' AND '.join(clauses)}", values).fetchall()
            db.execute(
                f"UPDATE business_regimes SET status = 'historical', valid_to = ? WHERE {' AND '.join(clauses)}",
                (valid_to, *values),
            )
        return [row["regime_id"] for row in rows]

    def save_profile(self, profile: CreatorProfile) -> CreatorProfile:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO creator_profiles VALUES (?, ?, ?, ?)",
                (profile.project_id, _json(profile.to_dict()), profile.version, profile.updated_at),
            )
        return profile

    def get_profile(self, project_id: str) -> CreatorProfile | None:
        with self._connect() as db:
            row = db.execute("SELECT profile_json FROM creator_profiles WHERE project_id = ?", (project_id,)).fetchone()
        return CreatorProfile(**json.loads(row["profile_json"])) if row else None

    def save_strategy_evidence(self, evidence: StrategyEvidence) -> StrategyEvidence:
        context = evidence.context
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO strategy_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evidence.evidence_id, evidence.project_id, evidence.source_episode_id, evidence.strategy,
                    context.get("platform", ""), context.get("topic", ""), context.get("content_format", ""),
                    _json(context), _json(evidence.metric_before), _json(evidence.metric_after),
                    None if evidence.success is None else int(evidence.success), evidence.confidence,
                    evidence.evidence_level, _json(evidence.causal_methods), int(evidence.confounder_checked),
                    evidence.created_at,
                ),
            )
        return evidence

    def list_strategy_evidence(self, project_id: str, **filters: Any) -> list[StrategyEvidence]:
        clauses, values = ["project_id = ?"], [project_id]
        for key in ("strategy", "platform", "topic", "content_format"):
            if filters.get(key):
                clauses.append(f"{key} = ?")
                values.append(filters[key])
        limit = max(1, min(int(filters.get("limit", 200)), 500))
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM strategy_evidence WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        return [_strategy_evidence(row) for row in rows]

    def save_candidate(self, candidate: StrategySkillCandidate) -> StrategySkillCandidate:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO strategy_skill_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    candidate.candidate_id, candidate.project_id, candidate.name, _json(candidate.applicability),
                    _json(candidate.procedure), _json(candidate.evidence_episode_ids), candidate.success_count,
                    candidate.failure_count, candidate.evidence_level, candidate.confidence, candidate.status,
                    int(candidate.verifier_passed), int(candidate.human_approved), candidate.created_at,
                ),
            )
        return candidate

    def list_candidates(self, project_id: str, status: str | None = None) -> list[StrategySkillCandidate]:
        sql, values = "SELECT * FROM strategy_skill_candidates WHERE project_id = ?", [project_id]
        if status:
            sql += " AND status = ?"
            values.append(status)
        sql += " ORDER BY created_at DESC"
        with self._connect() as db:
            rows = db.execute(sql, values).fetchall()
        return [_candidate(row) for row in rows]


def _episode(row: sqlite3.Row) -> DecisionEpisode:
    return DecisionEpisode(
        episode_id=row["episode_id"], timestamp=row["timestamp"], user_id=row["user_id"],
        project_id=row["project_id"], trace_id=row["trace_id"] or "",
        decision_context=DecisionContext(**json.loads(row["context_json"])),
        evidence=EpisodeEvidence(**json.loads(row["evidence_json"])),
        decision=EpisodeDecision(**json.loads(row["decision_json"])),
        outcome=DecisionOutcome(**json.loads(row["outcome_json"])),
    )


def _regime(row: sqlite3.Row) -> BusinessRegime:
    return BusinessRegime(
        regime_id=row["regime_id"], project_id=row["project_id"], scope=json.loads(row["scope_json"]),
        description=row["description"], valid_from=row["valid_from"], valid_to=row["valid_to"],
        evidence_episode_ids=json.loads(row["evidence_episode_ids_json"]), confidence=row["confidence"],
        status=row["status"],
    )


def _strategy_evidence(row: sqlite3.Row) -> StrategyEvidence:
    return StrategyEvidence(
        evidence_id=row["evidence_id"], project_id=row["project_id"], source_episode_id=row["source_episode_id"],
        strategy=row["strategy"], context=json.loads(row["context_json"]),
        metric_before=json.loads(row["metric_before_json"]), metric_after=json.loads(row["metric_after_json"]),
        success=None if row["success"] is None else bool(row["success"]), confidence=row["confidence"],
        evidence_level=row["evidence_level"], causal_methods=json.loads(row["causal_methods_json"]),
        confounder_checked=bool(row["confounder_checked"]), created_at=row["created_at"],
    )


def _candidate(row: sqlite3.Row) -> StrategySkillCandidate:
    return StrategySkillCandidate(
        candidate_id=row["candidate_id"], project_id=row["project_id"], name=row["name"],
        applicability=json.loads(row["applicability_json"]), procedure=json.loads(row["procedure_json"]),
        evidence_episode_ids=json.loads(row["evidence_episode_ids_json"]), success_count=row["success_count"],
        failure_count=row["failure_count"], evidence_level=row["evidence_level"], confidence=row["confidence"],
        status=row["status"], verifier_passed=bool(row["verifier_passed"]),
        human_approved=bool(row["human_approved"]), created_at=row["created_at"],
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
