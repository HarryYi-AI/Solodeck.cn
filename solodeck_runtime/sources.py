from __future__ import annotations

import re
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls", ".db", ".sqlite", ".txt", ".md"}


@dataclass(frozen=True)
class SourceDescriptor:
    source_id: str
    name: str
    source_type: str
    location: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class SourceAdapter(ABC):
    """Small MCP-shaped contract for source-specific data access."""

    @abstractmethod
    def list_sources(self) -> list[SourceDescriptor]: ...

    @abstractmethod
    def inspect_source(self, source_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def search_source(self, source_id: str, query: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def read_source(self, source_id: str, selection: dict[str, Any]) -> dict[str, Any]: ...


class DataFrameSourceAdapter(SourceAdapter):
    def __init__(self, sources: dict[str, pd.DataFrame], names: dict[str, str] | None = None) -> None:
        self.sources = sources
        self.names = names or {}

    def list_sources(self) -> list[SourceDescriptor]:
        return [
            SourceDescriptor(source_id, self.names.get(source_id, source_id), "dataframe", "runtime")
            for source_id in self.sources
        ]

    def inspect_source(self, source_id: str) -> dict[str, Any]:
        frame = self._frame(source_id)
        return _frame_profile(frame)

    def search_source(self, source_id: str, query: dict[str, Any]) -> dict[str, Any]:
        frame = _filter_frame(self._frame(source_id), query.get("filters") or [])
        columns = [name for name in query.get("columns") or [] if name in frame.columns]
        if columns:
            frame = frame[columns]
        return _safe_frame_result(frame, query.get("limit", 50))

    def read_source(self, source_id: str, selection: dict[str, Any]) -> dict[str, Any]:
        frame = self._frame(source_id)
        start = max(0, int(selection.get("offset", 0)))
        limit = max(1, min(int(selection.get("limit", 50)), 200))
        columns = [name for name in selection.get("columns") or list(frame.columns) if name in frame.columns]
        return _safe_frame_result(frame.iloc[start : start + limit][columns], limit)

    def _frame(self, source_id: str) -> pd.DataFrame:
        if source_id not in self.sources:
            raise KeyError(f"unknown source: {source_id}")
        return self.sources[source_id]


class FileSourceAdapter(SourceAdapter):
    """CSV/Excel/SQLite/text dispatch without vectorizing structured data."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def list_sources(self) -> list[SourceDescriptor]:
        if not self.root.exists():
            return []
        return [self._descriptor(path) for path in sorted(self.root.rglob("*")) if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES]

    def inspect_source(self, source_id: str) -> dict[str, Any]:
        path = self._path(source_id)
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            return {"source_type": "text", "characters": len(text), "lines": len(text.splitlines()), "sections": len(re.findall(r"^#+\s", text, re.M))}
        if suffix in {".db", ".sqlite"}:
            with sqlite3.connect(path) as db:
                tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                schemas = {table: [dict(zip(("cid", "name", "type", "notnull", "default", "pk"), row)) for row in db.execute(f'PRAGMA table_info("{table}")')] for table in tables}
            return {"source_type": "sqlite", "tables": tables, "schemas": schemas}
        if suffix in {".xlsx", ".xls"}:
            book = pd.ExcelFile(path)
            sheets = {sheet: _frame_profile(pd.read_excel(path, sheet_name=sheet, nrows=200)) for sheet in book.sheet_names}
            return {"source_type": "excel", "sheets": sheets}
        return {"source_type": "csv", **_frame_profile(pd.read_csv(path, nrows=1000))}

    def search_source(self, source_id: str, query: dict[str, Any]) -> dict[str, Any]:
        path = self._path(source_id)
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            return _search_text(path.read_text(encoding="utf-8", errors="replace"), str(query.get("text") or ""), int(query.get("limit", 20)))
        if suffix in {".db", ".sqlite"}:
            sql = str(query.get("sql") or "").strip()
            if not re.match(r"(?is)^\s*(select|with)\b", sql):
                raise ValueError("SQLite search only accepts SELECT/WITH queries")
            with sqlite3.connect(path) as db:
                return _safe_frame_result(pd.read_sql_query(sql, db), int(query.get("limit", 100)))
        sheet = query.get("sheet")
        frame = pd.read_excel(path, sheet_name=sheet or 0) if suffix in {".xlsx", ".xls"} else pd.read_csv(path)
        return DataFrameSourceAdapter({source_id: frame}).search_source(source_id, query)

    def read_source(self, source_id: str, selection: dict[str, Any]) -> dict[str, Any]:
        path = self._path(source_id)
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            start = max(0, int(selection.get("line_start", 1)) - 1)
            end = min(len(lines), int(selection.get("line_end", start + 80)))
            return {"line_start": start + 1, "line_end": end, "text": "\n".join(lines[start:end])}
        return self.search_source(source_id, selection)

    def _descriptor(self, path: Path) -> SourceDescriptor:
        suffix = path.suffix.lower()
        kind = "excel" if suffix in {".xlsx", ".xls"} else "sqlite" if suffix in {".db", ".sqlite"} else "text" if suffix in {".txt", ".md"} else "csv"
        return SourceDescriptor(str(path.relative_to(self.root)), path.name, kind, str(path))

    def _path(self, source_id: str) -> Path:
        path = (self.root / source_id).resolve()
        if self.root not in path.parents or not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise KeyError(f"unknown source: {source_id}")
        return path


def _frame_profile(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        "null_ratio": {str(column): round(float(value), 4) for column, value in frame.isna().mean().items()},
        "unique_ratio": {str(column): round(float(frame[column].nunique(dropna=True) / max(1, len(frame))), 4) for column in frame.columns},
        "sample_values": {str(column): [str(value)[:80] for value in frame[column].dropna().head(3).tolist()] for column in frame.columns},
    }


def _filter_frame(frame: pd.DataFrame, filters: list[dict[str, Any]]) -> pd.DataFrame:
    result = frame.copy()
    for item in filters:
        column, operator, value = item.get("column"), item.get("operator", "eq"), item.get("value")
        if column not in result.columns:
            raise KeyError(f"missing column: {column}")
        series = result[column]
        if operator == "eq": result = result[series.astype(str).str.lower() == str(value).lower()]
        elif operator == "contains": result = result[series.astype(str).str.contains(str(value), case=False, na=False, regex=False)]
        elif operator == "gte": result = result[pd.to_numeric(series, errors="coerce") >= float(value)]
        elif operator == "lte": result = result[pd.to_numeric(series, errors="coerce") <= float(value)]
        elif operator == "month": result = result[pd.to_datetime(series, errors="coerce").dt.month == int(value)]
        else: raise ValueError(f"unsupported filter operator: {operator}")
    return result


def _safe_frame_result(frame: pd.DataFrame, limit: int) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    safe = frame.head(limit).copy()
    safe = safe.where(pd.notna(safe), None)
    return {"row_count": int(len(frame)), "columns": list(frame.columns), "rows": safe.to_dict("records"), "truncated": len(frame) > limit}


def _search_text(text: str, query: str, limit: int) -> dict[str, Any]:
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", query)]
    lines = text.splitlines()
    matches = []
    for index, line in enumerate(lines):
        score = sum(term in line.lower() for term in terms)
        if score:
            matches.append({"line": index + 1, "score": score, "text": line[:400]})
    matches.sort(key=lambda item: (-item["score"], item["line"]))
    return {"matches": matches[: max(1, min(limit, 100))], "retrieval": "lexical"}
