# RaceAgent

面向大学生科技竞赛的 AI 助手，支持 RAG 知识检索、流式对话、文档管理与任务规划。

---

## 项目简介

RaceAgent 是一个端到端的竞赛辅助系统，通过 RAG（检索增强生成）技术将用户上传的竞赛相关文档（PDF / Markdown / TXT）转化为可检索的知识库，结合大语言模型为选手提供精准的问答、赛题分析和备赛建议。项目采用前后端分离架构，后端基于 FastAPI 提供 RESTful API，前端基于 Streamlit 构建交互式聊天界面。

---

## 功能特性

- **RAG 检索增强生成** — FAISS 向量索引 + HuggingFace Embeddings，上传文档后自动构建知识库，查询时返回带引用来源的回答
- **SSE 流式对话输出** — 基于 Server-Sent Events 的逐 token 流式响应，支持实时打字效果
- **文档上传与管理** — 支持 PDF / MD / TXT 格式，自动解析分块、向量化索引，支持上传与删除
- **任务规划生成** — 根据赛题描述自动生成结构化任务清单（含优先级、难度、预估工时）
- **赛题分析** — 对竞赛题目进行深度解读并给出备赛建议
- **会话管理** — 创建 / 切换 / 删除对话，自动提取标题，支持分页消息历史
- **多模型选择器** — 前端支持切换不同的 LLM 模型
- **深色侧边栏 + ChatGPT 风格聊天界面** — 基于 Streamlit Antd Components 构建的现代化 UI
- **API Key 鉴权** — 所有接口通过 `X-API-Key` 请求头进行身份验证
- **请求日志** — 自动生成访问日志，支持管理员页面查看

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端框架 | Streamlit |
| 数据库 | SQLite |
| 向量检索 | FAISS (faiss-cpu) |
| 文本嵌入 | 内置中文 hash fallback；可选远程 embedding 或本地 sentence-transformers |
| LLM 接口 | 兼容 OpenAI Chat Completions 格式的模型服务（通过环境变量配置） |
| PDF 解析 | PyPDF2 |
| 容器化 | Docker Compose |

---

## 快速开始

### 环境要求

- Python 3.10+
- pip
- Docker & Docker Compose（可选，用于容器化部署）

### 方式一：本地运行

**安装后端依赖**

```bash
cd backend
python -m venv .venv310
source .venv310/bin/activate   # Windows: .venv310\Scripts\activate
pip install -r requirements.txt
```

**安装前端依赖**

```bash
cd frontend
pip install -r requirements.txt
```

**配置环境变量**

复制 `.env.example` 为 `.env` 并填写实际配置：

```bash
cp .env.example .env
```

`.env` 文件内容示例：

```
LLM_API_KEY=your_llm_api_key
API_KEY=your_api_key
LLM_BASE_URL=https://api.example.com/v1
LLM_MODEL=gpt-4
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=2
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_PROVIDER=fallback_hash
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_TIMEOUT_SECONDS=30
EMBEDDING_MAX_RETRIES=1
VECTOR_STORE=faiss
TASK_WORKFLOW_ENGINE=simple
DATA_DIR=data
```

**启动后端**（端口 8000）

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**启动前端**（端口 8501）

```bash
cd frontend
streamlit run app.py --server.port 8501
```

启动后访问 `http://localhost:8501` 即可使用。

### 方式二：Docker Compose

