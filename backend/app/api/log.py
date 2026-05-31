from fastapi import APIRouter, Query, Request

from app.model.response import ApiResponse
from app.services import get_log_service

router = APIRouter()


@router.get("/logs", response_model=ApiResponse)
def get_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
):
    data = {"items": get_log_service().latest(limit)}
    return ApiResponse(
        code=200,
        message="success",
        data=data,
        request_id=request.state.request_id,
    )
