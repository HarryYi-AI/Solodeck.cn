from __future__ import annotations

from typing import Any

from solodeck_v4.retrieval.artifact_retriever import retrieve_artifacts, retrieve_session_turns
from solodeck_v4.retrieval.evidence_packer import pack_evidence
from solodeck_v4.retrieval.kg_retriever import retrieve_kg
from solodeck_v4.retrieval.memory_store import MemoryStore
from solodeck_v4.retrieval.schema_retriever import retrieve_schema
from solodeck_v4.retrieval.text_retriever import retrieve_text

INTENTS = {
    "schema_question",
    "metric_question",
    "relationship_question",
    "causal_question",
    "previous_result_question",
    "text_feedback_question",
    "planning_question",
    "report_question",
}

INTENT_MARKERS = {
    "schema_question": ("字段", "列", "schema", "映射", "有没有", "哪些数据", "数据结构"),
    "metric_question": ("多少", "数值", "指标", "咨询", "成交", "收入", "转化", "播放", "收藏"),
    "relationship_question": ("关系", "关联", "相关", "连接", "邻居", "图谱"),
    "causal_question": ("因果", "影响", "提升", "是不是", "是否", "相比", "更能", "导致", "confound"),
    "previous_result_question": ("上次", "之前", "继续", "刚才", "那个结果", "上一轮"),
    "text_feedback_question": ("评论", "反馈", "用户说", "私信", "留言", "吐槽", "文本", "怎么说", "怎么说的"),
    "planning_question": ("计划", "下一步", "怎么做", "行动", "安排", "本周", "下周"),
    "report_question": ("报告", "周报", "总结", "复盘", "导出"),
}


def classify_intent(query: str, task_spec: dict[str, Any]) -> str:
    q = query or ""
    scores = {intent: 0.0 for intent in INTENTS}

    for intent, markers in INTENT_MARKERS.items():
        for marker in markers:
            if marker in q:
                scores[intent] += 1.0

    task_type = task_spec.get("task_type") or ""
    if task_type in {"causal_effect_estimation", "counterfactual_analysis"}:
        scores["causal_question"] += 2.0
    if task_type in {"schema_mapping", "data_quality"}:
        scores["schema_question"] += 1.5
    if any(m in q for m in ("上次", "之前", "继续")):
        scores["previous_result_question"] += 1.5

    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        if task_type:
            return "metric_question"
        return "schema_question"
    return best


def route_sources(intent: str) -> list[str]:
    routes = {
        "schema_question": ["schema"],
        "metric_question": ["artifact", "schema"],
        "relationship_question": ["kg"],
        "causal_question": ["kg", "artifact"],
        "previous_result_question": ["artifact", "session"],
        "text_feedback_question": ["text"],
        "planning_question": ["failure", "skill", "artifact"],
        "report_question": ["artifact", "evaluation"],
    }
    return routes.get(intent, ["schema", "artifact"])


def retrieve_memory(
    query: str,
    task_spec: dict[str, Any] | None = None,
    *,
    entity_link: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
    artifact_cache: dict[str, Any] | None = None,
    store: MemoryStore | None = None,
) -> dict[str, Any]:
    task_spec = task_spec or {}
    store = store or MemoryStore()
    intent = classify_intent(query, task_spec)
    sources = route_sources(intent)

    evidence: list[dict[str, Any]] = []
    missing_info: list[str] = []
    warnings: list[str] = []

    if "schema" in sources:
        evidence.extend(retrieve_schema(query, task_spec, store))

    if "kg" in sources:
        kg_hits = retrieve_kg(query, task_spec, entity_link, store)
        evidence.extend(kg_hits)
        if not kg_hits:
            missing_info.append("未找到匹配的知识图谱边")

    if "artifact" in sources:
        artifacts = retrieve_artifacts(query, task_spec, artifact_cache, store)
        evidence.extend(artifacts)
        if intent == "causal_question":
            causal_types = {h.get("meta", {}).get("artifact_type") for h in artifacts}
            if "causal_readiness" not in causal_types:
                missing_info.append("缺少 causal_readiness 工件，需运行因果就绪检查")
        if intent == "metric_question" and not artifacts:
            missing_info.append("缺少可复用的指标 artifact，可能需要 Python 重算")

    if "session" in sources:
        session_history = _session_turns(session, store)
        evidence.extend(retrieve_session_turns(query, session_history))

    if "text" in sources:
        text_hits = retrieve_text(query, store)
        evidence.extend(text_hits)
        if not text_hits:
            missing_info.append("未找到匹配的文本反馈片段")

    if "failure" in sources or "skill" in sources or "evaluation" in sources:
        evidence.extend(_retrieve_unified_memory(query, sources, session))

    if intent == "causal_question" and _only_text_evidence(evidence):
        warnings.append("因果问题仅命中文本证据，强制 causal_readiness_check")

    plan = f"{intent} -> {' + '.join(sources)}"
    return pack_evidence(query, plan, evidence, missing_info, warnings)


def _retrieve_unified_memory(query: str, sources: list[str], session: dict[str, Any] | None) -> list[dict[str, Any]]:
    from solodeck_v4.memory import UnifiedMemory

    project_id = (session or {}).get("project_id", "solodeck")
    session_id = (session or {}).get("session_id")
    hits: list[dict[str, Any]] = []
    for memory_type in [source for source in sources if source in {"failure", "skill", "evaluation"}]:
        for item in UnifiedMemory().retrieve_memory(query=query, project_id=project_id, session_id=session_id, memory_type=memory_type, limit=8):
            hits.append({
                "source_type": "validator" if memory_type == "evaluation" else "artifact",
                "source_id": item.memory_id, "content": item.content_summary,
                "structured_payload": item.structured_payload, "score": item.quality_score,
                "used_for": "planning" if memory_type in {"failure", "skill"} else "validation",
                "warnings": item.warnings, "privacy_level": item.privacy_level,
            })
    return hits


def _session_turns(session: dict[str, Any] | None, store: MemoryStore) -> list[dict[str, Any]]:
    if session and session.get("turns"):
        return session["turns"]
    history = store.session_history()
    if isinstance(history, list) and history:
        latest = history[-1]
        return latest.get("turns") or history
    return []


def _only_text_evidence(evidence: list[dict[str, Any]]) -> bool:
    if not evidence:
        return False
    types = {item.get("source_type") for item in evidence}
    return types <= {"text", "session"}
