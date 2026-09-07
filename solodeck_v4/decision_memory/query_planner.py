from __future__ import annotations

import re
from typing import Any

from .schemas import MemoryQueryPlan


PLATFORM_ALIASES = {
    "小红书": "xiaohongshu", "XHS": "xiaohongshu", "抖音": "douyin",
    "B站": "bilibili", "公众号": "wechat", "视频号": "wechat",
    "淘宝": "taobao", "TikTok": "tiktok", "YouTube": "youtube",
}
METRIC_ALIASES = {
    "收藏率": "save_rate", "收藏": "favorites", "点击率": "ctr",
    "转化率": "conversion_rate", "转化": "conversions", "成交": "conversions",
    "咨询": "consultations", "收入": "revenue", "播放": "views",
}


def plan_memory_query(query: str, task_spec: dict[str, Any] | None = None) -> MemoryQueryPlan:
    text = query or ""
    task_spec = task_spec or {}
    platform = next((value for label, value in PLATFORM_ALIASES.items() if label.lower() in text.lower()), "")
    metric = next((value for label, value in METRIC_ALIASES.items() if label in text), "")
    topic = _topic_from_spec(task_spec)
    asks_why = any(term in text for term in ("为什么", "原因", "下降", "变化"))
    asks_history = any(term in text for term in ("过去", "之前", "上次", "历史", "曾经", "最近"))
    asks_action = any(term in text for term in ("怎么做", "策略", "建议", "继续", "暂停", "放大"))
    asks_current_value = bool(re.search(r"最近|当前|现在|多少|最高|最低|排名|下降|上升", text))

    requirements = []
    if metric:
        requirements.extend([f"recent {metric}", f"previous {metric}"])
    if asks_why:
        requirements.extend(["topic mix", "format mix", "posting frequency", "platform segmentation"])
    requirements = list(dict.fromkeys(requirements))
    rationale = []
    if asks_current_value:
        rationale.append("当前数值必须由实时数据层重新计算")
    if asks_history or asks_why:
        rationale.append("检索相似历史决策和当时业务阶段")
    if asks_action:
        rationale.append("检索历史策略结果与失败经验")

    return MemoryQueryPlan(
        need_current_profile=asks_why or asks_action,
        need_active_regime=asks_why or asks_history,
        need_similar_decision_episodes=asks_why or asks_history or asks_action,
        need_strategy_evidence=asks_why or asks_action,
        need_historical_failures=asks_action or asks_why,
        requires_live_data=asks_current_value,
        filters={key: value for key, value in {"platform": platform, "metric": metric, "topic": topic}.items() if value},
        live_data_requirements=requirements,
        rationale=rationale,
    )


def _topic_from_spec(task_spec: dict[str, Any]) -> str:
    filters = task_spec.get("filters") or {}
    if isinstance(filters, dict) and filters.get("topic"):
        return str(filters["topic"])
    return str(task_spec.get("topic") or "")
