import os
import json
import time
from datetime import datetime
from html import escape

import requests
import streamlit as st
import streamlit_antd_components as sac


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "")
SHOW_ADMIN_PAGES = os.getenv("FRONTEND_SHOW_ADMIN_PAGES", "false").lower() == "true"
DEFAULT_TOP_K = 3

# ── Model Configuration ────────────────────────────────────────────────
DEFAULT_MODELS = [
    {"id": "mimo-v2.5-pro", "name": "mimo-v2.5-pro", "type": "内置"},
]


# ── Backend API functions (do not modify) ──────────────────────────────

def _error_message(message: str) -> str:
    mapping = {
        "llm_unauthorized": "模型服务认证失败，请检查 API Key。",
        "llm_rate_limited": "模型服务繁忙，请稍后重试。",
        "llm_timeout": "模型响应超时，请稍后重试。",
        "llm_upstream_error": "模型服务暂时不可用，请稍后再试。",
        "vector_empty": "当前暂无可用资料，请先上传文档。",
    }
    return mapping.get(message or "", "操作未完成，请稍后重试。")


def _api_headers() -> dict:
    """返回包含 API Key 的公共请求头"""
    return {"X-API-Key": API_KEY}


def _api_get(path: str, timeout: int = 15):
    return requests.get(f"{API_BASE_URL}{path}", headers=_api_headers(), timeout=timeout)


def _api_post_json(path: str, payload: dict, timeout: int = 120):
    return requests.post(f"{API_BASE_URL}{path}", json=payload, headers=_api_headers(), timeout=timeout)


def _api_delete(path: str, timeout: int = 15):
    return requests.delete(f"{API_BASE_URL}{path}", headers=_api_headers(), timeout=timeout)


def _load_conversations() -> dict:
    """从后端 API 加载会话列表，返回 {id: {title, created_at}, ...}"""
    try:
        resp = _api_get("/conversations")
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            items = payload.get("data", {}).get("items", [])
            return {item["id"]: item for item in items}
    except Exception:
        pass
    return {}


def _update_conversation_title(conv_id: str, title: str):
    """通过后端 API 更新会话标题"""
    try:
        _api_post_json(f"/conversations/{conv_id}/title", {"title": title})
    except Exception:
        pass


def _create_new_conversation() -> str:
    """通过后端 API 创建新会话"""
    try:
        resp = _api_post_json("/conversations", {})
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            conv_id = payload["data"]["id"]
            conv_title = payload["data"]["title"]
            st.session_state.conversations[conv_id] = {
                "title": conv_title,
                "created_at": payload["data"]["created_at"],
            }
            st.session_state.current_conv_id = conv_id
            return conv_id
    except Exception:
        pass
    # 后端不可用时的降级处理
    conv_id = f"conv_{int(time.time() * 1000)}"
    st.session_state.conversations[conv_id] = {
        "title": f"新对话 {len(st.session_state.conversations) + 1}",
        "created_at": datetime.now().isoformat(),
    }
    st.session_state.current_conv_id = conv_id
    return conv_id


def _delete_conversation(conv_id: str):
    """通过后端 API 删除会话"""
    try:
        _api_delete(f"/conversations/{conv_id}")
    except Exception:
        pass
    if conv_id in st.session_state.conversations:
        del st.session_state.conversations[conv_id]
    if st.session_state.conversations:
        st.session_state.current_conv_id = list(st.session_state.conversations.keys())[0]
    else:
        _create_new_conversation()


def _switch_conversation(conv_id: str):
    st.session_state.current_conv_id = conv_id


