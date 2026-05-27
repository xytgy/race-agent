from fastapi import APIRouter, Request

from app.model.request import AnalysisRequest
from app.model.response import ApiResponse
from app.service.analysis_service import AnalysisService
from app.utils.errors import map_llm_error
from app.utils.logger import get_logger

router = APIRouter()
analysis_service = AnalysisService()
logger = get_logger(__name__)


@router.post("/analysis/analyze", response_model=ApiResponse)
def analyze(payload: AnalysisRequest, request: Request):
    try:
        result = analysis_service.analyze(
            payload.question,
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
        else:
            logger.error("analysis_failed", extra={"error": str(exc)})
            code, message = 500, "internal_error"
        return ApiResponse(
            code=code,
            message=message,
            data={},
            request_id=request.state.request_id,
        )
