from pydantic import BaseModel, Field, constr
from typing import List, Literal, Optional


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]  # only allow user or assistant
    content: constr(max_length=2000)


class ChatRequest(BaseModel):
    message: constr(max_length=2000)
    history: Optional[List[ChatMessage]] = None


class RagQueryRequest(BaseModel):
    question: constr(max_length=2000)
    top_k: int = Field(default=3, ge=1, le=20)
    score_threshold: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    history: Optional[List[ChatMessage]] = None
    stream: bool = False
    model: Optional[str] = Field(default=None, max_length=128)


class AnalysisRequest(BaseModel):
    question: constr(max_length=2000)
    top_k: int = Field(default=3, ge=1, le=20)


class TaskGenerateRequest(BaseModel):
    query: constr(max_length=2000)
    context_hint: constr(max_length=2000) = ""
    top_k: int = Field(default=3, ge=1, le=20)
    conversation_id: Optional[str] = Field(default=None, max_length=128)


class TaskUpdateRequest(BaseModel):
    status: Optional[str] = Field(default=None, max_length=32)
    assignee: Optional[str] = Field(default=None, max_length=128)
    deadline: Optional[str] = Field(default=None, max_length=64)
