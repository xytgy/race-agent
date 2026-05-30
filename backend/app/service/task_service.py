from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from app.config.settings import settings
from app.db.database import get_db
from app.service.agents import PlanningAgent, ResearchAgent, ReviewAgent
from app.service.contracts import LLMClient, PromptRenderer, VectorStore
from app.service.llm_service import LLMService
from app.service.prompt_service import PromptService
from app.service.task_workflow import TaskWorkflowState
from app.service.vector_store_factory import create_vector_store
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

    def __init__(
        self,
        llm_service: LLMClient | None = None,
        prompt_service: PromptRenderer | None = None,
        vector_service: VectorStore | None = None,
    ) -> None:
        self.llm_service = llm_service or LLMService()
        self.prompt_service = prompt_service or PromptService()
        self.vector_service = vector_service or create_vector_store()
        self.research_agent = ResearchAgent(self.vector_service)
        self.planning_agent = PlanningAgent(self.prompt_service, self.llm_service)
        self.review_agent = ReviewAgent()

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
            try:
                hours = float(item.get("estimated_hours", 4))
            except (ValueError, TypeError):
                hours = 4.0
            normalized.append(
                {
                    "title": str(item.get("title", "")).strip() or "未命名任务",
                    "description": str(item.get("description", "")).strip() or "无描述",
                    "task_type": str(item.get("task_type", "GENERAL")).upper(),
                    "priority": str(item.get("priority", "MEDIUM")).upper(),
                    "difficulty": str(item.get("difficulty", "MEDIUM")).upper(),
                    "estimated_hours": hours,
                    "dependency": str(item.get("dependency", "")).strip(),
                    "deliverable": str(item.get("deliverable", "")).strip(),
                    "status": "TODO",
                }
            )
        if not normalized:
            raise ValueError("empty_task_list")
        return normalized

    def _save_tasks(self, tasks: list[dict], refs: list[dict]) -> list[dict]:
        saved_tasks: list[dict] = []
        with get_db() as conn:
            for task in tasks:
                created_at = datetime.utcnow().isoformat()
                cursor = conn.execute(
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
                        created_at,
                    ),
                )
                task_id = cursor.lastrowid
                for ref in refs:
                    conn.execute(
                        """
                        INSERT INTO task_sources(task_id, document_id, chunk_id, source_file, page_no, section, score, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            task_id,
                            ref.get("document_id"),
                            ref.get("chunk_id"),
                            ref.get("source_file"),
                            ref.get("page_no"),
                            ref.get("section"),
                            ref.get("score"),
                            created_at,
                        ),
                    )
                saved_tasks.append({**task, "id": task_id, "created_at": created_at})
        return saved_tasks

    def _retrieve_context(self, state: TaskWorkflowState) -> None:
        self.research_agent.run(state)

    def _build_context(self, state: TaskWorkflowState) -> None:
        self.planning_agent.build_context(state)

    def _render_prompt(self, state: TaskWorkflowState) -> None:
        self.planning_agent.render_prompt(state)

    def _call_llm(self, state: TaskWorkflowState) -> None:
        self.planning_agent.call_llm(state)

    def _parse_tasks(self, state: TaskWorkflowState) -> None:
        state.parsed_payload = ensure_valid_json(state.raw_output)
        state.tasks = self._normalize_tasks(state.parsed_payload)
        state.mark("parse_tasks")

    def _review_tasks(self, state: TaskWorkflowState) -> None:
        self.review_agent.run(state)

    def _persist_tasks(self, state: TaskWorkflowState) -> None:
        state.saved_tasks = self._save_tasks(state.tasks, state.references)
        state.mark("persist_tasks")

    def _run_workflow(self, state: TaskWorkflowState) -> TaskWorkflowState:
        engine = settings.task_workflow_engine.lower().strip()
        if engine == "langgraph":
            return self._run_langgraph_workflow(state)
        if engine != "simple":
            raise ValueError(f"unsupported_task_workflow_engine: {settings.task_workflow_engine}")
        return self._run_simple_workflow(state)

    def _run_simple_workflow(self, state: TaskWorkflowState) -> TaskWorkflowState:
        self._retrieve_context(state)
        self._build_context(state)
        self._render_prompt(state)
        self._call_llm(state)
        self._parse_tasks(state)
        self._review_tasks(state)
        self._persist_tasks(state)
        return state

    def _run_langgraph_workflow(self, state: TaskWorkflowState) -> TaskWorkflowState:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError("langgraph_not_installed") from exc

        class GraphState(TypedDict):
            workflow: TaskWorkflowState

        def retrieve_context(graph_state: GraphState) -> GraphState:
            self._retrieve_context(graph_state["workflow"])
            return graph_state

        def build_context(graph_state: GraphState) -> GraphState:
            self._build_context(graph_state["workflow"])
            return graph_state

        def render_prompt(graph_state: GraphState) -> GraphState:
            self._render_prompt(graph_state["workflow"])
            return graph_state

        def call_llm(graph_state: GraphState) -> GraphState:
            self._call_llm(graph_state["workflow"])
            return graph_state

        def parse_tasks(graph_state: GraphState) -> GraphState:
            self._parse_tasks(graph_state["workflow"])
            return graph_state

        def review_tasks(graph_state: GraphState) -> GraphState:
            self._review_tasks(graph_state["workflow"])
            return graph_state

        def persist_tasks(graph_state: GraphState) -> GraphState:
            self._persist_tasks(graph_state["workflow"])
            return graph_state

        graph = StateGraph(GraphState)
        graph.add_node("retrieve_context", retrieve_context)
        graph.add_node("build_context", build_context)
        graph.add_node("render_prompt", render_prompt)
        graph.add_node("call_llm", call_llm)
        graph.add_node("parse_tasks", parse_tasks)
        graph.add_node("review_tasks", review_tasks)
        graph.add_node("persist_tasks", persist_tasks)
        graph.add_edge(START, "retrieve_context")
        graph.add_edge("retrieve_context", "build_context")
        graph.add_edge("build_context", "render_prompt")
        graph.add_edge("render_prompt", "call_llm")
        graph.add_edge("call_llm", "parse_tasks")
        graph.add_edge("parse_tasks", "review_tasks")
        graph.add_edge("review_tasks", "persist_tasks")
        graph.add_edge("persist_tasks", END)

        result = graph.compile().invoke({"workflow": state})
        return result["workflow"]

    def generate(self, query: str, context_hint: str, top_k: int, request_id: str) -> dict:
        state = TaskWorkflowState(
            query=query,
            context_hint=context_hint,
            top_k=top_k,
            request_id=request_id,
        )
        try:
            state = self._run_workflow(state)
        except Exception as exc:
            setattr(exc, "workflow_state", state)
            raise
        return {
            "tasks": state.saved_tasks,
            "references": state.references,
            "embedding_mode": state.embedding_mode,
            "workflow": {
                "engine": settings.task_workflow_engine.lower().strip(),
                "steps": state.steps,
                "review": state.review,
            },
        }
