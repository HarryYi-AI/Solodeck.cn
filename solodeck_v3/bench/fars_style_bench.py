from __future__ import annotations

import json
from pathlib import Path


FARS_TYPES = [
    ("ideation", "头脑风暴：根据知识图谱生成 3 个可验证经营假设"),
    ("planning", "规划：把假设转换成可执行工作流和方法计划"),
    ("experiment", "实验设计：运行实验或统计工具并记录可追溯产物"),
    ("writing", "写作：生成通过校验的简明报告、限制和下一步"),
    ("causal_validity", "判断策略是否可以做因果增量表述"),
    ("failure_repair", "验证失败后生成修复计划并更新记忆"),
]


def generate_fars_tasks(path: str | Path | None = None) -> list[dict]:
    tasks = []
    for task_type, goal in FARS_TYPES:
        for i in range(10):
            tasks.append({
                "id": f"{task_type}_{i + 1:02d}",
                "type": task_type,
                "goal": f"{goal} #{i + 1}",
            })
    if path:
        Path(path).write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    return tasks


if __name__ == "__main__":
    generate_fars_tasks(Path(__file__).with_name("fars_tasks.json"))
