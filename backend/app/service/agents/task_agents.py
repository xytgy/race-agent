from __future__ import annotations

from app.service.contracts import LLMClient, PromptRenderer, VectorStore
from app.service.task_workflow import TaskWorkflowState


class ResearchAgent:
    def __init__(self, vector_service: VectorStore) -> None:
        self.vector_service = vector_service

    def run(self, state: TaskWorkflowState) -> None:
        refs, embedding_mode = self.vector_service.search(state.query, top_k=state.top_k)
        state.references = refs
        state.embedding_mode = embedding_mode
        state.mark("research_agent.retrieve_context")


class PlanningAgent:
    def __init__(self, prompt_service: PromptRenderer, llm_service: LLMClient) -> None:
        self.prompt_service = prompt_service
        self.llm_service = llm_service

    def build_context(self, state: TaskWorkflowState) -> None:
        ref_lines = []
        for ref in state.references:
            source_parts = [str(ref.get("source_file") or "unknown")]
            if ref.get("page_no") is not None:
                source_parts.append(f"page={ref.get('page_no')}")
            if ref.get("section"):
                source_parts.append(f"section={ref.get('section')}")
            preview = ref.get("preview", "")
            ref_lines.append(f"- 来源: {' | '.join(source_parts)}\n  内容: {preview}")
        ref_context = "\n".join(ref_lines)
        state.combined_context = f"{state.context_hint}\n{ref_context}".strip() or state.query
        state.mark("planning_agent.build_context")

    def render_prompt(self, state: TaskWorkflowState) -> None:
        state.prompt = self.prompt_service.render("task.txt", context=state.combined_context)
        state.mark("planning_agent.render_prompt")

    def call_llm(self, state: TaskWorkflowState) -> None:
        state.raw_output = self.llm_service.chat_messages(
            [
                {"role": "system", "content": "你是竞赛项目经理助手，请严格输出合法 JSON。"},
                {"role": "user", "content": state.prompt},
            ],
            request_id=state.request_id,
        )
        state.mark("planning_agent.call_llm")


class ReviewAgent:
    def run(self, state: TaskWorkflowState) -> None:
        issues = []
        for idx, task in enumerate(state.tasks, start=1):
            if task.get("estimated_hours", 0) <= 0:
                issues.append({"task_index": idx, "message": "estimated_hours_must_be_positive"})
            if not task.get("deliverable"):
                issues.append({"task_index": idx, "message": "deliverable_required"})
        state.review = {
            "passed": not issues,
            "issues": issues,
            "source_count": len(state.references),
        }
        state.mark("review_agent.review_tasks")
