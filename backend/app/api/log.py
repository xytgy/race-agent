from fastapi import APIRouter, Request

from app.model.response import ApiResponse
from app.service.log_service import LogService

router = APIRouter()
log_service = LogService()


@router.get("/logs", response_model=ApiResponse)
def get_logs(request: Request):
    data = {"items": log_service.latest(100)}
    return ApiResponse(
        code=200,
        message="success",
        data=data,
        request_id=request.state.request_id,
    )
