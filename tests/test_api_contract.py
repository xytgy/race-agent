import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="requires fastapi")

os.environ.setdefault("LLM_API_KEY", "test-llm-key")
os.environ.setdefault("LLM_BASE_URL", "http://example.test/v1")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("EMBEDDING_MODEL", "test-embedding")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="raceagent-test-"))
os.environ.setdefault("API_KEY", "test-api-key")

if HAS_FASTAPI:
    from app.main import app  # noqa: E402
    client = TestClient(app)
else:
    app = None
    client = None


def test_health_uses_uniform_response_contract():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"] == {"status": "ok"}
    assert body["request_id"]
    assert response.headers["X-Request-Id"] == body["request_id"]


def test_protected_endpoint_unauthorized_keeps_request_id_contract():
    response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == 401
    assert body["message"] == "unauthorized"
    assert body["data"] == {}
    assert body["request_id"]
    assert response.headers["X-Request-Id"] == body["request_id"]


def test_validation_errors_use_uniform_response_contract():
    response = client.post(
        "/rag/query",
        headers={"X-API-Key": "test-api-key"},
        json={"question": "hello", "top_k": 0},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 422
    assert body["message"] == "validation_error"
    assert body["request_id"]
    assert response.headers["X-Request-Id"] == body["request_id"]


def test_openapi_exposes_task_and_rag_debug_endpoints():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/tasks/generate" in paths
    assert "/rag/debug" in paths
