import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PyPDF2 import PdfReader

from app.config.settings import settings
from app.db.database import get_db
from app.utils.chunk import TextPage, chunk_pages


class DocumentService:
    SUPPORTED_TYPES = {"pdf", "md", "txt"}

    def __init__(self) -> None:
        self.upload_dir = Path(settings.data_dir) / "uploads"
        self.chunk_dir = Path(settings.data_dir) / "chunks"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_dir.mkdir(parents=True, exist_ok=True)

    def _extract_text(self, file_path: Path, file_type: str) -> str:
        return "\n\n".join(page.content for page in self._extract_pages(file_path, file_type))

    def _extract_pages(self, file_path: Path, file_type: str) -> list[TextPage]:
        if file_type in {"md", "txt"}:
            return [TextPage(content=file_path.read_text(encoding="utf-8", errors="ignore"))]
        if file_type == "pdf":
            reader = PdfReader(str(file_path))
            return [
                TextPage(content=page.extract_text() or "", page_no=idx)
                for idx, page in enumerate(reader.pages, start=1)
            ]
        raise ValueError(f"unsupported_file_type: {file_type}")

    def upload_and_process(self, file_name: str, content: bytes) -> dict:
        suffix = Path(file_name).suffix.lower().lstrip(".")
        if suffix not in self.SUPPORTED_TYPES:
            raise ValueError("only pdf/md/txt are supported in phase_3")

        # 文件内容魔数校验：PDF 文件必须以 %PDF 开头
        if suffix == "pdf":
            if not content or not content[:5].startswith(b"%PDF"):
                raise ValueError("文件内容与扩展名不匹配：PDF 文件必须以 %PDF 开头")

        document_id = uuid4().hex
        stored_name = f"{document_id}_{file_name}"
        file_path = self.upload_dir / stored_name
        file_path.write_bytes(content)

        created_at = datetime.utcnow().isoformat()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO documents(id, file_name, file_path, file_type, parse_status, chunk_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    file_name,
                    str(file_path),
                    suffix,
                    "PROCESSING",
                    0,
                    created_at,
                ),
            )

        try:
            pages = self._extract_pages(file_path, suffix)
            chunks = chunk_pages(pages, chunk_size=800, chunk_overlap=100)
            chunk_payload = []
            for chunk in chunks:
                chunk_payload.append(
                    {
                        "chunk_id": f"{document_id}_chunk_{chunk.chunk_index:04d}",
                        "document_id": document_id,
                        "source_file": file_name,
                        "file_type": suffix,
                        "chunk_index": chunk.chunk_index,
                        "total_chunks": len(chunks),
                        "content": chunk.content,
                        "page_no": chunk.page_no,
                        "section": chunk.section,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                    }
                )
            (self.chunk_dir / f"{document_id}.json").write_text(
                json.dumps(chunk_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            status = "READY"
            chunk_count = len(chunk_payload)
        except Exception:
            status = "FAILED"
            chunk_count = 0
            raise
        finally:
            with get_db() as conn:
                conn.execute(
                    "UPDATE documents SET parse_status=?, chunk_count=? WHERE id=?",
                    (status, chunk_count, document_id),
                )

        return {
            "document_id": document_id,
            "file_name": file_name,
            "file_type": suffix,
            "parse_status": status,
            "chunk_count": chunk_count,
        }
