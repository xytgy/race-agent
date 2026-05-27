# RaceAgent MVP

## Stack
- FastAPI
- Streamlit
- SQLite
- FAISS
- Docker Compose

## Current Scope
- `GET /health`
- `POST /chat` (real OpenAI-compatible call; requires valid API key)
- `POST /documents/upload` (`pdf/md/txt`)
- `POST /rag/query` (FAISS topK + `answer/references`)
- `POST /tasks/generate` (task JSON + repair + SQLite save)
- `POST /analysis/analyze` (赛题解读 + 备赛建议)
- `GET /logs`
- Unified response format: `{code, message, data, request_id}`
- Request logs in `data/logs/app.log`

## Local Run
### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py --server.port=8501
```

## Docker Run
```bash
docker compose up --build
```

### 普通模式（推荐演示）
```bash
docker compose up --build -d
```

### 管理员模式（显示日志页）
```bash
export FRONTEND_SHOW_ADMIN_PAGES=true
docker compose up --build -d frontend
```

## Env Required
Copy [.env.example](.env.example) to `.env` and fill in your API key:
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `EMBEDDING_MODEL`
- `DATA_DIR`

## Demo Checklist
1. `docker compose up --build -d`
2. Open `http://localhost:8501`
3. Upload one txt/md/pdf in sidebar
4. Chat with AI and verify RAG answers with references
5. Use quick cards to generate task plans
6. Call `/analysis/analyze` for competition analysis
7. Check health: `GET http://localhost:8000/health`

## Common Issues
- `401 Unauthorized`: `LLM_API_KEY` invalid or missing.
- `rag_query_failed: no_chunks_found`: upload document first.
- slow first build: frontend installs heavy dependencies (`streamlit/pyarrow`).

## Quick Check
1. `GET http://localhost:8000/health`
2. Open Streamlit `http://localhost:8501`
3. Use `Chat` page and send a message
