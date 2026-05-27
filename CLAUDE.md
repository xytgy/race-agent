# RaceAgent

## Architecture
- FastAPI backend (port 8000) with SQLite + FAISS vector store
- Streamlit frontend (port 8501)
- OpenAI-compatible LLM API (configurable via env vars)
- SSE streaming for real-time chat responses

## Key Files
- `backend/app/main.py` — FastAPI entry, middleware stack (CORS, request_id, access_log, api_key auth)
- `backend/app/api/rag.py` — RAG query endpoint with SSE streaming
- `backend/app/api/document.py` — Document upload/delete/list
- `backend/app/api/conversation.py` — Conversation CRUD
- `backend/app/service/vector_service.py` — FAISS index management with thread-safe caching
- `backend/app/service/llm_service.py` — LLM API calls (sync requests)
- `backend/app/service/rag_service.py` — RAG pipeline (embed -> search -> generate)
- `backend/app/model/request.py` — Pydantic request models
- `frontend/app.py` — Single-file Streamlit app (~1000 lines)

## Conventions
- API responses use `ApiResponse` model with `code`, `message`, `data`, `request_id`
- Backend uses `get_db()` context manager for SQLite (auto-commit/rollback)
- Frontend uses `st.session_state` for all persistent state
- HTML output uses `html.escape()` for XSS prevention
- Prompt templates use `string.Template` ($variable syntax), not str.format()

## Running
```bash
# Backend
cd backend && uvicorn app.main:app --port 8000

# Frontend
cd frontend && streamlit run app.py --port 8501
```

## Environment Variables
- `API_KEY` — Backend auth key (required)
- `LLM_API_KEY` — LLM service API key (required)
- `LLM_BASE_URL` — LLM API base URL (required)
- `LLM_MODEL` — Model name (default: gpt-4)
- `DATA_DIR` — Data storage directory (default: ./data)
