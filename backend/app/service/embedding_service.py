from __future__ import annotations

import hashlib
from typing import Iterable

import numpy as np

from app.config.settings import settings
from app.utils.logger import get_logger


class EmbeddingService:
    def __init__(self) -> None:
        self._model = None
        self._model_attempted = False
        self._fallback_dim = 384
        self.mode = "unknown"
        self.logger = get_logger(__name__)

    def _load_model(self):
        if self._model is not None:
            return self._model
        if self._model_attempted:
            return None
        self._model_attempted = True
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(settings.embedding_model)
            self.mode = "model"
            return self._model
        except Exception as exc:
            self.logger.warning(
                "embedding_fallback",
                extra={
                    "reason": str(exc),
                    "model": settings.embedding_model,
                    "hint": "请先下载模型到本地缓存，或检查网络连接",
                },
            )
            self._model = None
            self.mode = "fallback_hash"
            return None

    def _fallback_embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self._fallback_dim, dtype=np.float32)
        for token in text.split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self._fallback_dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec) or 1.0
        return vec / norm

    def embed_documents(self, texts: Iterable[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return []
        model = self._load_model()
        if model is None:
            return np.vstack([self._fallback_embed_one(t) for t in texts])
        vectors = model.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]
