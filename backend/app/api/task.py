from fastapi import APIRouter, Request

from app.model.request import TaskGenerateRequest
from app.model.response import ApiResponse
from app.db.database import get_db
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
def list_tasks(request: Request):
    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT
                  t.id,
                  t.title,
                  t.task_type,
                  t.priority,
                  t.difficulty,
                  t.estimated_hours,
                  t.status,
                  t.created_at,
                  COUNT(ts.id) AS source_count
                FROM tasks t
                LEFT JOIN task_sources ts ON ts.task_id = t.id
                GROUP BY t.id
                ORDER BY t.id DESC
                LIMIT 20
                """
            ).fetchall()
            items = [dict(r) for r in rows]
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


@router.get("/tasks/{task_id}", response_model=ApiResponse)
def get_task(task_id: int, request: Request):
    try:
        with get_db() as conn:
            task = conn.execute(
                """
                SELECT id, title, description, task_type, priority, difficulty,
                       estimated_hours, dependency, deliverable, status, created_at
                FROM tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
            if not task:
                return ApiResponse(
                    code=404,
                    message="task_not_found",
                    data={},
                    request_id=request.state.request_id,
                )
            sources = conn.execute(
                """
                SELECT document_id, chunk_id, source_file, page_no, section, score
                FROM task_sources
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        return ApiResponse(
            code=200,
            message="success",
            data={"task": dict(task), "sources": [dict(row) for row in sources]},
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("task_get_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=request.state.request_id,
        )


@router.put("/tasks/{task_id}/status", response_model=ApiResponse)
def update_task_status(task_id: int, request: Request, status: str = "DONE"):
    try:
        valid_statuses = ["TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED"]
        if status not in valid_statuses:
            return ApiResponse(
                code=400,
                message="invalid_status",
                data={},
                request_id=request.state.request_id,
            )
        with get_db() as conn:
            result = conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
            if result.rowcount == 0:
                return ApiResponse(
                    code=404,
                    message="task_not_found",
                    data={},
                    request_id=request.state.request_id,
                )
        return ApiResponse(
            code=200,
            message="success",
            data={"task_id": task_id, "status": status},
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
