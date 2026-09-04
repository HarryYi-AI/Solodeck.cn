from __future__ import annotations

from typing import Any

import pandas as pd


class ActiveVerifier:
    """Executable probes for silent analytical errors, not merely schema checks."""

    def inspect_join(
        self,
        left: pd.DataFrame,
        right: pd.DataFrame,
        *,
        left_on: str,
        right_on: str,
        result: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        issues, warnings = [], []
        if left_on not in left or right_on not in right:
            return {"valid": False, "issues": ["连接键不存在"], "warnings": [], "probes": {}}
        left_dup = float(left[left_on].duplicated(keep=False).mean())
        right_dup = float(right[right_on].duplicated(keep=False).mean())
        expected = left.merge(right, left_on=left_on, right_on=right_on, how="left")
        inflation = len(expected) / max(1, len(left))
        if left_dup > 0 and right_dup > 0:
            warnings.append("两侧连接键都不唯一，存在多对多连接风险")
        if inflation > 1.2:
            issues.append(f"连接后行数膨胀 {inflation:.2f} 倍，聚合结果可能被重复计算")
        if result is not None and len(result) != len(expected):
            issues.append("实际连接结果与独立探针重算不一致")
        return {"valid": not issues, "issues": issues, "warnings": warnings,
                "probes": {"left_duplicate_rate": left_dup, "right_duplicate_rate": right_dup,
                           "expected_rows": len(expected), "row_inflation": inflation}}

    def inspect_rate(self, frame: pd.DataFrame, numerator: str, denominator: str, reported: pd.Series | None = None) -> dict[str, Any]:
        issues, warnings = [], []
        missing = [column for column in (numerator, denominator) if column not in frame]
        if missing:
            return {"valid": False, "issues": [f"比率字段不存在: {missing}"], "warnings": [], "probes": {}}
        denominator_values = pd.to_numeric(frame[denominator], errors="coerce")
        numerator_values = pd.to_numeric(frame[numerator], errors="coerce")
        zero_count = int((denominator_values == 0).sum())
        computed = numerator_values.div(denominator_values.where(denominator_values != 0))
        if zero_count: warnings.append(f"有 {zero_count} 行分母为 0，已按缺失处理")
        if reported is not None:
            comparable = pd.concat([computed, pd.to_numeric(reported, errors="coerce")], axis=1).dropna()
            if not comparable.empty and float((comparable.iloc[:, 0] - comparable.iloc[:, 1]).abs().max()) > 1e-8:
                issues.append("报告比率与分子/分母重算结果不一致")
        return {"valid": not issues, "issues": issues, "warnings": warnings,
                "probes": {"valid_rows": int(computed.notna().sum()), "zero_denominators": zero_count,
                           "recomputed_mean": float(computed.mean()) if computed.notna().any() else None}}

    def compare_artifacts(self, artifacts: list[dict[str, Any]], key: str | tuple[str, ...]) -> dict[str, Any]:
        keys = (key,) if isinstance(key, str) else key
        values = []
        for artifact in artifacts:
            content = artifact.get("content", artifact)
            matched = next((content[item] for item in keys if content.get(item) is not None), None)
            if matched is not None:
                values.append((artifact.get("id"), matched))
        unique = {str(value) for _, value in values}
        label = "/".join(keys)
        return {"valid": len(unique) <= 1, "issues": [] if len(unique) <= 1 else [f"工件对 {label} 给出矛盾结果"], "values": values}
