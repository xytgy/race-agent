from pydantic import BaseModel, constr
from typing import List, Literal, Optional


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]  # only allow user or assistant
    content: constr(max_length=2000)


class ChatRequest(BaseModel):
    message: constr(max_length=2000)
    history: Optional[List[ChatMessage]] = None


class RagQueryRequest(BaseModel):
    question: constr(max_length=2000)
    top_k: int = 3
    history: Optional[List[ChatMessage]] = None
    stream: bool = False


class AnalysisRequest(BaseModel):
    question: constr(max_length=2000)
    top_k: int = 3


class TaskGenerateRequest(BaseModel):
    query: constr(max_length=2000)
    context_hint: constr(max_length=2000) = ""
    top_k: int = 3
