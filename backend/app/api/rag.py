import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.model.request import RagQueryRequest
from app.model.response import ApiResponse
from app.services import get_rag_service
from app.utils.errors import classify_llm_error, map_llm_error
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/rag/query", response_model=ApiResponse)
def rag_query(payload: RagQueryRequest, request: Request):
    try:
        # 如果有历史消息，将其格式化为上下文前缀
        if payload.history:
            context_parts = []
            for msg in payload.history[-4:]:  # 只取最近4轮
                role = "用户" if msg.role == "user" else "AI"
                context_parts.append(f"{role}: {msg.content}")
            history_context = "\n".join(context_parts)
            question = f"对话历史:\n{history_context}\n\n当前问题: {payload.question}"
        else:
            question = payload.question

        # 流式输出模式：返回 SSE (Server-Sent Events)
        if payload.stream:
            token_gen, references, embedding_mode = get_rag_service().query_stream(
                question,
                top_k=payload.top_k,
                request_id=request.state.request_id,
                score_threshold=payload.score_threshold,
                model=payload.model,
            )

            def event_generator():
                try:
                    # 先发送参考文献元信息，前端可据此渲染引用来源
                    yield f"data: {json.dumps({'type': 'meta', 'references': references, 'embedding_mode': embedding_mode}, ensure_ascii=False)}\n\n"
                    # 逐 token 发送
                    for token in token_gen:
                        yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"
                except GeneratorExit:
                    # 客户端断开连接，执行清理
                    logger.info("sse_client_disconnected", extra={"request_id": request.state.request_id})
                except Exception as exc:
                    # 流式生成过程中发生异常，向前端发送错误事件
                    error_type = classify_llm_error(str(exc))
                    logger.error("sse_stream_error", extra={"error_type": error_type, "error": str(exc)})
                    yield f"data: {json.dumps({'type': 'error', 'message': error_type}, ensure_ascii=False)}\n\n"
                finally:
                    yield "data: [DONE]\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # 普通模式：一次性返回完整结果
        result = get_rag_service().query(
            question,
            top_k=payload.top_k,
            request_id=request.state.request_id,
            score_threshold=payload.score_threshold,
        )
        return ApiResponse(
            code=200,
            message="success",
            data=result,
            request_id=request.state.request_id,
        )
    except Exception as exc:
        text = str(exc)
        if "llm_call_failed" in text or "llm_stream_failed" in text:
            code, message = map_llm_error(text)
        else:
            logger.error("rag_query_failed", extra={"error": str(exc)})
            code, message = 500, "internal_error"
        return ApiResponse(
            code=code,
            message=message,
            data={"error_type": message} if message.startswith("llm_") else {},
            request_id=request.state.request_id,
        )


@router.post("/rag/debug", response_model=ApiResponse)
def rag_debug(payload: RagQueryRequest, request: Request):
    try:
        references, embedding_mode = get_rag_service().retrieve(
            payload.question,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
        )
        return ApiResponse(
            code=200,
            message="success",
            data={
                "question": payload.question,
                "top_k": payload.top_k,
                "score_threshold": payload.score_threshold,
                "references": references,
                "embedding_mode": embedding_mode,
            },
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("rag_debug_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=request.state.request_id,
        )
