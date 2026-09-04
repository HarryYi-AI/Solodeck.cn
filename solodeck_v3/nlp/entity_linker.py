"""Minimal business entity linking — optional NLP helper, not wired into default graph."""

from __future__ import annotations

import re
from typing import Any

PLATFORM_ALIASES = {
    "小红书": "xiaohongshu",
    "xhs": "xiaohongshu",
    "抖音": "douyin",
    "b站": "bilibili",
    "bilibili": "bilibili",
    "youtube": "youtube",
    "tiktok": "tiktok",
    "公众号": "wechat",
    "wechat": "wechat",
}

OUTCOME_ALIASES = {
    "转化率": "conversion_rate",
    "成交率": "conversion_rate",
    "咨询率": "consultation_rate",
    "收藏率": "favorite_rate",
    "转粉率": "follow_rate",
    "咨询": "consultations",
    "私信": "consultations",
    "线索": "consultations",
    "成交": "conversions",
    "转化": "conversions",
    "收入": "revenue",
    "播放": "views",
    "阅读": "views",
    "曝光": "views",
}

TREATMENT_ALIASES = {
    "痛点": "title_style",
    "教程": "title_style",
    "标题": "title_style",
    "平台": "platform",
    "主题": "topic",
    "选题": "topic",
}


def link_entities(user_goal: str, columns: list[str], prior: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map surface mentions to column/node ids with confidence."""
    prior = prior or {}
    goal = user_goal or ""
    linked: list[dict[str, Any]] = []

    for mention, canonical in _scan_aliases(goal, PLATFORM_ALIASES):
        target = "platform" if "platform" in columns else canonical
        linked.append(_entry(mention, target, canonical, columns))

    for mention, canonical in _scan_aliases(goal, OUTCOME_ALIASES):
        target = canonical if canonical in columns else _best_column(columns, OUTCOME_ALIASES.values())
        if target:
            linked.append(_entry(mention, target, canonical, columns))

    for mention, canonical in _scan_aliases(goal, TREATMENT_ALIASES):
        target = canonical if canonical in columns else _best_column(columns, TREATMENT_ALIASES.values())
        if target:
            linked.append(_entry(mention, target, canonical, columns))

    for key, value in prior.items():
        if key in goal and value:
            linked.append({"mention": key, "column": value, "confidence": 0.85, "source": "session_prior"})

    deduped = _dedupe(linked)
    return {
        "linked_entities": deduped,
        "unresolved": [m for m in re.findall(r"那个|上次|这篇", goal) if not deduped],
        "ready": bool(deduped) or not goal.strip(),
    }


def _scan_aliases(text: str, aliases: dict[str, str]) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    lower = text.lower()
    for mention, canonical in aliases.items():
        if mention.lower() in lower or mention in text:
            hits.append((mention, canonical))
    return hits


def _entry(mention: str, column: str, canonical: str, columns: list[str]) -> dict[str, Any]:
    confidence = 0.9 if column in columns else 0.45
    return {
        "mention": mention,
        "column": column if column in columns else None,
        "canonical": canonical,
        "confidence": confidence,
        "source": "alias_rules",
        "candidates": [c for c in columns if canonical in c or c in {column, canonical}],
    }


def _best_column(columns: list[str], candidates) -> str | None:
    for col in columns:
        if col in candidates:
            return col
    return None


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = f"{item.get('mention')}:{item.get('column')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
