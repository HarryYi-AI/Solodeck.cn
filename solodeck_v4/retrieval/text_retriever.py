from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from solodeck_v4.retrieval.memory_store import MemoryStore


def retrieve_text(
    query: str,
    store: MemoryStore | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    store = store or MemoryStore()
    chunks = store.text_chunks()
    if not chunks:
        return []

    embed_hits = _try_embedding_retrieval(query, chunks, limit)
    if embed_hits:
        return embed_hits

    hits = _bm25_retrieval(query, chunks, limit)
    if hits:
        return hits
    return _keyword_fallback(query, chunks, limit)


def _keyword_fallback(query: str, chunks: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    q = query or ""
    keywords = [t for t in _tokenize(q) if len(t) >= 2]
    hits: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        text = chunk.get("text") or chunk.get("content") or ""
        score = sum(1 for kw in keywords if kw in text) / max(len(keywords), 1)
        if score <= 0:
            continue
        hits.append(
            {
                "source_type": "text",
                "source_id": chunk.get("chunk_id") or chunk.get("id") or f"text:chunk:{idx}",
                "content": text[:400],
                "score": min(score, 1.0),
                "used_for": chunk.get("used_for") or "context",
                "meta": {"retriever": "keyword_fallback", "chunk_index": idx},
            }
        )
    return sorted(hits, key=lambda x: x["score"], reverse=True)[:limit]


def _tokenize(text: str) -> list[str]:
    raw = (text or "").lower()
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z_][a-zA-Z0-9_]*", raw)
    expanded: list[str] = []
    for token in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 4:
            for size in (2, 3):
                for i in range(len(token) - size + 1):
                    expanded.append(token[i : i + size])
        else:
            expanded.append(token)
    return [t for t in expanded if len(t) >= 2]


def _bm25_retrieval(query: str, chunks: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    docs = [(idx, _tokenize(chunk.get("text") or chunk.get("content") or "")) for idx, chunk in enumerate(chunks)]
    n_docs = len(docs)
    df: Counter[str] = Counter()
    for _, tokens in docs:
        df.update(set(tokens))

    avg_dl = sum(len(tokens) for _, tokens in docs) / max(n_docs, 1)
    k1, b = 1.5, 0.75
    hits: list[dict[str, Any]] = []

    for idx, tokens in docs:
        if not tokens:
            continue
        tf = Counter(tokens)
        dl = len(tokens)
        score = 0.0
        for term in q_tokens:
            if term not in tf:
                continue
            idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avg_dl))

        if score <= 0:
            continue
        chunk = chunks[idx]
        text = chunk.get("text") or chunk.get("content") or ""
        hits.append(
            {
                "source_type": "text",
                "source_id": chunk.get("chunk_id") or chunk.get("id") or f"text:chunk:{idx}",
                "content": text[:400],
                "score": min(score / 10.0, 1.0),
                "used_for": chunk.get("used_for") or "context",
                "meta": {"retriever": "bm25", "chunk_index": idx},
            }
        )

    return sorted(hits, key=lambda x: x["score"], reverse=True)[:limit]


def _try_embedding_retrieval(query: str, chunks: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return []

    try:
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        texts = [c.get("text") or c.get("content") or "" for c in chunks]
        if not any(texts):
            return []
        q_emb = model.encode([query], normalize_embeddings=True)
        doc_emb = model.encode(texts, normalize_embeddings=True)
        scores = (doc_emb @ q_emb.T).ravel()
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:limit]
        hits: list[dict[str, Any]] = []
        for idx, score in ranked:
            if score <= 0.15:
                continue
            chunk = chunks[idx]
            text = chunk.get("text") or chunk.get("content") or ""
            hits.append(
                {
                    "source_type": "text",
                    "source_id": chunk.get("chunk_id") or chunk.get("id") or f"text:chunk:{idx}",
                    "content": text[:400],
                    "score": float(score),
                    "used_for": chunk.get("used_for") or "context",
                    "meta": {"retriever": "sentence-transformers"},
                }
            )
        return hits
    except Exception:
        return []
