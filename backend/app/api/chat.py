from fastapi import APIRouter, Request

from app.model.request import ChatRequest
from app.model.response import ApiResponse
from app.services import get_llm_service
from app.utils.errors import map_llm_error
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat", response_model=ApiResponse)
def chat(payload: ChatRequest, request: Request):
    try:
        messages = [{"role": "system", "content": "你是 RaceAgent 竞赛 AI 助手，专注于大学生科技竞赛备赛。请全程使用中文，输出 Markdown 格式，结构清晰、内容具体。"}]
        # 添加历史消息
        if payload.history:
            for msg in payload.history:
                messages.append({"role": msg.role, "content": msg.content})
        # 添加当前消息
        messages.append({"role": "user", "content": payload.message})
        answer = get_llm_service().chat_messages(messages, request_id=request.state.request_id)
    except Exception as exc:
        text = str(exc)
        if "llm_call_failed" in text:
            code, message = map_llm_error(text)
        else:
            logger.error("chat_failed", extra={"error": str(exc)})
            code, message = 500, "internal_error"
        return ApiResponse(
            code=code,
            message=message,
            data={"error_type": message} if message.startswith("llm_") else {},
            request_id=request.state.request_id,
        )
    return ApiResponse(
        code=200,
        message="success",
        data={"answer": answer},
        request_id=request.state.request_id,
    )
