from app.service.contracts import LLMClient, PromptRenderer, VectorStore
from app.service.llm_service import LLMService
from app.service.prompt_service import PromptService
from app.service.vector_store_factory import create_vector_store


class AnalysisService:
    def __init__(
        self,
        vector_service: VectorStore | None = None,
        prompt_service: PromptRenderer | None = None,
        llm_service: LLMClient | None = None,
    ) -> None:
        self.vector_service = vector_service or create_vector_store()
        self.prompt_service = prompt_service or PromptService()
        self.llm_service = llm_service or LLMService()

    def _build_context(self, refs: list[dict]) -> str:
        lines: list[str] = []
        for i, r in enumerate(refs, start=1):
            source_parts = [str(r.get("source_file") or "unknown")]
            if r.get("page_no") is not None:
                source_parts.append(f"page={r.get('page_no')}")
            if r.get("section"):
                source_parts.append(f"section={r.get('section')}")
            if r.get("chunk_id"):
                source_parts.append(f"chunk_id={r.get('chunk_id')}")
            lines.append(
                f"[{i}] source={' | '.join(source_parts)} score={r.get('score'):.4f}\n{r.get('preview','')}"
            )
        return "\n\n".join(lines)

    def analyze(self, question: str, top_k: int, request_id: str) -> dict:
        references, embedding_mode = self.vector_service.search(question, top_k=top_k)
        if not references:
            return {
                "answer": "资料中未找到与赛题相关的内容。",
                "references": [],
                "embedding_mode": embedding_mode,
            }

        context = self._build_context(references)
        rendered_prompt = self.prompt_service.render(
            "analysis.txt",
            question=question,
            context=context,
        )
        answer = self.llm_service.chat_messages(
            [
                {"role": "system", "content": "你是一位经验丰富的竞赛指导专家，擅长解读赛题和制定备赛策略。"},
                {"role": "user", "content": rendered_prompt},
            ],
            request_id=request_id,
        )
        return {
            "answer": answer,
            "references": references,
            "embedding_mode": embedding_mode,
        }