```bash
# 构建并启动
docker compose up --build -d

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

**管理员模式**（显示日志页面）

```bash
export FRONTEND_SHOW_ADMIN_PAGES=true
docker compose up --build -d
```

---

## 项目结构

```
race-agent/
├── backend/
│   ├── app/
│   │   ├── api/              # API 路由
│   │   │   ├── health.py     # 健康检查
│   │   │   ├── chat.py       # 直接对话
│   │   │   ├── rag.py        # RAG 查询（支持 SSE 流式）
│   │   │   ├── document.py   # 文档上传与管理
│   │   │   ├── conversation.py  # 会话管理
│   │   │   ├── task.py       # 任务规划生成
│   │   │   ├── analysis.py   # 赛题分析
│   │   │   └── log.py        # 请求日志查询
│   │   ├── config/           # 配置模块
│   │   │   └── settings.py   # 环境变量加载
│   │   ├── db/               # 数据库
│   │   │   └── database.py   # SQLite 初始化与连接
│   │   ├── model/            # 数据模型（请求 / 响应）
│   │   ├── prompts/          # Prompt 模板
│   │   ├── service/          # 业务逻辑
│   │   │   ├── llm_service.py
│   │   │   ├── rag_service.py
│   │   │   ├── vector_service.py
│   │   │   ├── document_service.py
│   │   │   ├── task_service.py
│   │   │   ├── analysis_service.py
│   │   │   └── log_service.py
│   │   └── utils/            # 工具函数
│   │       ├── errors.py
│   │       └── logger.py
│   └── requirements.txt
├── frontend/
│   ├── app.py                # Streamlit 主入口
│   └── requirements.txt
├── data/                     # 数据目录（运行时生成）
│   ├── uploads/              # 上传的原始文档
│   ├── chunks/               # 文档分块 JSON
│   ├── faiss/                # FAISS 向量索引
│   └── logs/                 # 请求日志
├── .env.example              # 环境变量模板
├── docker-compose.yml        # Docker 编排
└── README.md
```

---

## API 接口

所有接口均需通过 `X-API-Key` 请求头进行鉴权（`/health`、`/docs`、`/openapi.json`、`/redoc` 除外）。

统一响应格式：

```json
{
  "code": 200,
  "message": "success",
  "data": {},
  "request_id": "uuid"
}
```

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 服务健康检查，返回 `{"status": "ok"}` |

### 直接对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 直接与 LLM 对话（不经过 RAG），支持历史消息 |

请求体：

```json
{
  "message": "你好",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

### RAG 查询

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rag/query` | RAG 检索增强查询，支持 SSE 流式输出 |

请求体：

```json
{
  "question": "什么是机器学习？",
  "top_k": 3,
  "stream": true,
  "history": []
}
```

流式响应格式（SSE）：

```
data: {"type": "meta", "references": [...], "embedding_mode": "..."}
data: {"type": "token", "token": "你"}
data: {"type": "token", "token": "好"}
data: [DONE]
```

### 文档管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/documents/upload` | 上传文档（PDF / MD / TXT），最大 10MB |
| GET | `/documents/recent` | 获取最近上传的文档列表 |
| DELETE | `/documents/{doc_id}` | 删除指定文档及其向量索引 |

上传方式（multipart/form-data）：

```bash
curl -X POST http://localhost:8000/documents/upload \
  -H "X-API-Key: your_key" \
  -F "file=@document.pdf"
```

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/conversations` | 获取会话列表（支持分页：`limit`、`offset`） |
| POST | `/conversations` | 创建新会话 |
| DELETE | `/conversations/{conv_id}` | 删除会话及其所有消息 |
| GET | `/conversations/{conv_id}/messages` | 获取会话消息列表（支持分页） |
| POST | `/conversations/{conv_id}/messages` | 添加消息到会话 |
| POST | `/conversations/{conv_id}/messages/replace` | 替换会话的所有消息（批量更新） |
| POST | `/conversations/{conv_id}/title` | 更新会话标题 |

### 任务规划

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks/generate` | 根据查询生成结构化任务清单 |
| GET | `/tasks` | 获取最近 20 条任务 |
| PUT | `/tasks/{task_id}/status` | 更新任务状态（TODO / IN_PROGRESS / DONE / CANCELLED） |

### 赛题分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/analysis/analyze` | 赛题深度解读与备赛建议 |

### 日志查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/logs` | 查询请求访问日志 |

### 交互式文档

启动后端后，访问以下地址查看 Swagger 交互式 API 文档：

```
http://localhost:8000/docs
```

---

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `LLM_API_KEY` | 是 | - | LLM API 密钥，用于访问语言模型服务 |
| `LLM_BASE_URL` | 是 | - | LLM API 基础 URL（需兼容 OpenAI 接口格式） |
| `LLM_MODEL` | 是 | - | 使用的语言模型名称 |
| `LLM_TIMEOUT_SECONDS` | 否 | `30` | API 请求超时时间（秒） |
| `LLM_MAX_RETRIES` | 否 | `2` | API 请求最大重试次数 |
| `EMBEDDING_MODEL` | 是 | - | 嵌入模型名称，用于文本向量化（默认 `BAAI/bge-small-zh-v1.5`） |
| `EMBEDDING_PROVIDER` | 否 | `fallback_hash` | 默认使用内置中文 hash embedding；可设为 `remote`、`local`、`auto` |
| `EMBEDDING_BASE_URL` | 否 | 复用 `LLM_BASE_URL` | 远程 Embedding API 基础 URL；不需要 OpenAI 账号，只要接口兼容 `/embeddings` |
| `EMBEDDING_API_KEY` | 否 | 复用 `LLM_API_KEY` | Embedding API 密钥 |
| `EMBEDDING_TIMEOUT_SECONDS` | 否 | `30` | Embedding 请求超时时间（秒） |
| `EMBEDDING_MAX_RETRIES` | 否 | `1` | Embedding 请求最大重试次数 |
| `VECTOR_STORE` | 否 | `faiss` | 向量库实现，当前支持 `faiss` |
| `TASK_WORKFLOW_ENGINE` | 否 | `simple` | 任务生成编排引擎，可设为 `simple` 或 `langgraph` |
| `DATA_DIR` | 是 | - | 数据存储目录 |
| `API_KEY` | 是 | - | 接口鉴权密钥，客户端需在 `X-API-Key` 请求头中携带 |
| `API_BASE_URL` | 否 | `http://localhost:8000` | 前端连接的后端地址（仅前端使用） |
| `FRONTEND_SHOW_ADMIN_PAGES` | 否 | `false` | 是否在前端显示管理员页面（如日志查看） |

默认后端镜像不安装 `sentence-transformers`，也不要求 OpenAI 账号，会使用内置中文 hash embedding，便于稳定构建和演示。若你有兼容 `/embeddings` 的远程服务，可以把 `EMBEDDING_PROVIDER` 设为 `remote`。若需要本地模型检索，可在后端环境额外安装：

```bash
pip install -r backend/requirements-embedding.txt
```

---

## 常见问题

**401 Unauthorized**

`API_KEY` 未配置或客户端请求头中的 `X-API-Key` 与服务端不匹配。请确认 `.env` 文件中 `API_KEY` 已正确设置。

**rag_query_failed: no_chunks_found**

查询时知识库中没有可用的文档分块。请先通过文档上传接口或前端上传至少一个文档。

**首次构建较慢**

Streamlit 及其依赖（pyarrow 等）体积较大，首次安装可能需要较长时间。Docker 构建时建议使用镜像缓存。

**嵌入模型下载**

首次运行时 HuggingFace 会自动下载 `BAAI/bge-small-zh-v1.5` 模型文件（约 100MB），请确保网络通畅。也可提前手动下载到本地缓存目录。

---

## License

MIT
