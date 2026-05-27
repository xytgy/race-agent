from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import hmac
import time
from uuid import uuid4

from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.document import router as document_router
from app.api.rag import router as rag_router
from app.api.analysis import router as analysis_router
from app.api.log import router as log_router
from app.api.conversation import router as conversation_router
from app.config.settings import settings
from app.db.database import init_db
from app.service.log_service import LogService
from app.utils.logger import setup_logging, get_logger


setup_logging(settings.log_dir)
init_db()
logger = get_logger(__name__)

app = FastAPI(title="RaceAgent API")

# 延迟初始化 LogService，在 FastAPI startup 事件中创建
log_service: LogService | None = None


@app.on_event("startup")
async def startup_event():
    global log_service
    log_service = LogService()

    # 启动时确保 FAISS 索引与 chunks 目录一致
    try:
        from app.service.vector_service import VectorService
        vs = VectorService()
        vs.ensure_index()
        logger.info("faiss_index_startup_check_done")
    except Exception as exc:
        logger.warning("faiss_index_startup_check_failed", extra={"error": str(exc)})

# Middleware registration order (Starlette executes in REVERSE / LIFO order):
#
# Registration order (top to bottom) → Execution order (bottom to top):
#   1. access_log    → runs 4th (last)  — logs after request_id is set
#   2. request_id    → runs 3rd         — sets request.state.request_id
#   3. api_key       → runs 2nd         — checks auth after CORS headers
#   4. CORSMiddleware→ runs 1st (first) — handles OPTIONS preflight before auth


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    started = time.perf_counter()
    error_text = ""
    response = await call_next(request)
    latency_ms = int((time.perf_counter() - started) * 1000)
    request_id = getattr(request.state, "request_id", "-")
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    if response.status_code >= 400:
        error_text = f"http_{response.status_code}"
    if log_service is not None:
        try:
            log_service.write(
                request_id=request_id,
                endpoint=request.url.path,
                status=str(response.status_code),
                latency_ms=latency_ms,
                error=error_text,
            )
        except Exception as exc:
            logger.warning("log_write_failed", extra={"error": str(exc)})
    return response


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


# API Key 认证中间件
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # 健康检查和文档接口不需要认证
    if request.url.path in ("/docs", "/openapi.json", "/redoc", "/health"):
        return await call_next(request)
    # 如果服务端未配置 API_KEY，拒绝所有受保护请求
    if not settings.api_key:
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "API_KEY not configured on server", "data": {}, "request_id": ""},
        )
    # 检查 API Key
    api_key = request.headers.get("X-API-Key")
    if not api_key or not hmac.compare_digest(api_key, settings.api_key):
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "unauthorized", "data": {}, "request_id": ""},
        )
    return await call_next(request)


# CORSMiddleware — registered last so it executes first (LIFO),
# ensuring OPTIONS preflight requests receive CORS headers before api_key check.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health_router, tags=["health"])
app.include_router(chat_router, tags=["chat"])
app.include_router(document_router, tags=["document"])
app.include_router(rag_router, tags=["rag"])
app.include_router(analysis_router, tags=["analysis"])
app.include_router(log_router, tags=["log"])
app.include_router(conversation_router, tags=["conversation"])
