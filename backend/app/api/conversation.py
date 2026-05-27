from datetime import datetime
from enum import Enum
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, constr

from app.db.database import get_db
from app.model.response import ApiResponse
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


# ── 请求模型 ──────────────────────────────────────────────────────

class MessageRole(str, Enum):
    """消息角色枚举，仅允许 user / assistant"""
    user = "user"
    assistant = "assistant"


class AddMessageRequest(BaseModel):
    """添加消息请求体"""
    role: MessageRole
    content: constr(max_length=100000)


class MessageItem(BaseModel):
    """replace_messages 中的单条消息"""
    role: MessageRole
    content: constr(max_length=100000)
    created_at: str | None = None


class ReplaceMessagesRequest(BaseModel):
    """替换消息请求体"""
    messages: list[MessageItem] = []

    def model_post_init(self, __context) -> None:
        if len(self.messages) > 100:
            raise ValueError("messages list cannot exceed 100 items")


class UpdateTitleRequest(BaseModel):
    """更新会话标题请求体"""
    title: constr(max_length=100) = "新对话"


@router.get("/conversations", response_model=ApiResponse)
def list_conversations(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """列出所有会话（分页）"""
    try:
        with get_db() as conn:
            # 查询总数
            total = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            # 使用 SQL JOIN 一次性查询会话及消息数量，避免 N+1 问题
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.created_at, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                GROUP BY c.id
                ORDER BY c.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            conversations = [dict(r) for r in rows]
        return ApiResponse(
            code=200,
            message="success",
            data={"items": conversations, "total": total, "limit": limit, "offset": offset},
            request_id=getattr(request.state, "request_id", "-"),
        )
    except Exception as exc:
        logger.error("list_conversations_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )


@router.post("/conversations", response_model=ApiResponse)
def create_conversation(request: Request):
    """创建新会话"""
    try:
        conv_id = f"conv_{uuid4().hex}"
        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
                (conv_id, "新对话", now),
            )
        return ApiResponse(
            code=200,
            message="success",
            data={"id": conv_id, "title": "新对话", "created_at": now},
            request_id=getattr(request.state, "request_id", "-"),
        )
    except Exception as exc:
        logger.error("create_conversation_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )


@router.delete("/conversations/{conv_id}", response_model=ApiResponse)
def delete_conversation(conv_id: str, request: Request):
    """删除会话及其所有消息"""
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        return ApiResponse(
            code=200,
            message="success",
            data={"deleted": conv_id},
            request_id=getattr(request.state, "request_id", "-"),
        )
    except Exception as exc:
        logger.error("delete_conversation_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )


@router.get("/conversations/{conv_id}/messages", response_model=ApiResponse)
def get_messages(
    conv_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """获取会话的消息列表（分页）"""
    try:
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conv_id,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC LIMIT ? OFFSET ?",
                (conv_id, limit, offset),
            ).fetchall()
            messages = [dict(r) for r in rows]
        return ApiResponse(
            code=200,
            message="success",
            data={"items": messages, "total": total, "limit": limit, "offset": offset},
            request_id=getattr(request.state, "request_id", "-"),
        )
    except Exception as exc:
        logger.error("get_messages_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )


@router.post("/conversations/{conv_id}/messages", response_model=ApiResponse)
def add_message(conv_id: str, request: Request, payload: AddMessageRequest):
    """添加消息到会话，第一条用户消息时自动从内容提取标题"""
    try:
        role = payload.role.value
        content = payload.content
        now = datetime.now().isoformat()

        with get_db() as conn:
            # 检查会话是否存在，不存在则创建
            row = conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
                    (conv_id, "新对话", now),
                )

            # 查询当前用户消息数量
            user_msg_count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND role = 'user'",
                (conv_id,),
            ).fetchone()[0]

            # 插入新消息
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conv_id, role, content, now),
            )

            # 仅在第一条用户消息时自动更新标题，避免重复调用和并发冲突
            if role == "user" and user_msg_count == 0:
                title = content[:30] + ("..." if len(content) > 30 else "")
                # 使用条件更新：仅当标题仍为默认值时才更新
                conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ? AND title = '新对话'",
                    (title, conv_id),
                )

        return ApiResponse(
            code=200,
            message="success",
            data={"conversation_id": conv_id},
            request_id=getattr(request.state, "request_id", "-"),
        )
    except Exception as exc:
        logger.error("add_message_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )


@router.post("/conversations/{conv_id}/messages/replace", response_model=ApiResponse)
def replace_messages(conv_id: str, request: Request, payload: ReplaceMessagesRequest):
    """替换会话的所有消息（用于清空或批量更新）"""
    try:
        messages = payload.messages
        now = datetime.now().isoformat()

        # Atomic: get_db() commits on normal exit and rolls back on exception.
        # Python's sqlite3 (default isolation_level) groups the DELETE + INSERTs
        # into a single implicit transaction, so a crash mid-loop loses nothing.
        with get_db() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            rows = [
                (conv_id, msg.role.value, msg.content, msg.created_at or now)
                for msg in messages
            ]
            if rows:
                conn.executemany(
                    "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    rows,
                )
        return ApiResponse(
            code=200,
            message="success",
            data={"conversation_id": conv_id, "count": len(messages)},
            request_id=getattr(request.state, "request_id", "-"),
        )
    except Exception as exc:
        logger.error("replace_messages_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )


@router.post("/conversations/{conv_id}/title", response_model=ApiResponse)
def update_conversation_title(conv_id: str, request: Request, payload: UpdateTitleRequest):
    """更新会话标题"""
    try:
        title = payload.title

        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (title, conv_id),
            )
        return ApiResponse(
            code=200,
            message="success",
            data={"conversation_id": conv_id, "title": title},
            request_id=getattr(request.state, "request_id", "-"),
        )
    except Exception as exc:
        logger.error("update_title_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )
