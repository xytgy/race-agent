from fastapi import APIRouter, Request

from app.config.settings import settings
from app.model.response import ApiResponse
from app.services import get_llm_service
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.get("/diagnostics/llm", response_model=ApiResponse)
def diagnose_llm(request: Request):
    try:
        result = get_llm_service().diagnose(request_id=request.state.request_id)
        return ApiResponse(
            code=200 if result.get("ok") else 502,
            message="success" if result.get("ok") else result.get("error_type", "llm_upstream_error"),
            data=result,
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("llm_diagnostic_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=request.state.request_id,
        )
