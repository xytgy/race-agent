# AGENTS.md

## 一、项目定位

RaceAgent 当前是一个面向大学生科技竞赛场景的 Python MVP 项目，现阶段目标很明确：

1. 上传比赛资料
2. 基于资料进行问答
3. 自动生成任务拆解
4. 展示引用来源
5. 保留基础日志

当前技术栈已经冻结为：

- 后端：FastAPI
- 前端：Streamlit
- 数据存储：SQLite + JSON 文件
- 检索：FAISS
- 部署：Docker Compose

当前阶段不要引入：

- 多 Agent 编排
- LangGraph / LangChain / LlamaIndex
- 微服务
- Kubernetes
- Milvus
- LoRA 微调
- 权限体系
- 多租户

一句话原则：

**先把可演示闭环做稳，再谈复杂能力。**

---

## 二、仓库结构

当前仓库主要结构如下：

```text
backend/
  app/
    api/          # 接口层
    service/      # 核心业务逻辑
    db/           # SQLite 初始化与连接
    model/        # 请求与响应模型
    prompts/      # Prompt 模板
    utils/        # 工具函数

frontend/
  app.py          # Streamlit 单文件入口

data/
  uploads/        # 原始上传文件
  chunks/         # 文本切片 JSON
  faiss/          # 向量索引与元数据
  sqlite/         # SQLite 数据库
  logs/           # 后端日志
  frontend/       # 前端持久化数据
```

---

## 三、当前接口范围

当前对外接口如下：

- `GET /health`
- `POST /chat`
- `POST /documents/upload`
- `GET /documents/recent`
- `POST /rag/query`
- `POST /tasks/generate`
- `GET /logs`

统一返回格式：

```json
{
  "code": 200,
  "message": "success",
  "data": {},
  "request_id": "..."
}
```

任何新增或修改接口时，都应尽量保持这个返回结构不变。

---

## 四、启动方式

### 1. 推荐方式

在项目根目录执行：

```bash
docker compose up --build -d
```

启动后访问：

- 前端：`http://localhost:8501`
- 后端：`http://localhost:8000`

### 2. 本地开发方式

后端：

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py --server.port=8501 --server.address=0.0.0.0
```

---

## 五、环境变量

`.env` 中当前必须有这些变量：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `EMBEDDING_MODEL`
- `DATA_DIR`

当前约定：

- 后端容器使用 `DATA_DIR=/app/data`
- 前端容器也使用 `DATA_DIR=/app/data`

这样可以保证前后端都能访问同一份 `data/` 目录。

---

## 六、前端说明

当前前端是单文件 Streamlit 应用：

- 入口文件：`frontend/app.py`

当前前端方向是：

**单页面工作台**

也就是说，不建议随意再拆回多页面模式，除非用户明确要求。

### 前端当前约束

当前前端已经做了这些约束：

- 左侧显示资料区
- 右侧显示问答工作区
- 聊天记录持久化到 `data/frontend/chat_history.json`
- 上传、问答、任务拆解都尽量在同一页完成

### 前端开发注意事项

在 Streamlit 中，下面几种东西很容易互相冲突：

1. 自定义 HTML 容器
2. `st.chat_message`
3. 固定定位 CSS
4. 手写 `<div>` 开闭标签包裹 Streamlit 组件

因此改前端时要遵守：

1. 优先用简单容器和列布局
2. 保持只有一个主要滚动区域
3. 不要在一个函数里打开 `<div>`，在另一个函数里关闭它，再把 Streamlit 组件夹在中间
4. 每次改布局后，都要实际重启并在浏览器里验证

一句话：

**前端优先稳定，不要为了“像某个参考图”把结构搞得不可控。**

---

## 七、后端说明

### 1. 文档处理

当前阶段只支持：

- `pdf`
- `md`
- `txt`

文档处理流程：

1. 文件保存到 `data/uploads/`
2. 提取文本
3. 做文本切片
4. 生成 `data/chunks/*.json`
5. 更新 SQLite 中的文档状态

### 2. RAG 检索

当前默认约束：

- 向量模型由 `EMBEDDING_MODEL` 决定
- 向量库只使用 FAISS
- 默认 `top_k = 3`

### 3. 任务拆解

`/tasks/generate` 当前链路是：

1. 读取 Prompt 模板
2. 检索上下文
3. 调用模型
4. 做 JSON 修复
5. 写入 SQLite

---

## 八、数据持久化规则

当前这些目录和文件属于有效业务数据，不能随意清空：

- `data/sqlite/raceagent.db`
- `data/chunks/*.json`
- `data/faiss/*`
- `data/frontend/chat_history.json`
- `data/uploads/*`

如果要改影响持久化的逻辑，必须优先考虑兼容已有数据。

禁止：

- 无提示删除用户数据
- 无说明重置数据库
- 无说明清空聊天记录

---

## 九、常见问题

### 1. 模型鉴权失败

现象：

- `llm_unauthorized`
- `401 Unauthorized`

原因：

- `LLM_API_KEY` 无效
- `.env` 还是占位值

### 2. 前端空白或布局错乱

常见原因：

- 固定高度 CSS 和 Streamlit 布局打架
- 不正确的 `overflow: hidden`
- 自定义 HTML 容器没有真正包住 Streamlit 组件

解决方向：

- 先简化结构
- 再做样式
- 不要继续叠加复杂 CSS

### 3. 聊天记录丢失

原因：

- 只存在 `st.session_state`
- 前端容器重启后状态丢失

当前解决方式：

- 持久化到 `data/frontend/chat_history.json`

### 4. 左侧资料没有全部显示

优先检查：

- `/documents/recent` 是否被限制数量
- 前端资料区是否被高度裁切
- 前端容器是否拿到了最新数据

---

## 十、协作修改规则

以后任何人或任何代理修改这个仓库时，默认遵守下面规则：

1. 不要破坏当前 MVP 范围
2. 优先做小改动、可回退改动
3. 没有明确要求时，不要引入新框架
4. 尽量不要随意改后端接口结构
5. 必须保留中文文件名支持
6. 必须保留统一返回格式
7. 必须保留 Docker 运行方式

---

## 十一、改动后检查清单

做完中等以上改动后，至少检查下面这些：

1. `docker compose up --build -d`
2. `GET /health` 返回正常
3. 前端能打开 `http://localhost:8501`
4. 上传资料仍可使用
5. 资料问答仍可使用
6. 任务拆解仍可生成
7. 左侧资料列表正常显示
8. `frontend/app.py` 没有语法错误

---

## 十二、推荐改动策略

### 遇到前端问题时

按这个顺序处理：

1. 先简化结构
2. 再修布局
3. 最后再做样式

不要一开始就继续叠复杂 CSS。

### 遇到后端问题时

按这个顺序处理：

1. 先看接口契约
2. 再看 service 逻辑
3. 最后再动数据结构

### 遇到“参考图还原”需求时

默认原则：

**优先做接近且稳定的版本，不强求 1:1 还原。**

因为当前前端是 Streamlit，不是真正的前端框架。

---

## 十三、当前最重要的目标

现阶段最重要的不是把页面做成最炫，而是保证这件事：

```text
上传资料
→ 提问
→ 给出基于资料的回答
→ 生成任务拆解
→ 可稳定演示
```

只要这个闭环稳，项目就是成功的 MVP。
