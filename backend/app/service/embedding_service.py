from __future__ import annotations

import hashlib
import re
import time
from typing import Any
from typing import Iterable

import numpy as np
import requests

from app.config.settings import settings
from app.utils.logger import get_logger


class EmbeddingService:
    def __init__(self) -> None:
        self._model = None
        self._model_attempted = False
        self._remote_attempted = False
        self._remote_disabled = False
        self._fallback_dim = 384
        self.fallback_version = "hash_char_ngram_v2"
        self.mode = "unknown"
        self.logger = get_logger(__name__)

    def _embedding_base_url(self) -> str:
        return (settings.embedding_base_url or settings.llm_base_url).rstrip("/")

    def _embedding_api_key(self) -> str:
        return settings.embedding_api_key or settings.llm_api_key

    def _should_try_remote(self) -> bool:
        provider = settings.embedding_provider.lower().strip()
        if provider in {"hash", "fallback_hash", "local"}:
            return False
        if provider in {"remote", "openai", "auto"}:
            return bool(self._embedding_base_url() and self._embedding_api_key())
        raise ValueError(f"unsupported_embedding_provider: {settings.embedding_provider}")

    def _normalize(self, vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms

    def _remote_embed_documents(self, texts: list[str]) -> np.ndarray | None:
        if self._remote_disabled or not self._should_try_remote():
            return None

        url = f"{self._embedding_base_url()}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._embedding_api_key()}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": settings.embedding_model,
            "input": texts,
        }

        last_error: Exception | None = None
        for attempt in range(settings.embedding_max_retries + 1):
            started = time.perf_counter()
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=settings.embedding_timeout_seconds,
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                resp.raise_for_status()
                data = resp.json()
                items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
                vectors = [item.get("embedding") for item in items]
                if len(vectors) != len(texts) or any(vector is None for vector in vectors):
                    raise ValueError("invalid_embedding_response")
                result = np.asarray(vectors, dtype=np.float32)
                self.mode = "remote"
                self.logger.info(
                    "embedding_remote_call",
                    extra={
                        "status_code": resp.status_code,
                        "latency_ms": latency_ms,
                        "attempt": attempt,
                        "model": settings.embedding_model,
                        "input_count": len(texts),
                        "dimension": int(result.shape[1]) if result.ndim == 2 else 0,
                    },
                )
                return self._normalize(result)
            except Exception as exc:
                last_error = exc
                self.logger.warning(
                    "embedding_remote_failed",
                    extra={
                        "attempt": attempt,
                        "error": str(exc),
                        "model": settings.embedding_model,
                    },
                )

        self._remote_attempted = True
        if settings.embedding_provider.lower().strip() in {"remote", "openai"}:
            raise RuntimeError(f"embedding_remote_failed: {last_error}")
        self._remote_disabled = True
        return None

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
        for token, weight in self._fallback_tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self._fallback_dim
            vec[idx] += weight
        norm = np.linalg.norm(vec) or 1.0
        return vec / norm

    def _fallback_tokens(self, text: str) -> list[tuple[str, float]]:
        normalized = text.lower()
        tokens: list[tuple[str, float]] = []

        for word in re.findall(r"[a-z0-9_]+", normalized):
            tokens.append((f"word:{word}", 2.0))

        cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
        for char in cjk_chars:
            tokens.append((f"cjk1:{char}", 0.4))
        for size, weight in ((2, 1.4), (3, 1.0)):
            for idx in range(0, max(len(cjk_chars) - size + 1, 0)):
                gram = "".join(cjk_chars[idx: idx + size])
                tokens.append((f"cjk{size}:{gram}", weight))

        compact = re.sub(r"\s+", "", normalized)
        for size, weight in ((2, 0.6), (3, 0.5)):
            for idx in range(0, max(len(compact) - size + 1, 0)):
                tokens.append((f"mix{size}:{compact[idx: idx + size]}", weight))

        if not tokens and normalized:
            tokens.append((f"text:{normalized}", 1.0))
        return tokens

    def embed_documents(self, texts: Iterable[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return []
        remote_vectors = self._remote_embed_documents(texts)
        if remote_vectors is not None:
            return remote_vectors
        model = self._load_model()
        if model is None:
            return np.vstack([self._fallback_embed_one(t) for t in texts])
        vectors = model.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]
