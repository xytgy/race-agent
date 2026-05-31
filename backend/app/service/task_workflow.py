from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskWorkflowState:
    query: str
    context_hint: str
    top_k: int
    request_id: str
    conversation_id: str = ""
    references: list[dict] = field(default_factory=list)
    embedding_mode: str = ""
    combined_context: str = ""
    prompt: str = ""
    raw_output: str = ""
    parsed_payload: Any = None
    tasks: list[dict] = field(default_factory=list)
    saved_tasks: list[dict] = field(default_factory=list)
    review: dict = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)

    def mark(self, step: str) -> None:
        self.steps.append(step)
