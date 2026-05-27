from fastapi import APIRouter, Request

from app.model.response import ApiResponse

router = APIRouter()


@router.get("/health", response_model=ApiResponse)
def health(request: Request):
    return ApiResponse(
        code=200,
        message="success",
        data={"status": "ok"},
        request_id=request.state.request_id,
    )

