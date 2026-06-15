from __future__ import annotations

import json
from pathlib import Path


def generate_tasks(path: str | Path | None = None) -> list[dict]:
    tasks = []
    for i in range(10):
        tasks.append({"id": f"schema_{i+1:02d}", "type": "schema_grounding", "goal": f"识别第 {i+1} 组上传数据字段并给出质量提醒"})
    for i in range(5):
        tasks.append({"id": f"kg_{i+1:02d}", "type": "kg_construction", "goal": f"构建内容、平台、主题和指标的知识图谱 {i+1}"})
    for i in range(5):
        tasks.append({"id": f"causal_{i+1:02d}", "type": "causal_validity", "goal": f"判断标题风格是否提升咨询数，避免强因果结论 {i+1}"})
    for i in range(5):
        tasks.append({"id": f"stats_{i+1:02d}", "type": "statistical_uncertainty", "goal": f"检查小样本策略增量的 Bootstrap 区间稳定性 {i+1}"})
    for i in range(5):
        tasks.append({"id": f"repair_{i+1:02d}", "type": "failure_repair", "goal": f"当验证失败时生成修复计划并降级为验证建议 {i+1}"})
    if path:
        Path(path).write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    return tasks


if __name__ == "__main__":
    generate_tasks(Path(__file__).with_name("tasks_v3.json"))

