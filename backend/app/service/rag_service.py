from app.service.llm_service import LLMService
from app.service.prompt_service import PromptService
from app.service.vector_service import VectorService


class RAGService:
    def __init__(self) -> None:
        self.vector_service = VectorService()
        self.prompt_service = PromptService()
        self.llm_service = LLMService()

    def _build_context(self, refs: list[dict]) -> str:
        """构建传递给 LLM 的参考上下文，使用完整内容而非截断的 preview。"""
        lines: list[str] = []
        for i, r in enumerate(refs, start=1):
            # 优先使用完整 content，若不存在则回退到 preview
            full_content = r.get("content") or r.get("preview", "")
            lines.append(
                f"[{i}] 来源: {r.get('source_file')} | 相关度: {r.get('score'):.4f}\n{full_content}"
            )
        return "\n\n---\n\n".join(lines)

    def query(self, question: str, top_k: int, request_id: str) -> dict:
        references, embedding_mode = self.vector_service.search(question, top_k=top_k)
        if not references:
            return {
                "answer": "资料中未找到明确依据。",
                "references": [],
                "embedding_mode": embedding_mode,
            }

        context = self._build_context(references)
        rendered_prompt = self.prompt_service.render(
            "rag.txt",
            question=question,
            context=context,
        )
        answer = self.llm_service.chat_messages(
            [
                {"role": "system", "content": "你是一个专业的大学生科技竞赛备赛助手。请优先基于参考资料回答，如果资料不足可以结合你的知识补充，但要明确区分信息来源。"},
                {"role": "user", "content": rendered_prompt},
            ],
            request_id=request_id,
        )
        return {
            "answer": answer,
            "references": references,
            "embedding_mode": embedding_mode,
        }

    def query_stream(self, question: str, top_k: int, request_id: str):
        """
        流式查询：先检索参考文献，然后以 SSE 流式输出 LLM 生成的每个 token。
        返回一个 (generator, references, embedding_mode) 元组。
        """
        references, embedding_mode = self.vector_service.search(question, top_k=top_k)
        if not references:
            # 无参考文献时直接返回一条完整消息
            def empty_gen():
                yield "资料中未找到明确依据。"
            return empty_gen(), [], embedding_mode

        context = self._build_context(references)
        rendered_prompt = self.prompt_service.render(
            "rag.txt",
            question=question,
            context=context,
        )
        messages = [
            {"role": "system", "content": "你是一个专业的大学生科技竞赛备赛助手。请优先基于参考资料回答，如果资料不足可以结合你的知识补充，但要明确区分信息来源。"},
            {"role": "user", "content": rendered_prompt},
        ]
        token_gen = self.llm_service.chat_stream(messages, request_id=request_id)
        return token_gen, references, embedding_mode
