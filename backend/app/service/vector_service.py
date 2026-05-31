from __future__ import annotations

import json
import math
import re
import threading
from collections import Counter
from pathlib import Path

import faiss
import numpy as np

from app.config.settings import settings
from app.service.embedding_service import EmbeddingService


class VectorService:
    """FAISS 向量存储服务。

    管理文档切片的向量索引，支持混合检索（向量 + BM25）、重排序和去重。
    使用线程安全的缓存机制避免重复加载索引。
    """

    _lock = threading.Lock()
    _cached_index: faiss.Index | None = None
    _cached_metadata: list[dict[str, object]] | None = None
    _cache_valid = False

    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()
        self.faiss_dir = Path(settings.data_dir) / "faiss"
        self.chunks_dir = Path(settings.data_dir) / "chunks"
        self.faiss_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.faiss_dir / "index.faiss"
        self.meta_path = self.faiss_dir / "metadata.json"

    def _load_all_chunks(self) -> list[dict[str, object]]:
        """加载所有 chunk JSON 文件。"""
        chunks: list[dict[str, object]] = []
        for p in sorted(self.chunks_dir.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            chunks.extend(data)
        return chunks

    def has_chunks(self) -> bool:
        """检查是否存在任何 chunk 文件。"""
        return any(self.chunks_dir.glob("*.json"))

    def rebuild_index(self) -> dict[str, object]:
        """重建 FAISS 索引。

        从所有 chunk 文件重新计算向量并构建索引。

        Returns:
            包含 status、vectors、dim 的字典
        """
        with self._lock:
            chunks = self._load_all_chunks()
            if not chunks:
                raise ValueError("no_chunks_found")

            texts = [c["content"] for c in chunks]
            vectors = self.embedding_service.embed_documents(texts).astype(np.float32)
            dim = vectors.shape[1]
            index = faiss.IndexFlatIP(dim)
            index.add(vectors)

            faiss.write_index(index, str(self.index_path))
            self.meta_path.write_text(
                json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # Update in-memory cache
            VectorService._cached_index = index
            VectorService._cached_metadata = chunks
            VectorService._cache_valid = True

            return {"indexed_chunks": len(chunks), "dimension": dim}

    def ensure_index(self) -> None:
        """确保索引存在且与 chunks 目录一致。若索引缺失或 chunks 数量不匹配则自动重建。"""
        current_chunks = self._load_all_chunks()
        current_count = len(current_chunks)

        # 索引不存在 → 必须重建
        if not self.index_path.exists() or not self.meta_path.exists():
            if current_count > 0:
                self.rebuild_index()
            return

        # 索引存在 → 检查是否与 chunks 一致
        try:
            existing_meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            self.rebuild_index()
            return

        if len(existing_meta) != current_count:
            # chunks 数量发生变化，需要重建
            if current_count > 0:
                self.rebuild_index()

    def _get_index_and_metadata(self) -> tuple[faiss.Index, list[dict]]:
        """Return the index and metadata, using cache if valid."""
        if VectorService._cache_valid and VectorService._cached_index is not None and VectorService._cached_metadata is not None:
            return VectorService._cached_index, VectorService._cached_metadata

        # Cache miss — load from disk and populate cache
        with self._lock:
            index = faiss.read_index(str(self.index_path))
            metadata = json.loads(self.meta_path.read_text(encoding="utf-8"))
            VectorService._cached_index = index
            VectorService._cached_metadata = metadata
            VectorService._cache_valid = True
            return index, metadata

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower()
        cjk = re.findall(r'[\u4e00-\u9fff]', text)
        words = re.findall(r'[a-z0-9_]+', text)
        return cjk + words

    def _bm25_search(self, query: str, metadata: list[dict], top_k: int) -> dict[int, float]:
        """BM25 关键词检索，返回 {chunk_index: score}"""
        k1, b = 1.5, 0.75
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return {}

        doc_count = len(metadata)
        avg_dl = sum(len(self._tokenize(c.get("content", ""))) for c in metadata) / max(doc_count, 1)

        df: Counter = Counter()
        doc_tokens_cache: list[list[str]] = []
        for chunk in metadata:
            tokens = self._tokenize(chunk.get("content", ""))
            doc_tokens_cache.append(tokens)
            unique = set(tokens)
            for t in unique:
                df[t] += 1

        scores: dict[int, float] = {}
        for idx, tokens in enumerate(doc_tokens_cache):
            if not tokens:
                continue
            tf = Counter(tokens)
            dl = len(tokens)
            score = 0.0
            for qt in query_tokens:
                if qt not in tf:
                    continue
                n = df.get(qt, 0)
                idf = math.log((doc_count - n + 0.5) / (n + 0.5) + 1)
                tf_val = (tf[qt] * (k1 + 1)) / (tf[qt] + k1 * (1 - b + b * dl / max(avg_dl, 1)))
                score += idf * tf_val
            if score > 0:
                scores[idx] = score

        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k * 2]
        if top:
            max_score = top[0][1]
            return {idx: s / max_score for idx, s in top}
        return {}

    def _rerank(self, query: str, results: list[dict]) -> list[dict]:
        """基于关键词重叠的轻量重排序"""
        query_tokens = set(self._tokenize(query))
        if not query_tokens:
            return results

        for r in results:
            doc_tokens = set(self._tokenize(r.get("content", "")))
            overlap = len(query_tokens & doc_tokens) / len(query_tokens) if query_tokens else 0
            r["rerank_boost"] = overlap

        results.sort(key=lambda x: x.get("score", 0) + x.get("rerank_boost", 0) * 0.3, reverse=True)
        return results

    def search(
        self,
        question: str,
        top_k: int = 3,
        score_threshold: float | None = None,
    ) -> tuple[list[dict], str]:
        self.ensure_index()

        index, metadata = self._get_index_and_metadata()

        # 向量检索
        query = self.embedding_service.embed_text(question).astype(np.float32).reshape(1, -1)
        if query.shape[1] != index.d:
            self.rebuild_index()
            index, metadata = self._get_index_and_metadata()
            query = self.embedding_service.embed_text(question).astype(np.float32).reshape(1, -1)
        vec_scores, vec_ids = index.search(query, top_k * 2)

        # BM25 关键词检索
        bm25_scores = self._bm25_search(question, metadata, top_k)

        # 合并向量和 BM25 结果（RRF 融合）
        candidate_indices: dict[int, float] = {}
        vec_weight, bm25_weight = 0.6, 0.4

        for rank, (score, idx) in enumerate(zip(vec_scores[0], vec_ids[0])):
            if idx < 0 or idx >= len(metadata):
                continue
            rrf_score = 1.0 / (rank + 60)
            candidate_indices[int(idx)] = candidate_indices.get(int(idx), 0) + rrf_score * vec_weight

        for idx, score in bm25_scores.items():
            rrf_score = score / 60
            candidate_indices[idx] = candidate_indices.get(idx, 0) + rrf_score * bm25_weight

        sorted_candidates = sorted(candidate_indices.items(), key=lambda x: x[1], reverse=True)[:top_k * 2]

        results: list[dict] = []
        for idx, fused_score in sorted_candidates:
            if score_threshold is not None and fused_score < score_threshold:
                continue
            item = metadata[idx]
            full_content = item.get("content", "")
            results.append(
                {
                    "document_id": item.get("document_id"),
                    "source_file": item.get("source_file"),
                    "file_type": item.get("file_type"),
                    "chunk_id": item.get("chunk_id"),
                    "chunk_index": item.get("chunk_index"),
                    "total_chunks": item.get("total_chunks"),
                    "page_no": item.get("page_no"),
                    "section": item.get("section"),
                    "char_start": item.get("char_start"),
                    "char_end": item.get("char_end"),
                    "score": fused_score,
                    "content": full_content,
                    "preview": full_content[:200],
                }
            )

        # 重排序
        results = self._rerank(question, results)

        # 去重重叠切片
        results = self._dedup_chunks(results)

        return results[:top_k], self.embedding_service.mode

    @staticmethod
    def _dedup_chunks(results: list[dict]) -> list[dict]:
        """去除内容高度重叠的切片"""
        if len(results) <= 1:
            return results
        deduped: list[dict] = []
        seen_content: list[str] = []
        for r in results:
            content = r.get("content", "")
            is_dup = False
            for seen in seen_content:
                if len(content) > 0 and len(seen) > 0:
                    shorter, longer = (content, seen) if len(content) <= len(seen) else (seen, content)
                    if shorter and shorter in longer:
                        is_dup = True
                        break
            if not is_dup:
                deduped.append(r)
                seen_content.append(content)
        return deduped
