from __future__ import annotations

from collections.abc import Generator
from typing import Any

from app.service.contracts import LLMClient, PromptRenderer, VectorStore
from app.service.llm_service import LLMService
from app.service.prompt_service import PromptService
from app.service.vector_store_factory import create_vector_store


class RAGService:
    """RAG（检索增强生成）服务。

    负责将用户问题与向量数据库中的参考资料结合，通过 LLM 生成回答。
    支持普通查询和流式查询两种模式。
    """

    def __init__(
        self,
        vector_service: VectorStore | None = None,
        prompt_service: PromptRenderer | None = None,
        llm_service: LLMClient | None = None,
    ) -> None:
        self.vector_service = vector_service or create_vector_store()
        self.prompt_service = prompt_service or PromptService()
        self.llm_service = llm_service or LLMService()

    def _format_source_label(self, ref: dict[str, Any]) -> str:
        """将参考文献格式化为可读的来源标签。"""
        parts = [str(ref.get("source_file") or "unknown")]
        if ref.get("page_no") is not None:
            parts.append(f"page={ref.get('page_no')}")
        if ref.get("section"):
            parts.append(f"section={ref.get('section')}")
        if ref.get("chunk_id"):
            parts.append(f"chunk={ref.get('chunk_id')}")
        return " | ".join(parts)

    def _build_context(self, refs: list[dict[str, Any]]) -> str:
        """构建传递给 LLM 的参考上下文，使用完整内容而非截断的 preview。"""
        lines: list[str] = []
        for i, r in enumerate(refs, start=1):
            full_content = r.get("content") or r.get("preview", "")
            lines.append(
                f"[{i}] 来源: {self._format_source_label(r)} | 相关度: {r.get('score'):.4f}\n{full_content}"
            )
        return "\n\n---\n\n".join(lines)

    def retrieve(
        self,
        question: str,
        top_k: int,
        score_threshold: float | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """从向量数据库中检索与问题相关的参考文献。

        Args:
            question: 用户问题
            top_k: 返回的最大结果数
            score_threshold: 最低相关度阈值

        Returns:
            (参考文献列表, embedding模式名称)
        """
        return self.vector_service.search(
            question,
            top_k=top_k,
            score_threshold=score_threshold,
        )

    def query(
        self,
        question: str,
        top_k: int,
        request_id: str,
        score_threshold: float | None = None,
    ) -> dict[str, Any]:
        """执行完整的 RAG 查询：检索 + LLM 生成。

        Args:
            question: 用户问题
            top_k: 检索的最大结果数
            request_id: 请求追踪 ID
            score_threshold: 最低相关度阈值

        Returns:
            包含 answer、references、embedding_mode 的字典
        """
        references, embedding_mode = self.retrieve(
            question,
            top_k=top_k,
            score_threshold=score_threshold,
        )
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
                {"role": "system", "content": "你是大学生科技竞赛备赛助手。请优先基于参考资料回答，资料不足时可补充通用知识但需标注。输出使用 Markdown 格式，结构清晰、内容具体。"},
                {"role": "user", "content": rendered_prompt},
            ],
            request_id=request_id,
        )
        return {
            "answer": answer,
            "references": references,
            "embedding_mode": embedding_mode,
        }

    def query_stream(
        self,
        question: str,
        top_k: int,
        request_id: str,
        score_threshold: float | None = None,
        model: str | None = None,
    ) -> tuple[Generator[str, None, None], list[dict[str, Any]], str]:
        """流式 RAG 查询：先检索参考文献，然后以流式输出 LLM 生成的每个 token。

        Args:
            question: 用户问题
            top_k: 检索的最大结果数
            request_id: 请求追踪 ID
            score_threshold: 最低相关度阈值
            model: 可选的模型名称覆盖

        Returns:
            (token生成器, 参考文献列表, embedding模式名称)
        """
        references, embedding_mode = self.retrieve(
            question,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        if not references:
            def empty_gen() -> Generator[str, None, None]:
                yield "资料中未找到明确依据。"
            return empty_gen(), [], embedding_mode

        context = self._build_context(references)
        rendered_prompt = self.prompt_service.render(
            "rag.txt",
            question=question,
            context=context,
        )
        messages = [
            {"role": "system", "content": "你是大学生科技竞赛备赛助手。请优先基于参考资料回答，资料不足时可补充通用知识但需标注。输出使用 Markdown 格式，结构清晰、内容具体。"},
            {"role": "user", "content": rendered_prompt},
        ]
        token_gen = self.llm_service.chat_stream(messages, request_id=request_id, model=model)
        return token_gen, references, embedding_mode
