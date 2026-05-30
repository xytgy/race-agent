from __future__ import annotations

from typing import Iterable, Protocol

import numpy as np


class LLMClient(Protocol):
    def chat_messages(self, messages: list[dict[str, str]], request_id: str = "-") -> str:
        ...

    def chat_stream(self, messages: list[dict[str, str]], request_id: str = "-"):
        ...


class PromptRenderer(Protocol):
    def render(self, template_name: str, **kwargs) -> str:
        ...


class EmbeddingClient(Protocol):
    mode: str

    def embed_text(self, text: str) -> np.ndarray:
        ...

    def embed_documents(self, texts: Iterable[str]) -> np.ndarray:
        ...


class VectorStore(Protocol):
    def search(
        self,
        question: str,
        top_k: int = 3,
        score_threshold: float | None = None,
    ) -> tuple[list[dict], str]:
        ...
