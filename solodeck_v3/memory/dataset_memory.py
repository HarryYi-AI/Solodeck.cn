from __future__ import annotations

import pandas as pd

from .memory_store import JsonMemoryStore


def store_dataset_memory(trace_id: str, df: pd.DataFrame) -> dict:
    memory = JsonMemoryStore("dataset_memory")
    summary = {
        "trace_id": trace_id,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "numeric_columns": [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])],
    }
    return memory.append(summary)