def _get_current_messages() -> list:
    """通过后端 API 获取当前会话消息，返回前端需要的格式"""
    conv_id = st.session_state.current_conv_id
    try:
        resp = _api_get(f"/conversations/{conv_id}/messages")
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            items = payload.get("data", {}).get("items", [])
            messages = []
            i = 0
            while i < len(items):
                if items[i]["role"] == "user":
                    user_content = items[i]["content"]
                    assistant_content = ""
                    assistant_meta = {}
                    # 检查下一条是否为 assistant 消息
                    if i + 1 < len(items) and items[i + 1]["role"] == "assistant":
                        raw_content = items[i + 1]["content"]
                        # 如果 content 已经是字典（API 已解析），直接使用
                        if isinstance(raw_content, dict):
                            assistant_meta = raw_content
                            assistant_content = raw_content.get("answer", "")
                        # 如果 content 是字符串，尝试解析为字典
                        elif isinstance(raw_content, str):
                            try:
                                parsed = json.loads(raw_content)
                                # 解析成功但结果不是字典时降级处理
                                if isinstance(parsed, dict):
                                    assistant_meta = parsed
                                    assistant_content = parsed.get("answer", "")
                                else:
                                    assistant_meta = {"kind": "qa", "answer": raw_content}
                                    assistant_content = raw_content
                            except (json.JSONDecodeError, TypeError):
                                assistant_meta = {"kind": "qa", "answer": raw_content}
                                assistant_content = raw_content
                        else:
                            # 其他类型（None 等）的降级处理
                            assistant_meta = {"kind": "qa", "answer": ""}
                            assistant_content = ""
                        i += 2
                    else:
                        i += 1
                    messages.append({
                        "user": user_content,
                        "assistant": assistant_meta if assistant_meta else {"kind": "qa", "answer": assistant_content},
                    })
                else:
                    i += 1
            return messages
    except Exception:
        pass
    return []


def _export_chat() -> str:
    """导出当前会话聊天记录为 Markdown"""
    title = st.session_state.conversations.get(
        st.session_state.current_conv_id, {}
    ).get("title", "新对话")
    lines = [f"# RaceAgent 聊天记录 - {title}\n"]
    for item in _get_current_messages():
        lines.append(f"## 用户\n{item['user']}\n")
        answer = item.get('assistant', {}).get('answer', '')
        lines.append(f"## AI\n{answer}\n")
        lines.append("---\n")
    return "\n".join(lines)


def _load_recent_docs() -> list[dict]:
    try:
        resp = _api_get("/documents/recent")
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return payload.get("data", {}).get("items", [])
    except Exception:
        pass
    return []


def _load_logs() -> list[dict]:
    try:
        resp = _api_get("/logs")
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return payload.get("data", {}).get("items", [])
    except Exception:
        pass
    return []


def _upload_document(uploaded_file) -> tuple[bool, str]:
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type or "application/octet-stream",
        )
    }
    try:
        resp = requests.post(f"{API_BASE_URL}/documents/upload", files=files, headers=_api_headers(), timeout=120)
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return True, "资料上传成功。"
        return False, _error_message(payload.get("message", ""))
    except Exception:
        return False, "上传失败，请稍后重试。"


# ── Custom CSS ─────────────────────────────────────────────────────────

