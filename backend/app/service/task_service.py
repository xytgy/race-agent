from __future__ import annotations

from datetime import datetime

from app.db.database import get_db
from app.service.llm_service import LLMService
from app.service.prompt_service import PromptService
from app.service.vector_service import VectorService
from app.utils.json_fix import ensure_valid_json


class TaskService:
    REQUIRED_FIELDS = {
        "title",
        "description",
        "task_type",
        "priority",
        "difficulty",
        "estimated_hours",
        "dependency",
        "deliverable",
    }
    def __init__(self) -> None:
        self.llm_service = LLMService()
        self.prompt_service = PromptService()
        self.vector_service = VectorService()

    def _normalize_tasks(self, payload) -> list[dict]:
        if isinstance(payload, dict):
            payload = payload.get("tasks", [])
        if not isinstance(payload, list):
            raise ValueError("task_payload_must_be_list")

        normalized = []
        for idx, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            missing = [f for f in self.REQUIRED_FIELDS if f not in item]
            if missing:
                raise ValueError(f"task[{idx}] missing_fields: {','.join(missing)}")
            normalized.append(
                {
                    "title": str(item.get("title", "")).strip() or "未命名任务",
                    "description": str(item.get("description", "")).strip() or "无描述",
                    "task_type": str(item.get("task_type", "GENERAL")).upper(),
                    "priority": str(item.get("priority", "MEDIUM")).upper(),
                    "difficulty": str(item.get("difficulty", "MEDIUM")).upper(),
                    "estimated_hours": float(item.get("estimated_hours", 4)),
                    "dependency": str(item.get("dependency", "")).strip(),
                    "deliverable": str(item.get("deliverable", "")).strip(),
                    "status": "TODO",
                }
            )
        if not normalized:
            raise ValueError("empty_task_list")
        return normalized

    def _save_tasks(self, tasks: list[dict]) -> None:
        with get_db() as conn:
            for task in tasks:
                conn.execute(
                    """
                    INSERT INTO tasks(title, description, task_type, priority, difficulty, estimated_hours, dependency, deliverable, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task["title"],
                        task["description"],
                        task["task_type"],
                        task["priority"],
                        task["difficulty"],
                        task["estimated_hours"],
                        task["dependency"],
                        task["deliverable"],
                        task["status"],
                        datetime.utcnow().isoformat(),
                    ),
                )

    def generate(self, query: str, context_hint: str, top_k: int, request_id: str) -> dict:
        refs, embedding_mode = self.vector_service.search(query, top_k=top_k)
        ref_context = "\n".join([f"- {r.get('preview','')}" for r in refs])
        combined_context = f"{context_hint}\n{ref_context}".strip() or query
        prompt = self.prompt_service.render("task.txt", context=combined_context)
        raw_output = self.llm_service.chat_messages(
            [
                {"role": "system", "content": "你是竞赛项目经理助手，请严格输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ],
            request_id=request_id,
        )
        parsed = ensure_valid_json(raw_output)
        tasks = self._normalize_tasks(parsed)
        self._save_tasks(tasks)
        return {"tasks": tasks, "references": refs, "embedding_mode": embedding_mode}
