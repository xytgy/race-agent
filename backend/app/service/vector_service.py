from __future__ import annotations

import json
import threading
from pathlib import Path

import faiss
import numpy as np

from app.config.settings import settings
from app.service.embedding_service import EmbeddingService


class VectorService:
    _lock = threading.Lock()
    _cached_index: faiss.Index | None = None
    _cached_metadata: list[dict] | None = None
    _cache_valid = False

    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()
        self.faiss_dir = Path(settings.data_dir) / "faiss"
        self.chunks_dir = Path(settings.data_dir) / "chunks"
        self.faiss_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.faiss_dir / "index.faiss"
        self.meta_path = self.faiss_dir / "metadata.json"

    def _load_all_chunks(self) -> list[dict]:
        chunks: list[dict] = []
        for p in sorted(self.chunks_dir.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            chunks.extend(data)
        return chunks

    def has_chunks(self) -> bool:
        """检查是否存在任何 chunk 文件。"""
        return any(self.chunks_dir.glob("*.json"))

    def rebuild_index(self) -> dict:
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

    def search(
        self,
        question: str,
        top_k: int = 3,
        score_threshold: float | None = None,
    ) -> tuple[list[dict], str]:
        self.ensure_index()

        query = self.embedding_service.embed_text(question).astype(np.float32).reshape(1, -1)
        index, metadata = self._get_index_and_metadata()
        if query.shape[1] != index.d:
            self.rebuild_index()
            index, metadata = self._get_index_and_metadata()
            query = self.embedding_service.embed_text(question).astype(np.float32).reshape(1, -1)
        scores, ids = index.search(query, top_k)

        results: list[dict] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0 or idx >= len(metadata):
                continue
            score_value = float(score)
            if score_threshold is not None and score_value < score_threshold:
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
                    "score": score_value,
                    "content": full_content,
                    "preview": full_content[:200],
                }
            )
        return results, self.embedding_service.mode