def inject_custom_css():
    st.markdown(
        """
        <style>
        /* 全局 */
        .stApp { background: #ffffff; font-family: "SF Pro Display", "PingFang SC", sans-serif; }
        header[data-testid="stHeader"] { background: transparent !important; }

        /* 侧边栏 - 深色 */
        section[data-testid="stSidebar"] { background: #171717 !important; }
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] .stMarkdown li,
        section[data-testid="stSidebar"] .stMarkdown span,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stFileUploader label,
        section[data-testid="stSidebar"] .stAlert p,
        section[data-testid="stSidebar"] .stSpinner p { color: #ececec !important; }
        section[data-testid="stSidebar"] .stMarkdown h1,
        section[data-testid="stSidebar"] .stMarkdown h2,
        section[data-testid="stSidebar"] .stMarkdown h3 { color: #ececec !important; }

        /* 移除侧边栏顶部默认间距，让品牌紧贴左上角 */
        section[data-testid="stSidebar"] > div:first-child {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        section[data-testid="stSidebar"] > div:first-child > div:first-child {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }

        /* 侧边栏品牌 - 紧贴左上角 */
        .sidebar-brand { display: flex; align-items: center; gap: 12px; padding: 0; margin: 0; margin-bottom: 8px; }
        .sidebar-logo { width: 36px; height: 36px; border-radius: 50%; background: #10a37f; color: white; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; }
        .sidebar-brand-text h3 { font-size: 15px; font-weight: 600; color: #ececec !important; margin: 0; }
        .sidebar-brand-text p { font-size: 12px; color: #8e8e8e !important; margin: 0; }

        /* 侧边栏导航 */
        .sidebar-nav { padding: 8px 12px; }
        .sidebar-nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px; color: #ececec !important; font-size: 14px; cursor: pointer; transition: background 0.15s; }
        .sidebar-nav-item:hover { background: #212121; }
        .sidebar-nav-item.active { background: #212121; }

        /* 侧边栏文件上传 */
        [data-testid="stFileUploaderDropzone"] { background: transparent !important; border: 1px dashed #424242 !important; border-radius: 8px !important; min-height: 60px !important; }
        [data-testid="stFileUploaderDropzone"] button[kind="secondary"] { background: transparent !important; border: 1px solid #424242 !important; color: #ececec !important; border-radius: 8px !important; }

        /* 侧边栏文件列表 */
        .file-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-radius: 8px; color: #ececec !important; font-size: 13px; cursor: pointer; transition: background 0.15s; }
        .file-item:hover { background: #212121; }

        /* 侧边栏按钮 */
        section[data-testid="stSidebar"] .stButton > button { background: transparent !important; color: #ececec !important; border: 1px solid #424242 !important; border-radius: 8px !important; }
        section[data-testid="stSidebar"] .stButton > button:hover { background: #212121 !important; }

        /* 聊天区 - 居中 */
        .chat-container { max-width: 800px; margin: 0 auto; padding: 20px 24px; }

        /* 顶部栏 */
        .chat-header { position: sticky; top: 0; z-index: 999; display: flex; align-items: center; justify-content: space-between; padding: 12px 24px; background: rgba(255,255,255,0.95); backdrop-filter: blur(10px); border-bottom: 1px solid #f0f0f0; }
        .chat-header-title { font-size: 16px; font-weight: 600; color: #1a1a1a; }

        /* 消息 - 无气泡边框 */
        .user-message { display: flex; justify-content: flex-end; margin-bottom: 16px; }
        .user-bubble { max-width: 70%; background: #f0f4ff; color: #1a1a1a; border-radius: 16px; padding: 12px 16px; font-size: 15px; line-height: 1.6; }
        .assistant-message { display: flex; gap: 0; margin-bottom: 16px; }
        .assistant-content { max-width: 70%; font-size: 15px; line-height: 1.7; color: #1a1a1a; text-align: left; margin: 0; }

        /* 思考步骤 - 折叠 */
        .thinking-steps { background: #f8f9fa; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; border-left: 3px solid #10a37f; }
        .thinking-step { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; color: #666; }
        .thinking-check { color: #10a37f; font-weight: 700; }

        /* AI 回答卡片 - 无边框 */
        .answer-card { background: transparent; border: none; padding: 0; font-size: 15px; line-height: 1.7; color: #1a1a1a; }

        /* 引用来源 */
        .ref-section { margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
        .ref-item { font-size: 12px; color: #888; padding: 4px 0; }

        /* 欢迎区 */
        .welcome-section { text-align: center; padding: 80px 20px 40px; }
        .welcome-title { font-size: 28px; font-weight: 700; color: #1a1a1a; margin-bottom: 12px; }
        .welcome-subtitle { font-size: 15px; color: #666; }

        /* 输入框 */
        .stChatInput { border-radius: 24px !important; }
        .stChatInput textarea { border-radius: 24px !important; font-size: 15px !important; }

        /* 滚动条 */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #d0d0d0; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #b0b0b0; }

        /* 按钮 */
        .stButton > button { border-radius: 8px !important; font-size: 14px !important; }
        .stButton > button:hover { opacity: 0.85; }

        /* 用户卡片 - 固定左下角 */
        .fixed-user-card { position: fixed; bottom: 20px; left: 20px; background: #1a1a1a; color: #ececec; padding: 10px 16px; border-radius: 12px; z-index: 998; display: flex; align-items: center; gap: 10px; font-size: 13px; }

        /* 流式输出占位符 - 确保左对齐 */
        [data-testid="stMarkdownContainer"] > div > .assistant-content {
            text-align: left !important;
            margin-left: 0 !important;
            margin-right: auto !important;
        }

        /* Streamlit 容器内的 assistant-content 强制左对齐 */
        .stMarkdown .assistant-content,
        div[data-testid="stMarkdown"] .assistant-content {
            text-align: left !important;
            max-width: 70% !important;
        }

        /* status 组件 - 左对齐 */
        [data-testid="stStatus"] {
            text-align: left !important;
            align-items: flex-start !important;
        }
        [data-testid="stStatus"] > div {
            justify-content: flex-start !important;
        }

        section.main .block-container {
            padding-bottom: 140px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Session State ──────────────────────────────────────────────────────

def init_session_state():
    if "conversations" not in st.session_state:
        saved = _load_conversations()
        st.session_state.conversations = saved if saved else {}
    if "current_conv_id" not in st.session_state:
        if st.session_state.conversations:
            st.session_state.current_conv_id = list(st.session_state.conversations.keys())[0]
        else:
            _create_new_conversation()
    if "latest_docs" not in st.session_state:
        st.session_state.latest_docs = _load_recent_docs()
    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False
    # Model-related state
    if "available_models" not in st.session_state:
        st.session_state.available_models = DEFAULT_MODELS.copy()
    if "selected_model" not in st.session_state:
        st.session_state.selected_model = DEFAULT_MODELS[0]["id"]
    if "show_add_model_dialog" not in st.session_state:
        st.session_state.show_add_model_dialog = False


# ── Sidebar ────────────────────────────────────────────────────────────

def render_sidebar():
    # Brand
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-logo">RA</div>
            <div class="sidebar-brand-text">
                <h3>RaceAgent</h3>
                <p>竞赛 AI 助手</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # New session button
    if st.button("+ 新建会话", use_container_width=True, key="new_session_btn"):
        _create_new_conversation()
        st.rerun()

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

    # 会话列表
    for conv_id, conv in st.session_state.conversations.items():
        title = conv.get("title", "新对话")
        is_active = conv_id == st.session_state.current_conv_id
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            label = f"{'● ' if is_active else ''}{title}"
            if st.button(label, key=f"conv_{conv_id}", use_container_width=True):
                _switch_conversation(conv_id)
                st.rerun()
        with col2:
            if st.button("×", key=f"del_conv_{conv_id}"):
                _delete_conversation(conv_id)
                st.rerun()

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

    # Navigation
    st.markdown(
        """
        <div class="sidebar-nav">
            <div class="sidebar-nav-item active">
                <span>&#9633;</span>
                <span>Agent 工作台</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # File uploader
    uploaded = st.file_uploader(
        "上传资料",
        type=["pdf", "md", "txt"],
        label_visibility="collapsed",
        key="workspace_uploader",
    )
    if uploaded is not None and st.button("上传", use_container_width=True, key="upload_submit"):
        with st.spinner("正在处理资料..."):
            ok, message = _upload_document(uploaded)
        if ok:
            st.session_state.latest_docs = _load_recent_docs()
            st.success(message)
        else:
            st.error(message)

    # File list - simplified, no status/chunks
    docs = st.session_state.latest_docs
    if docs:
        for i, doc in enumerate(docs):
            col_file, col_del = st.columns([0.8, 0.2])
            with col_file:
                st.markdown(
                    f'<div class="file-item">{escape(str(doc.get("file_name", "未命名资料")))}</div>',
                    unsafe_allow_html=True,
                )
            with col_del:
                if st.button("x", key=f"delete_doc_{i}", help="删除此资料"):
                    doc_id = doc.get("id")
                    if doc_id:
                        try:
                            resp = _api_delete(f"/documents/{doc_id}")
                            if resp.status_code == 200:
                                # API 确认删除成功后，才修改本地状态
                                st.session_state.latest_docs = [
                                    d for d in st.session_state.latest_docs if d.get("id") != doc_id
                                ]
                        except Exception:
                            pass
                    st.rerun()

    # 刷新按钮
    if st.button("🔄 刷新资料列表", use_container_width=True, key="refresh_docs"):
        st.session_state.latest_docs = _load_recent_docs()
        st.rerun()

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

    # Spacer
    st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)

    # Fixed user card (bottom-left corner via CSS)
    st.markdown(
        """
        <div class="fixed-user-card">
            <div style="width:28px;height:28px;border-radius:50%;background:#10a37f;color:white;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;">U</div>
            <span>用户</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Chat Header ────────────────────────────────────────────────────────

def render_chat_header():
    col_left, col_right = st.columns([1, 0.15])
    with col_left:
        st.markdown(
            """
            <div class="chat-header">
                <div class="chat-header-title">RaceAgent</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_right:
        if st.button("清空聊天", key="clear_chat", use_container_width=True):
            conv_id = st.session_state.current_conv_id
            # 通过 API 清空消息并更新标题
            new_title = f"新对话 {len(st.session_state.conversations)}"
            try:
                _api_post_json(f"/conversations/{conv_id}/messages/replace", {"messages": []})
            except Exception:
                pass
            _update_conversation_title(conv_id, new_title)
            # 更新本地状态
            if conv_id in st.session_state.conversations:
                st.session_state.conversations[conv_id]["title"] = new_title
            st.rerun()


# ── Message Rendering ──────────────────────────────────────────────────

def render_message(message: dict):
    """Render a single chat message (user + assistant pair)."""
    # User bubble - right aligned, light blue background
    st.markdown(
        f'<div class="user-message"><div class="user-bubble">{escape(str(message["user"]))}</div></div>',
        unsafe_allow_html=True,
    )

    assistant = message.get("assistant", {})
    kind = assistant.get("kind", "")

    if kind == "loading":
        with st.spinner("正在分析中..."):
            pass

    elif kind == "error":
        st.error(assistant.get("answer", "发生未知错误"))

    else:
        # Thinking steps - collapsible expander
        steps = assistant.get("steps", [])
        if steps:
            with st.expander("思考步骤", expanded=True):
                steps_html = ""
                for step in steps:
                    steps_html += f"""
                    <div class="thinking-step">
                        <span class="thinking-check">&#10003;</span>
                        <span>{escape(str(step))}</span>
                    </div>
                    """
                st.markdown(steps_html, unsafe_allow_html=True)

        # Answer content - plain text, no border card
        # XSS 防护：对 LLM 输出进行转义处理
        answer_text = assistant.get("answer", "")
        if answer_text:
            st.markdown(f'<div class="answer-card">{escape(str(answer_text))}</div>', unsafe_allow_html=True)

        # References - small gray text at the end
        refs = assistant.get("references", [])
        if refs:
            refs_html = '<div class="ref-section">'
            refs_html += '<div style="font-size:12px;color:#888;margin-bottom:4px;font-weight:600;">引用来源</div>'
            for ref in refs:
                score = round(float(ref.get("score", 0)), 4)
                ref_file = escape(str(ref.get("source_file", "未命名资料")))
                refs_html += f'<div class="ref-item">{ref_file} (相似度 {score})</div>'
            refs_html += '</div>'
            st.markdown(refs_html, unsafe_allow_html=True)



# ── Chat Area ──────────────────────────────────────────────────────────

def render_chat_area():
    current_messages = _get_current_messages()
    if not current_messages:
        # ChatGPT-style centered welcome
        st.markdown(
            """
            <div class="welcome-section">
                <div class="welcome-title">RaceAgent</div>
                <div class="welcome-subtitle">竞赛 AI 助手 — 帮你分析竞赛、生成计划、检索资料</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Quick action cards - simpler style
        quick_prompts = [
            ("分析比赛", "帮我分析这个比赛的重点和评分关注点"),
            ("做 MVP 计划", "生成 7 天 MVP 开发计划"),
            ("梳理技术路线", "给我一套适合比赛的技术方案"),
        ]
        cols = st.columns(3)
        for col, (title, prompt) in zip(cols, quick_prompts):
            with col:
                if st.button(
                    f"{title}\n\n{prompt}",
                    key=f"quick_{title}",
                    use_container_width=True,
                ):
                    _handle_query(prompt)
                    st.rerun()
    else:
        for item in current_messages:
            render_message(item)


def _handle_query(text: str):
    """添加用户消息，执行查询，通过 SSE 流式展示回答，通过 API 更新助手回复"""

    # 1. 立即显示用户消息气泡（ChatGPT 风格：右对齐、浅蓝背景）
    st.markdown(
        f'<div class="user-message"><div class="user-bubble">{escape(text)}</div></div>',
        unsafe_allow_html=True,
    )

    # 2. 发送用户消息到后端数据库
    conv_id = st.session_state.current_conv_id
    try:
        _api_post_json(f"/conversations/{conv_id}/messages", {
            "role": "user",
            "content": text,
        })
    except Exception as e:
        print(f"[Handle] 保存用户消息失败: {type(e).__name__}: {e}")

    # 标题由后端 add_message 在第一条用户消息时自动更新，无需前端额外调用

    # 构建历史消息
    history = []
    for item in _get_current_messages()[-4:]:
        history.append({"role": "user", "content": item["user"][:2000]})
        if item["assistant"].get("answer") and item["assistant"].get("kind") != "loading":
            history.append({"role": "assistant", "content": item["assistant"]["answer"][:2000]})

    # 显示加载状态
    result = None
    full_answer = ""
    references: list[dict] = []

    # Streaming text placeholder - placed OUTSIDE and BEFORE the status block
    # to render at full width (not constrained by status widget layout).
    answer_placeholder = st.empty()

    with st.status("正在分析资料...", expanded=True) as status:
        status.write("正在检索相关资料...")

        # ── SSE 流式查询 ──
        try:
            print(f"[Handle] 正在发送 SSE 流式请求到 {API_BASE_URL}/rag/query ...")
            resp = requests.post(
                f"{API_BASE_URL}/rag/query",
                json={"question": text, "top_k": DEFAULT_TOP_K, "history": history, "stream": True, "model": st.session_state.selected_model},
                headers=_api_headers(),
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()
            print(f"[Handle] SSE 响应状态码: {resp.status_code}, content-type: {resp.headers.get('content-type', 'unknown')}")

            content_type = resp.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                # 正常 SSE 流式处理
                status.write("正在生成回答...")
                answer_tokens: list[str] = []

                for raw_line in resp.iter_lines(decode_unicode=True):
                    if raw_line is None:
                        continue
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue

                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")
                    if event_type == "meta":
                        references = event.get("references", [])
                    elif event_type == "token":
                        token = event.get("token", "")
                        if token:
                            answer_tokens.append(token)
                            # Update streaming placeholder to show live text
                            answer_placeholder.markdown(
                                f'<div class="assistant-content">{escape("".join(answer_tokens))}</div>',
                                unsafe_allow_html=True,
                            )

                resp.close()
                full_answer = "".join(answer_tokens)
                print(f"[Handle] SSE 流式读取完成，回答长度: {len(full_answer)} 字符")

                if full_answer:
                    result = {
                        "kind": "qa",
                        "answer": full_answer,
                        "references": references,
                        "steps": [
                            "分析问题：识别用户查询目标",
                            "检索资料：定位相关文档片段",
                            "整理回答：基于资料生成结果",
                        ],
                    }
                else:
                    # SSE 流为空，走 fallback
                    print("[Handle] SSE 流返回内容为空，降级到普通请求")
                    raise ValueError("SSE stream returned empty")

            else:
                # 后端未返回 SSE，走 fallback（JSON 响应）
                resp.close()
                print(f"[Handle] 后端未返回 SSE 格式 (content-type: {content_type})，降级到普通请求")
                raise ValueError("Non-SSE response")

        except Exception as e:
            print(f"[Handle] SSE 请求异常: {type(e).__name__}: {e}")
            # ── 降级：普通请求 ──
            try:
                print(f"[Handle] 正在发送普通请求到 {API_BASE_URL}/rag/query ...")
                resp = _api_post_json("/rag/query", {"question": text, "top_k": DEFAULT_TOP_K, "history": history, "model": st.session_state.selected_model})
                payload = resp.json()
                print(f"[Handle] 普通请求响应状态码: {resp.status_code}")
                if resp.status_code == 200 and payload.get("code") == 200:
                    data = payload.get("data", {})
                    full_answer = data.get("answer", "")
                    references = data.get("references", [])
                    result = {
                        "kind": "qa",
                        "answer": full_answer,
                        "references": references,
                        "steps": [
                            "分析问题：识别用户查询目标",
                            "检索资料：定位相关文档片段",
                            "整理回答：基于资料生成结果",
                        ],
                    }
                else:
                    print(f"[Handle] 普通请求失败，后端返回: {payload.get('message', 'unknown')}")
                    result = {"kind": "error", "answer": _error_message(payload.get("message", ""))}
            except Exception as e2:
                print(f"[Handle] 普通请求也失败了: {type(e2).__name__}: {e2}")
                result = {"kind": "error", "answer": "请求失败，请稍后重试。"}

        # 更新加载状态
        if result and result.get("kind") == "error":
            status.update(label="分析失败", state="error")
        else:
            status.update(label="分析完成", state="complete")

    # ── 在 status 容器外面渲染 AI 回答（左对齐，宽度限制在 80% 以内）──
    # Clear the streaming placeholder - final render goes after the status block
    answer_placeholder.empty()

    if result and result.get("kind") == "error":
        st.error(result.get("answer", "发生未知错误"))
    else:
        # XSS 防护：对 LLM 输出进行转义处理
        if full_answer:
            st.markdown(
                f'<div class="assistant-content">{escape(full_answer)}</div>',
                unsafe_allow_html=True,
            )

        # 引用来源也渲染在 status 容器外面
        if references:
            refs_html = '<div class="ref-section">'
            refs_html += '<div style="font-size:12px;color:#888;margin-bottom:4px;font-weight:600;">引用来源</div>'
            for ref in references:
                score = round(float(ref.get("score", 0)), 4)
                ref_file = escape(str(ref.get("source_file", "未命名资料")))
                refs_html += f'<div class="ref-item">{ref_file} (相似度 {score})</div>'
            refs_html += '</div>'
            st.markdown(refs_html, unsafe_allow_html=True)

    # 通过 API 发送助手回复
    if result is None:
        result = {"kind": "error", "answer": "操作未完成，请稍后重试。"}
    try:
        _api_post_json(f"/conversations/{conv_id}/messages", {
            "role": "assistant",
            "content": json.dumps(result, ensure_ascii=False),
        })
    except Exception as e:
        print(f"[Handle] 保存助手回复失败: {type(e).__name__}: {e}")


# ── Input Toolbar & Model Selector ────────────────────────────────────

def render_input_toolbar():
    """渲染输入框工具栏 - 紧贴 chat_input 上方"""
    # 工具栏布局：左(附件+代码) | 中(模型选择) | 右(语音+添加模型)
    col_left, col_center, col_right = st.columns([1, 3, 1])

    with col_left:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📎", key="toolbar_attach", help="附件"):
                pass
        with c2:
            if st.button("⌨", key="toolbar_code", help="代码"):
                pass

    with col_center:
        model_names = [m["name"] for m in st.session_state.available_models]
        current_index = 0
        for i, m in enumerate(st.session_state.available_models):
            if m["id"] == st.session_state.selected_model:
                current_index = i
                break
        selected = st.selectbox(
            "模型", model_names, index=current_index,
            key="model_selector_main", label_visibility="collapsed",
        )
        for m in st.session_state.available_models:
            if m["name"] == selected and st.session_state.selected_model != m["id"]:
                st.session_state.selected_model = m["id"]
                st.rerun()

    with col_right:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🎤", key="toolbar_voice", help="语音"):
                pass
        with c2:
            if st.button("➕", key="toolbar_add_model", help="添加模型"):
                st.session_state.show_add_model_dialog = True
                st.rerun()


def render_add_model_dialog():
    """渲染添加自定义模型弹窗"""
    if not st.session_state.get("show_add_model_dialog", False):
        return

    # 使用 st.container + form 实现弹窗效果
    with st.container():
        st.markdown("---")
        with st.form("add_model_form", clear_on_submit=True):
            st.markdown("### 添加自定义模型")

            model_name = st.text_input(
                "模型名称",
                placeholder="例如: GPT-4",
                help="给模型起一个友好的名称",
            )
            api_base = st.text_input(
                "API Base URL",
                placeholder="例如: https://api.openai.com/v1",
                help="模型 API 的基础地址",
            )
            api_key = st.text_input(
                "API Key",
                type="password",
                placeholder="输入 API Key",
                help="用于认证的 API 密钥",
            )
            model_id = st.text_input(
                "模型 ID",
                placeholder="例如: gpt-4-turbo",
                help="模型的实际标识符，用于 API 调用",
            )

            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.form_submit_button("保存", use_container_width=True, type="primary"):
                    if model_name and model_id:
                        new_model = {
                            "id": model_id,
                            "name": model_name,
                            "type": "自定义",
                            "api_base": api_base,
                            "api_key": api_key,
                        }
                        st.session_state.available_models.append(new_model)
                        st.session_state.selected_model = model_id
                        st.session_state.show_add_model_dialog = False
                        st.rerun()
                    else:
                        st.error("请填写模型名称和模型 ID")
            with col2:
                if st.form_submit_button("取消", use_container_width=True):
                    st.session_state.show_add_model_dialog = False
                    st.rerun()
            with col3:
                if st.form_submit_button("保存并继续添加", use_container_width=True):
                    if model_name and model_id:
                        new_model = {
                            "id": model_id,
                            "name": model_name,
                            "type": "自定义",
                            "api_base": api_base,
                            "api_key": api_key,
                        }
                        st.session_state.available_models.append(new_model)
                        st.session_state.selected_model = model_id
                        # 不关闭弹窗，继续添加
                        st.rerun()
                    else:
                        st.error("请填写模型名称和模型 ID")

        st.markdown("---")


# ── Main ───────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="RaceAgent",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_custom_css()
    init_session_state()

    with st.sidebar:
        render_sidebar()

    render_chat_header()
    render_chat_area()

    # 渲染添加模型弹窗（如果有）
    render_add_model_dialog()

    # 渲染输入框工具栏（在 chat_input 之前，通过 Streamlit 原生组件渲染）
    render_input_toolbar()

    # Chat input at the very bottom
    user_input = st.chat_input("输入消息，Enter 发送，Shift+Enter 换行...", max_chars=2000)
    if user_input:
        _handle_query(user_input)
        st.rerun()


if __name__ == "__main__":
    main()
else:
    main()
