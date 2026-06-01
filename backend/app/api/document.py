import re
import json
from pathlib import Path

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from app.config.settings import settings
from app.db.database import get_db
from app.model.response import ApiResponse
from app.middleware.security import FileUploadGuard
from app.services import get_document_service, get_vector_service
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/documents/upload", response_model=ApiResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    project_id: str = Form(default=""),
):
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
        guard_error = FileUploadGuard.validate_upload(file.filename or "unknown", content)
        if guard_error:
            return ApiResponse(
                code=400 if guard_error != "file_too_large" else 413,
                message=guard_error,
                data={},
                request_id=request.state.request_id,
            )
        result = get_document_service().upload_and_process(file.filename or "unknown", content, project_id=project_id)
        # 文件上传成功后，触发 FAISS 向量索引重建
        try:
            index_info = get_vector_service().rebuild_index()
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


@router.post("/documents/url", response_model=ApiResponse)
def upload_from_url(request: Request):
    """从网页链接抓取内容并处理为文档"""
    try:
        import json as _json
        body = _json.loads(request._body.decode("utf-8")) if hasattr(request, "_body") else {}
    except Exception:
        body = {}
    # 从 query 或 body 中获取 url
    url = request.query_params.get("url") or body.get("url", "")
    if not url or not url.startswith(("http://", "https://")):
        return ApiResponse(
            code=400,
            message="invalid_url",
            data={},
            request_id=request.state.request_id,
        )
    try:
        result = get_document_service().fetch_url_and_process(url)
        try:
            get_vector_service().rebuild_index()
        except Exception:
            pass
        return ApiResponse(
            code=200,
            message="success",
            data=result,
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("url_fetch_failed", extra={"error": str(exc), "url": url})
        return ApiResponse(
            code=500,
            message=f"抓取失败: {str(exc)[:100]}",
            data={},
            request_id=request.state.request_id,
        )


@router.get("/documents/recent", response_model=ApiResponse)
def recent_documents(
    request: Request,
    project_id: str | None = Query(default=None),
    include_unassigned: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    try:
        with get_db() as conn:
            if project_id:
                if include_unassigned:
                    rows = conn.execute(
                        """
                        SELECT id, file_name, file_type, parse_status, chunk_count, tags, project_id, created_at
                        FROM documents
                        WHERE project_id = ? OR project_id = ''
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (project_id, limit, offset),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, file_name, file_type, parse_status, chunk_count, tags, project_id, created_at
                        FROM documents
                        WHERE project_id = ?
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (project_id, limit, offset),
                    ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, file_name, file_type, parse_status, chunk_count, tags, project_id, created_at
                    FROM documents
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            data = []
            for r in rows:
                d = dict(r)
                d["tags"] = [t.strip() for t in (d.get("tags") or "").split(",") if t.strip()]
                data.append(d)
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


@router.put("/documents/{doc_id}/project", response_model=ApiResponse)
async def update_document_project(doc_id: str, request: Request):
    if not re.match(r'^[0-9a-fA-F]{32}$', doc_id):
        return ApiResponse(code=400, message="invalid_doc_id", data={}, request_id=request.state.request_id)
    try:
        body = await request.json()
    except Exception:
        body = {}
    project_id = str(body.get("project_id", "")).strip()
    if project_id:
        if not re.match(r"^conv_[0-9a-fA-F]{32}$", project_id) and not re.match(r"^conv_\d+$", project_id):
            return ApiResponse(code=400, message="invalid_project_id", data={}, request_id=request.state.request_id)
    try:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return ApiResponse(code=404, message="not_found", data={}, request_id=request.state.request_id)
            conn.execute("UPDATE documents SET project_id = ? WHERE id = ?", (project_id, doc_id))
        return ApiResponse(
            code=200,
            message="success",
            data={"id": doc_id, "project_id": project_id},
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("update_document_project_failed", extra={"error": str(exc)})
        return ApiResponse(code=500, message="internal_error", data={}, request_id=request.state.request_id)


@router.post("/documents/assign_unassigned", response_model=ApiResponse)
async def assign_unassigned_documents(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    project_id = str(body.get("project_id", "")).strip()
    if not project_id:
        return ApiResponse(code=400, message="invalid_project_id", data={}, request_id=request.state.request_id)
    if not re.match(r"^conv_[0-9a-fA-F]{32}$", project_id) and not re.match(r"^conv_\d+$", project_id):
        return ApiResponse(code=400, message="invalid_project_id", data={}, request_id=request.state.request_id)
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE documents SET project_id = ? WHERE project_id = ''",
                (project_id,),
            )
            affected = cursor.rowcount
        return ApiResponse(
            code=200,
            message="success",
            data={"assigned": affected},
            request_id=request.state.request_id,
        )
    except Exception as exc:
        logger.error("assign_unassigned_documents_failed", extra={"error": str(exc)})
        return ApiResponse(code=500, message="internal_error", data={}, request_id=request.state.request_id)



@router.get("/documents/{doc_id}", response_model=ApiResponse)
def get_document_detail(doc_id: str, request: Request):
    """获取文档详情（含内容摘要和标签）"""
    if not re.match(r'^[0-9a-fA-F]{32}$', doc_id):
        return ApiResponse(code=400, message="invalid_doc_id", data={}, request_id=request.state.request_id)
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, file_name, file_type, parse_status, chunk_count, tags, summary, project_id, created_at FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            if not row:
                return ApiResponse(code=404, message="not_found", data={}, request_id=request.state.request_id)
            doc = dict(row)
            chunk_path = Path(settings.data_dir) / "chunks" / f"{doc_id}.json"
            preview_parts: list[str] = []
            if chunk_path.exists():
                try:
                    chunk_payload = json.loads(chunk_path.read_text(encoding="utf-8"))
                    if isinstance(chunk_payload, list):
                        for item in chunk_payload[:3]:
                            if isinstance(item, dict) and item.get("content"):
                                preview_parts.append(str(item["content"])[:200])
                except Exception:
                    preview_parts = []
            doc["preview"] = "\n\n".join(preview_parts)
            doc["tags"] = [t.strip() for t in (doc.get("tags") or "").split(",") if t.strip()]
        return ApiResponse(code=200, message="success", data=doc, request_id=request.state.request_id)
    except Exception as exc:
        logger.error("get_document_detail_failed", extra={"error": str(exc)})
        return ApiResponse(code=500, message="internal_error", data={}, request_id=request.state.request_id)


@router.put("/documents/{doc_id}/tags", response_model=ApiResponse)
def update_document_tags(doc_id: str, request: Request):
    """更新文档标签"""
    if not re.match(r'^[0-9a-fA-F]{32}$', doc_id):
        return ApiResponse(code=400, message="invalid_doc_id", data={}, request_id=request.state.request_id)
    try:
        import json as _json
        body = _json.loads(request._body.decode("utf-8")) if hasattr(request, "_body") else {}
    except Exception:
        body = {}
    tags = body.get("tags", [])
    if isinstance(tags, list):
        tags_str = ",".join(str(t).strip() for t in tags if t)
    else:
        tags_str = str(tags).strip()
    try:
        with get_db() as conn:
            conn.execute("UPDATE documents SET tags = ? WHERE id = ?", (tags_str, doc_id))
        return ApiResponse(code=200, message="success", data={"tags": tags_str}, request_id=request.state.request_id)
    except Exception as exc:
        logger.error("update_tags_failed", extra={"error": str(exc)})
        return ApiResponse(code=500, message="internal_error", data={}, request_id=request.state.request_id)


@router.delete("/documents/{doc_id}", response_model=ApiResponse)
def delete_document(doc_id: str, request: Request):
    if not re.match(r'^[0-9a-fA-F]{32}$', doc_id):
        return ApiResponse(
            code=400,
            message="invalid_doc_id",
            data={},
            request_id=getattr(request.state, "request_id", "-"),
        )
    try:
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
            vs = get_vector_service()
            if vs.has_chunks():
                vs.rebuild_index()
            else:
                # 所有文档已删除，清理索引文件
                index_path = vs.faiss_dir / "index.faiss"
                meta_path = vs.faiss_dir / "metadata.json"
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
