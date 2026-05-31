import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

try:
    import numpy  # noqa: F401
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="requires numpy and other backend dependencies")


def test_get_llm_service_returns_same_instance():
    from app.services import get_llm_service

    s1 = get_llm_service()
    s2 = get_llm_service()
    assert s1 is s2


def test_get_document_service_returns_same_instance():
    from app.services import get_document_service

    s1 = get_document_service()
    s2 = get_document_service()
    assert s1 is s2


def test_get_rag_service_returns_same_instance():
    from app.services import get_rag_service

    s1 = get_rag_service()
    s2 = get_rag_service()
    assert s1 is s2


def test_get_task_service_returns_same_instance():
    from app.services import get_task_service

    s1 = get_task_service()
    s2 = get_task_service()
    assert s1 is s2


def test_get_analysis_service_returns_same_instance():
    from app.services import get_analysis_service

    s1 = get_analysis_service()
    s2 = get_analysis_service()
    assert s1 is s2


def test_get_log_service_returns_same_instance():
    from app.services import get_log_service

    s1 = get_log_service()
    s2 = get_log_service()
    assert s1 is s2


def test_services_module_exports_all_getters():
    import app.services as svc

    assert hasattr(svc, "get_llm_service")
    assert hasattr(svc, "get_document_service")
    assert hasattr(svc, "get_rag_service")
    assert hasattr(svc, "get_task_service")
    assert hasattr(svc, "get_analysis_service")
    assert hasattr(svc, "get_log_service")
    assert hasattr(svc, "get_vector_service")
