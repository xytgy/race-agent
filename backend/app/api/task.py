from fastapi import APIRouter, Query, Request

from app.model.request import TaskGenerateRequest, TaskUpdateRequest
from app.model.response import ApiResponse
from app.service.task_service import TaskService
from app.utils.errors import map_llm_error
from app.utils.logger import get_logger

router = APIRouter()
task_service = TaskService()
logger = get_logger(__name__)


@router.post("/tasks/generate", response_model=ApiResponse)
def generate_tasks(payload: TaskGenerateRequest, request: Request):
    try:
        result = task_service.generate(
            query=payload.query,
            context_hint=payload.context_hint,
            top_k=payload.top_k,
            request_id=request.state.request_id,
            conversation_id=payload.conversation_id or "",
        )
        return ApiResponse(
            code=200,
            message="success",
            data=result,
            request_id=request.state.request_id,
        )
    except Exception as exc:
        text = str(exc)
        if "llm_call_failed" in text:
            code, message = map_llm_error(text)
            state = getattr(exc, "workflow_state", None)
            data = {
                "error_type": message,
                "workflow": {
                    "steps": getattr(state, "steps", []),
                    "failed_step": "planning_agent.call_llm",
                },
            }
        else:
            logger.error("task_generate_failed", extra={"error": str(exc)})
            code, message = 500, "internal_error"
            data = {}
        return ApiResponse(
            code=code,
            message=message,
            data=data,
            request_id=request.state.request_id,
        )


@router.get("/tasks", response_model=ApiResponse)
def list_tasks(
    request: Request,
    conversation_id: str | None = Query(default=None),
):
    try:
        if conversation_id:
            items = task_service.list_by_conversation(conversation_id)
        else:
            items = []
        return ApiResponse(
            code=200,
            message="success",
            data={"items": items},
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("task_list_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=request.state.request_id,
        )


@router.put("/tasks/{task_id}", response_model=ApiResponse)
def update_task(
    task_id: int,
    payload: TaskUpdateRequest,
    request: Request,
):
    try:
        updated = task_service.update_task(
            task_id=task_id,
            status=payload.status,
            assignee=payload.assignee,
            deadline=payload.deadline,
        )
        if updated is None:
            return ApiResponse(
                code=404,
                message="task_not_found",
                data={},
                request_id=request.state.request_id,
            )
        return ApiResponse(
            code=200,
            message="success",
            data=updated,
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("task_update_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=request.state.request_id,
        )


@router.delete("/tasks/{task_id}", response_model=ApiResponse)
def delete_task(task_id: int, request: Request):
    try:
        deleted = task_service.delete_task(task_id)
        if not deleted:
            return ApiResponse(
                code=404,
                message="task_not_found",
                data={},
                request_id=request.state.request_id,
            )
        return ApiResponse(
            code=200,
            message="success",
            data={"task_id": task_id},
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("task_delete_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=request.state.request_id,
        )
