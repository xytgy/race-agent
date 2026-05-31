from app.service.analysis_service import AnalysisService
from app.service.document_service import DocumentService
from app.service.llm_service import LLMService
from app.service.log_service import LogService
from app.service.rag_service import RAGService
from app.service.task_service import TaskService
from app.service.vector_store_factory import create_vector_store

_llm_service: LLMService | None = None
_document_service: DocumentService | None = None
_rag_service: RAGService | None = None
_task_service: TaskService | None = None
_analysis_service: AnalysisService | None = None
_log_service: LogService | None = None
_vector_service = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def get_document_service() -> DocumentService:
    global _document_service
    if _document_service is None:
        _document_service = DocumentService()
    return _document_service


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


def get_task_service() -> TaskService:
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service


def get_analysis_service() -> AnalysisService:
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = AnalysisService()
    return _analysis_service


def get_log_service() -> LogService:
    global _log_service
    if _log_service is None:
        _log_service = LogService()
    return _log_service


def get_vector_service():
    global _vector_service
    if _vector_service is None:
        _vector_service = create_vector_store()
    return _vector_service
