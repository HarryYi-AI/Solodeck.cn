from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable


ACTION_SPACE = ("sql", "python", "plot", "causal", "search", "memory", "finish")


@dataclass
class ToolRouteDecision:
    action: str
    confidence: float
    reason: str
    alternatives: list[str] = field(default_factory=list)
    policy: str = "rule_baseline"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def route_tool(
    state: dict[str, Any],
    policy: Callable[[dict[str, Any], tuple[str, ...]], str | dict[str, Any]] | None = None,
) -> ToolRouteDecision:
    """Stable router API; a classifier, small LM or RL policy can replace policy."""
    if policy is not None:
        raw = policy(state, ACTION_SPACE)
        if isinstance(raw, str):
            raw = {"action": raw}
        action = raw.get("action")
        if action not in ACTION_SPACE:
            raise ValueError(f"policy returned invalid action: {action}")
        return ToolRouteDecision(
            action=action,
            confidence=float(raw.get("confidence", 0.5)),
            reason=str(raw.get("reason", "external policy")),
            alternatives=[item for item in raw.get("alternatives", []) if item in ACTION_SPACE],
            policy=str(raw.get("policy", "external_policy")),
        )

    text = str(state.get("task") or state.get("message") or "").lower()
    kind = str(state.get("kind") or "")
    if state.get("done"):
        return ToolRouteDecision("finish", 1.0, "任务已有通过校验的结果")
    if kind == "causal" or any(word in text for word in ("ate", "cate", "因果", "增量", "混杂")):
        return ToolRouteDecision("causal", 0.96, "任务要求估计干预效果", ["python"])
    if kind == "sql" or any(word in text for word in ("sql", "订单", "分组汇总", "数据库")):
        return ToolRouteDecision("sql", 0.90, "结构化聚合适合数据库执行", ["python"])
    if kind in {"python", "numpy", "pandas"} or any(word in text for word in ("均值", "中位数", "相关", "缺失", "dataframe")):
        return ToolRouteDecision("python", 0.88, "需要 DataFrame 或数值计算", ["sql"])
    if any(word in text for word in ("图", "趋势", "可视化")):
        return ToolRouteDecision("plot", 0.86, "输出目标是可视化", ["python"])
    if any(word in text for word in ("之前", "历史", "记忆")):
        return ToolRouteDecision("memory", 0.84, "问题引用历史分析状态", ["search"])
    if any(word in text for word in ("搜索", "资料", "文档")):
        return ToolRouteDecision("search", 0.82, "问题需要检索外部或文本证据", ["memory"])
    return ToolRouteDecision("python", 0.45, "低置信回退到受控 Python 分析", ["sql", "finish"])
