from __future__ import annotations


class ExplorerAgent:
    name = "ExplorerAgent"

    def repair_options(self, critique: dict) -> list[str]:
        options = []
        if critique.get("unstable_ci"):
            options.append("补充 Bootstrap 或延长验证周期")
        if critique.get("unsupported_causal_claim"):
            options.append("降级为探索性假设并补充混杂变量")
        if not options:
            options.append("保留当前最佳产物并记录后续数据")
        return options

