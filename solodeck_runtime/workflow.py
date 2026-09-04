from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import TaskSpec, Workflow, WorkflowNode


SKILL_BY_OPERATION = {
    "LoadDataset": "DataIngestionSkill",
    "ProfileSchema": "SchemaSkill",
    "ResolveEntities": "EntityResolutionSkill",
    "JoinTables": "JoinSkill",
    "CreateMetric": "MetricSkill",
    "Describe": "DescriptiveComparisonSkill",
    "CausalReadiness": "CausalReadinessSkill",
    "Bootstrap": "BootstrapSkill",
    "Regression": "RegressionSkill",
    "ValidateClaim": "ActiveVerifierSkill",
    "GenerateReport": "ReportSkill",
}


class WorkflowCompiler:
    def compile(self, task: TaskSpec, grounding: Any) -> Workflow:
        operations = ["LoadDataset", "ProfileSchema", "ResolveEntities"]
        if len(grounding.selected_tables) > 1 and grounding.join_candidates:
            operations.append("JoinTables")
        operations.append("CreateMetric")
        if task.task_type in {"causal_effect_estimation", "counterfactual_analysis", "experiment_design"}:
            operations.extend(["CausalReadiness", "Bootstrap", "Regression"])
        else:
            operations.append("Describe")
        operations.extend(["ValidateClaim", "GenerateReport"])

        nodes, previous = [], None
        for operation in operations:
            node = WorkflowNode(
                operation_type=operation,
                required_skill=SKILL_BY_OPERATION[operation],
                dependencies=[previous] if previous else [],
                outputs=[operation.lower()],
                validation_policy=self._validation_policy(operation),
                estimated_cost=0.08 if operation in {"Bootstrap", "Regression"} else 0.01,
                parameters=self._parameters(operation, task, grounding),
            )
            nodes.append(node)
            previous = node.node_id
        physical, notes = self.optimize(nodes)
        return Workflow(task.task_id, nodes, physical, optimization_notes=notes)

    def optimize(self, logical_nodes: list[WorkflowNode], cached_outputs: set[str] | None = None) -> tuple[list[WorkflowNode], list[str]]:
        cached_outputs = cached_outputs or set()
        physical, seen, notes = [], set(), []
        for original in logical_nodes:
            node = deepcopy(original)
            signature = (node.operation_type, tuple(sorted(node.parameters.items(), key=lambda x: x[0])))
            if str(signature) in seen:
                notes.append(f"移除重复节点 {node.operation_type}")
                continue
            seen.add(str(signature))
            if set(node.outputs) & cached_outputs:
                node.status = "cached"
                notes.append(f"复用缓存 {node.operation_type}")
            physical.append(node)
        return physical, notes

    @staticmethod
    def insert_node(workflow: Workflow, after_node_id: str, node: WorkflowNode) -> Workflow:
        nodes = workflow.physical_nodes
        index = next((i for i, item in enumerate(nodes) if item.node_id == after_node_id), None)
        if index is None:
            raise KeyError(after_node_id)
        former_children = [item for item in nodes if after_node_id in item.dependencies]
        node.dependencies = [after_node_id]
        for child in former_children:
            child.dependencies = [node.node_id if dep == after_node_id else dep for dep in child.dependencies]
        nodes.insert(index + 1, node)
        workflow.version += 1
        workflow.optimization_notes.append(f"运行时插入 {node.operation_type}")
        return workflow

    @staticmethod
    def _validation_policy(operation: str) -> list[str]:
        policies = ["output_schema"]
        if operation == "JoinTables": policies.extend(["join_cardinality", "row_inflation"])
        if operation == "CreateMetric": policies.extend(["denominator", "missingness"])
        if operation in {"Bootstrap", "Regression"}: policies.extend(["sample_size", "uncertainty"])
        if operation == "GenerateReport": policies.extend(["claim_lineage", "privacy"])
        return policies

    @staticmethod
    def _parameters(operation: str, task: TaskSpec, grounding: Any) -> dict[str, Any]:
        if operation == "JoinTables": return {"candidates": grounding.join_candidates[:3]}
        if operation == "CreateMetric": return {"outcome": task.outcome, "dimensions": task.dimensions}
        if operation in {"Bootstrap", "Regression", "CausalReadiness"}:
            return {"treatment": task.treatment, "outcome": task.outcome, "unit": task.analysis_unit}
        return {}


class WorkflowValidator:
    def validate(self, workflow: Workflow, *, datasets: dict[str, Any], allowed_skills: set[str] | None = None) -> dict[str, Any]:
        issues, warnings = [], []
        ids = [node.node_id for node in workflow.physical_nodes]
        if len(ids) != len(set(ids)): issues.append("workflow node_id 不唯一")
        known = set(ids)
        for node in workflow.physical_nodes:
            missing = set(node.dependencies) - known
            if missing: issues.append(f"{node.node_id} 引用了不存在的依赖 {sorted(missing)}")
            if allowed_skills is not None and node.required_skill not in allowed_skills:
                issues.append(f"未注册 Skill: {node.required_skill}")
        if self._has_cycle(workflow.physical_nodes): issues.append("执行计划不是 DAG")
        if not datasets:
            issues.append("没有可执行的数据源")
        available_columns = {str(column) for frame in datasets.values() for column in getattr(frame, "columns", [])}
        required_columns = set()
        for node in workflow.physical_nodes:
            if node.operation_type in {"CreateMetric", "CausalReadiness", "Bootstrap", "Regression"}:
                required_columns.update(
                    value for key, value in node.parameters.items()
                    if key in {"treatment", "outcome"} and isinstance(value, str) and value
                )
        missing_columns = required_columns - available_columns
        if missing_columns:
            issues.append(f"工作流引用了不存在的字段 {sorted(missing_columns)}")
        cost = sum(node.estimated_cost for node in workflow.physical_nodes if node.status != "cached")
        if cost > 1.0: warnings.append("预计执行成本超过默认单任务预算")
        workflow.validation_status = "valid" if not issues else "invalid"
        return {"valid": not issues, "issues": issues, "warnings": warnings, "estimated_cost": round(cost, 4)}

    @staticmethod
    def _has_cycle(nodes: list[WorkflowNode]) -> bool:
        graph = {node.node_id: node.dependencies for node in nodes}
        visiting, visited = set(), set()
        def visit(node_id: str) -> bool:
            if node_id in visiting: return True
            if node_id in visited: return False
            visiting.add(node_id)
            if any(visit(parent) for parent in graph.get(node_id, [])): return True
            visiting.remove(node_id); visited.add(node_id)
            return False
        return any(visit(node_id) for node_id in graph)
