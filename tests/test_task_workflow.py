import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-llm-key")
os.environ.setdefault("LLM_BASE_URL", "http://example.test/v1")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("EMBEDDING_MODEL", "test-embedding")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="raceagent-test-"))
os.environ.setdefault("API_KEY", "test-api-key")

from app.service.task_service import TaskService  # noqa: E402


class FakeVectorStore:
    def search(self, question: str, top_k: int = 3, score_threshold=None):
        return (
            [
                {
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "source_file": "赛题.md",
                    "page_no": None,
                    "section": "评分标准",
                    "score": 0.95,
                    "preview": "需要完成原型系统和答辩材料",
                }
            ],
            "fake",
        )


class FakePromptService:
    def render(self, template_name: str, **kwargs) -> str:
        return f"{template_name}:{kwargs['context']}"


class FakeLLMService:
    def chat_messages(self, messages: list[dict[str, str]], request_id: str = "-") -> str:
        return """
        [
          {
            "title": "完成原型",
            "description": "基于赛题要求完成可演示原型",
            "task_type": "BACKEND",
            "priority": "HIGH",
            "difficulty": "MEDIUM",
            "estimated_hours": 8,
            "dependency": "",
            "deliverable": "原型系统"
          }
        ]
        """


class NoopSaveTaskService(TaskService):
    def _save_tasks(self, tasks: list[dict], refs: list[dict]) -> list[dict]:
        return [{**task, "id": idx, "created_at": "2026-05-30T00:00:00"} for idx, task in enumerate(tasks, start=1)]


def test_task_generation_runs_explicit_workflow_steps():
    service = NoopSaveTaskService(
        llm_service=FakeLLMService(),
        prompt_service=FakePromptService(),
        vector_service=FakeVectorStore(),
    )

    result = service.generate("怎么拆解任务", context_hint="优先做 MVP", top_k=3, request_id="req-1")

    assert result["workflow"]["steps"] == [
        "research_agent.retrieve_context",
        "planning_agent.build_context",
        "planning_agent.render_prompt",
        "planning_agent.call_llm",
        "parse_tasks",
        "review_agent.review_tasks",
        "persist_tasks",
    ]
    assert result["workflow"]["engine"] == "simple"
    assert result["workflow"]["review"]["passed"] is True
    assert result["embedding_mode"] == "fake"
    assert result["references"][0]["section"] == "评分标准"
    assert result["tasks"][0]["id"] == 1
    assert result["tasks"][0]["title"] == "完成原型"


def test_task_generation_runs_langgraph_workflow(monkeypatch):
    monkeypatch.setattr("app.service.task_service.settings.task_workflow_engine", "langgraph")
    service = NoopSaveTaskService(
        llm_service=FakeLLMService(),
        prompt_service=FakePromptService(),
        vector_service=FakeVectorStore(),
    )

    result = service.generate("怎么拆解任务", context_hint="优先做 MVP", top_k=3, request_id="req-1")

    assert result["workflow"]["engine"] == "langgraph"
    assert result["workflow"]["steps"] == [
        "research_agent.retrieve_context",
        "planning_agent.build_context",
        "planning_agent.render_prompt",
        "planning_agent.call_llm",
        "parse_tasks",
        "review_agent.review_tasks",
        "persist_tasks",
    ]
    assert result["workflow"]["review"]["passed"] is True
