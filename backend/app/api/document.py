from fastapi import APIRouter, File, Request, UploadFile

from app.db.database import get_db
from app.model.response import ApiResponse
from app.service.document_service import DocumentService
from app.service.vector_store_factory import create_vector_store
from app.utils.logger import get_logger

router = APIRouter()
document_service = DocumentService()
vector_service = create_vector_store()
logger = get_logger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/documents/upload", response_model=ApiResponse)
async def upload_document(request: Request, file: UploadFile = File(...)):
    try:
        # Check size before reading to avoid OOM
        if file.size and file.size > MAX_FILE_SIZE:
            return ApiResponse(
                code=413,
                message="file_too_large",
                data={},
                request_id=request.state.request_id,
            )
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            return ApiResponse(
                code=413,
                message="file_too_large",
                data={},
                request_id=request.state.request_id,
            )
        result = document_service.upload_and_process(file.filename or "unknown", content)
        # 文件上传成功后，触发 FAISS 向量索引重建
        try:
            index_info = vector_service.rebuild_index()
            result["index_info"] = index_info
            logger.info("index_rebuilt_after_upload", extra={"document_id": result.get("document_id")})
        except Exception as idx_exc:
            logger.error("index_rebuild_failed", extra={"error": str(idx_exc)})
            result["index_info"] = {"error": str(idx_exc)}
        return ApiResponse(
            code=200,
            message="success",
            data=result,
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("document_upload_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=request.state.request_id,
        )


@router.get("/documents/recent", response_model=ApiResponse)
def recent_documents(request: Request):
    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, file_name, file_type, parse_status, chunk_count, created_at
                FROM documents
                ORDER BY created_at DESC
                """
            ).fetchall()
            data = [dict(r) for r in rows]
        return ApiResponse(
            code=200,
            message="success",
            data={"items": data},
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("recent_documents_failed", extra={"error": str(exc)})
        return ApiResponse(
            code=500,
            message="internal_error",
            data={},
            request_id=request.state.request_id,
        )


@router.delete("/documents/{doc_id}", response_model=ApiResponse)
def delete_document(doc_id: str, request: Request):
    # 校验 doc_id 格式：只允许 hex 字符串，长度 32
    import re
    if not re.match(r'^[0-9a-fA-F]{32}$', doc_id):
        return ApiResponse(
            code=400,
            message="invalid_doc_id",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )
    try:
        from pathlib import Path

        from app.config.settings import settings

        with get_db() as conn:
            # 先查文件信息
            row = conn.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return ApiResponse(code=404, message="document_not_found", data={}, request_id=request.state.request_id)
            # 删除数据库记录
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

        # 删除物理文件
        # 数据库中 file_path 可能是相对路径（如 "data/uploads/xxx"），
        # 需要基于 settings.data_dir 的父目录（项目根目录）解析为绝对路径
        raw_path = Path(row["file_path"])
        if raw_path.is_absolute():
            upload_file = raw_path
        else:
            upload_file = Path(settings.data_dir).parent / raw_path

        # Security: verify resolved path is within data directory
        upload_file = upload_file.resolve()
        data_dir = Path(settings.data_dir).resolve()
        if not str(upload_file).startswith(str(data_dir)):
            return ApiResponse(
                code=400,
                message="invalid_file_path",
                data={},
                request_id=request.state.request_id,
            )

        if upload_file.exists():
            upload_file.unlink()

        # 删除对应的 chunks 文件（文件名格式: {doc_id}.json）
        chunk_path = (Path(settings.data_dir) / "chunks" / f"{doc_id}.json").resolve()
        if not str(chunk_path).startswith(str(data_dir)):
            pass  # skip invalid path
        elif chunk_path.exists():
            chunk_path.unlink()

        # 重建 FAISS 索引
        try:
            if vector_service.has_chunks():
                vector_service.rebuild_index()
            else:
                # 所有文档已删除，清理索引文件
                index_path = vector_service.faiss_dir / "index.faiss"
                meta_path = vector_service.faiss_dir / "metadata.json"
                if index_path.exists():
                    index_path.unlink()
                if meta_path.exists():
                    meta_path.unlink()
        except Exception as rebuild_exc:
            logger.warning("faiss_rebuild_after_delete_failed", extra={"error": str(rebuild_exc)})

        return ApiResponse(code=200, message="success", data={"deleted": doc_id}, request_id=request.state.request_id)
    except Exception as exc:
        logger.error("document_delete_failed", extra={"error": str(exc)})
        return ApiResponse(code=500, message="internal_error", data={}, request_id=request.state.request_id)
