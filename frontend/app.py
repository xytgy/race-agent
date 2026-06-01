import os
import json
import time
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st

from doc_filters import compute_doc_filter_state, filter_docs


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "")
SHOW_ADMIN_PAGES = os.getenv("FRONTEND_SHOW_ADMIN_PAGES", "false").lower() == "true"
DEFAULT_TOP_K = 3

# ── Model Configuration ────────────────────────────────────────────────
DEFAULT_MODELS = [
    {"id": "mimo-v2.5-pro", "name": "mimo-v2.5-pro", "type": "内置"},
    {"id": "mimo-v2-flash", "name": "mimo-v2-flash", "type": "内置"},
    {"id": "deepseek-v3", "name": "DeepSeek V3", "type": "内置"},
]


# ── Backend API functions (do not modify) ──────────────────────────────

def _error_message(message: str) -> str:
    mapping = {
        "llm_unauthorized": "模型服务认证失败，请检查 LLM_API_KEY。",
        "llm_rate_limited": "模型服务请求过于频繁，请稍后重试。",
        "llm_timeout": "模型响应超时，请稍后重试。",
        "llm_connect_timeout": "无法连接模型服务，请检查 LLM_BASE_URL 是否正确。",
        "llm_read_timeout": "模型生成响应超时，请稍后重试或调大超时时间。",
        "llm_ssl_error": "模型服务 SSL 连接失败，请检查网络代理或证书配置。",
        "llm_bad_gateway": "模型服务网关异常，请稍后重试。",
        "llm_connection_error": "无法连接模型服务，请检查 LLM_BASE_URL。",
        "llm_invalid_response": "模型服务返回格式异常，请确认接口兼容 Chat Completions。",
        "llm_forbidden": "模型服务拒绝访问，请检查 API Key 权限。",
        "llm_upstream_error": "模型服务暂时不可用，请稍后再试。",
        "llm_call_failed": "模型调用失败，请稍后重试。",
        "llm_stream_failed": "模型流式输出中断，请稍后重试。",
        "vector_empty": "当前暂无可用资料，请先上传文档后再提问。",
        "unauthorized": "接口鉴权失败，请检查前端 API_KEY 配置。",
        "internal_error": "后端处理失败，请查看后端日志。",
        "validation_error": "请求参数有误，请检查输入内容。",
        "rag_query_failed": "资料检索失败，请稍后重试。",
    }
    return mapping.get(message or "", f"操作未完成（{message}），请稍后重试。")


def _llm_diagnostics() -> tuple[bool, dict | str]:
    try:
        resp = _api_get("/diagnostics/llm", timeout=60)
        payload = resp.json()
        data = payload.get("data", {})
        if payload.get("code") == 200:
            return True, data
        return False, data or _error_message(payload.get("message", ""))
    except Exception as exc:
        return False, f"诊断失败：{exc}"


def _api_headers() -> dict:
    """返回包含 API Key 的公共请求头"""
    return {"X-API-Key": API_KEY}


def _api_get(path: str, timeout: int = 15):
    return requests.get(f"{API_BASE_URL}{path}", headers=_api_headers(), timeout=timeout)


def _api_post_json(path: str, payload: dict, timeout: int = 120):
    return requests.post(f"{API_BASE_URL}{path}", json=payload, headers=_api_headers(), timeout=timeout)


def _api_put_json(path: str, payload: dict, timeout: int = 30):
    return requests.put(f"{API_BASE_URL}{path}", json=payload, headers=_api_headers(), timeout=timeout)


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
        resp = _api_delete(f"/conversations/{conv_id}")
        if resp.status_code != 200:
            st.toast("删除会话失败，请重试", icon="⚠️")
    except Exception as exc:
        st.toast(f"删除会话失败：{exc}", icon="⚠️")
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
    lines.append(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    for item in _get_current_messages():
        lines.append(f"## 👤 用户\n{item['user']}\n")
        answer = item.get('assistant', {}).get('answer', '')
        lines.append(f"## 🤖 AI\n{answer}\n")
        refs = item.get('assistant', {}).get('references', [])
        if refs:
            lines.append("### 引用来源")
            for ref in refs:
                score = round(float(ref.get("score", 0)), 4)
                lines.append(f"- {ref.get('source_file', '未命名')} (相似度 {score})")
        lines.append("\n---\n")
    return "\n".join(lines)


def _load_recent_docs(project_id: str | None = None, *, include_unassigned: bool = True) -> list[dict]:
    try:
        path = "/documents/recent"
        if project_id:
            include_text = "true" if include_unassigned else "false"
            path = f"{path}?project_id={quote(project_id)}&include_unassigned={include_text}"
        resp = _api_get(path)
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return payload.get("data", {}).get("items", [])
    except Exception:
        pass
    return []


def _assign_doc_to_project(doc_id: str, project_id: str) -> tuple[bool, str]:
    try:
        resp = _api_put_json(f"/documents/{doc_id}/project", {"project_id": project_id})
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return True, "已归档到当前项目。"
        return False, _error_message(payload.get("message", ""))
    except Exception as exc:
        return False, f"归档失败：{exc}"


def _assign_unassigned_docs(project_id: str) -> tuple[bool, str]:
    try:
        resp = _api_post_json("/documents/assign_unassigned", {"project_id": project_id}, timeout=60)
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            assigned = payload.get("data", {}).get("assigned", 0)
            return True, f"已归档 {assigned} 个未归属资料。"
        return False, _error_message(payload.get("message", ""))
    except Exception as exc:
        return False, f"归档失败：{exc}"


def _load_logs() -> list[dict]:
    try:
        resp = _api_get("/logs")
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return payload.get("data", {}).get("items", [])
    except Exception:
        pass
    return []


def _rag_debug(question: str, top_k: int, score_threshold: float | None = None) -> tuple[bool, dict | str]:
    payload = {"question": question, "top_k": top_k, "stream": False}
    if score_threshold is not None:
        payload["score_threshold"] = score_threshold
    try:
        resp = _api_post_json("/rag/debug", payload, timeout=60)
        data = resp.json()
        if resp.status_code == 200 and data.get("code") == 200:
            return True, data.get("data", {})
        payload = data.get("data") or {}
        if isinstance(payload, dict):
            payload["message"] = data.get("message", "")
            return False, payload
        return False, _error_message(data.get("message", ""))
    except Exception as exc:
        return False, f"检索调试失败：{exc}"


def _generate_tasks(query: str, context_hint: str, top_k: int, conversation_id: str = "") -> tuple[bool, dict | str]:
    try:
        resp = _api_post_json(
            "/tasks/generate",
            {"query": query, "context_hint": context_hint, "top_k": top_k, "conversation_id": conversation_id},
            timeout=180,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("code") == 200:
            return True, data.get("data", {})
        return False, _error_message(data.get("message", ""))
    except Exception as exc:
        return False, f"任务生成失败：{exc}"


def _load_tasks(conversation_id: str = "") -> list[dict]:
    try:
        params = f"?conversation_id={conversation_id}" if conversation_id else ""
        resp = _api_get(f"/tasks{params}")
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return payload.get("data", {}).get("items", [])
    except Exception:
        pass
    return []


def _load_task_detail(task_id: int) -> tuple[bool, dict | str]:
    try:
        resp = _api_get(f"/tasks/{task_id}")
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return True, payload.get("data", {})
        return False, _error_message(payload.get("message", ""))
    except Exception as exc:
        return False, f"任务详情加载失败：{exc}"


def _upload_document(uploaded_file, project_id: str = "") -> tuple[bool, str]:
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type or "application/octet-stream",
        )
    }
    data = {"project_id": project_id} if project_id else {}
    try:
        resp = requests.post(
            f"{API_BASE_URL}/documents/upload",
            data=data,
            files=files,
            headers=_api_headers(),
            timeout=120,
        )
        payload = resp.json()
        if resp.status_code == 200 and payload.get("code") == 200:
            return True, "资料上传成功。"
        return False, _error_message(payload.get("message", ""))
    except Exception:
        return False, "上传失败，请稍后重试。"


# ── Custom CSS ─────────────────────────────────────────────────────────

def inject_custom_css():
    css_path = Path(__file__).parent / "static" / "styles.css"
    external_css = ""
    if css_path.exists():
        external_css = css_path.read_text(encoding="utf-8")
    st.markdown(
        "<style>" + external_css + "</style>",
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
        st.session_state.latest_docs = _load_recent_docs(st.session_state.current_conv_id)
    if "include_unassigned_docs" not in st.session_state:
        st.session_state.include_unassigned_docs = True
    if "only_unassigned_docs" not in st.session_state:
        st.session_state.only_unassigned_docs = False
    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False
    # Model-related state
    if "available_models" not in st.session_state:
        st.session_state.available_models = DEFAULT_MODELS.copy()
    if "selected_model" not in st.session_state:
        st.session_state.selected_model = DEFAULT_MODELS[0]["id"]
    if "show_add_model_dialog" not in st.session_state:
        st.session_state.show_add_model_dialog = False
    if "rag_debug_result" not in st.session_state:
        st.session_state.rag_debug_result = None
    if "task_generate_result" not in st.session_state:
        st.session_state.task_generate_result = None
    if "llm_diagnostic_result" not in st.session_state:
        st.session_state.llm_diagnostic_result = None


# ── Sidebar ────────────────────────────────────────────────────────────

def render_sidebar():
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

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

    # 对话搜索
    search_query = st.text_input("🔍 搜索项目", placeholder="输入关键词...", key="conv_search", label_visibility="collapsed")

    filtered_convs = st.session_state.conversations
    if search_query:
        filtered_convs = {
            k: v for k, v in st.session_state.conversations.items()
            if search_query.lower() in v.get("title", "").lower()
        }

    for conv_id, conv in filtered_convs.items():
        title = conv.get("title", "新对话")
        is_active = conv_id == st.session_state.current_conv_id
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            label = f"{'● ' if is_active else ''}{title}"
            if st.button(label, key=f"conv_{conv_id}", use_container_width=True):
                _switch_conversation(conv_id)
                st.rerun()
        with col2:
            pending_conv_key = f"pending_delete_conv_{conv_id}"
            if st.session_state.get(pending_conv_key):
                if st.button("✓", key=f"confirm_conv_{conv_id}", help="确认删除"):
                    _delete_conversation(conv_id)
                    st.session_state.pop(pending_conv_key, None)
                    st.rerun()
            else:
                if st.button("×", key=f"del_conv_{conv_id}"):
                    st.session_state[pending_conv_key] = True
                    st.rerun()

    st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)

    col_new, col_export = st.columns(2)
    with col_new:
        if st.button("＋ 新建项目", use_container_width=True, key="new_conv_inline"):
            _create_new_conversation()
            st.rerun()
    with col_export:
        export_md = _export_chat()
        st.download_button(
            "📥 导出",
            data=export_md,
            file_name="chat_export.md",
            mime="text/markdown",
            use_container_width=True,
            key="export_chat_btn",
        )

    st.markdown("---")

    include_unassigned = st.toggle(
        "包含未归属资料",
        value=bool(st.session_state.get("include_unassigned_docs", True)),
        key="include_unassigned_docs",
    )
    only_unassigned = st.toggle(
        "只看未归属",
        value=bool(st.session_state.get("only_unassigned_docs", False)),
        key="only_unassigned_docs",
    )
    include_unassigned, only_unassigned = compute_doc_filter_state(
        include_unassigned=include_unassigned, only_unassigned=only_unassigned
    )
    if include_unassigned != bool(st.session_state.get("include_unassigned_docs", True)):
        st.session_state.include_unassigned_docs = include_unassigned
        st.rerun()

    docs_raw = _load_recent_docs(
        st.session_state.current_conv_id,
        include_unassigned=include_unassigned,
    )
    docs = filter_docs(docs_raw, only_unassigned=only_unassigned)
    st.session_state.latest_docs = docs_raw

    doc_count = len(docs) if docs else 0
    unassigned_count = len([d for d in docs_raw if not d.get("project_id")]) if docs_raw else 0
    st.markdown(f'<div class="sidebar-section-label">📁 资料库 ({doc_count})</div>', unsafe_allow_html=True)
    st.caption(f"未归属：{unassigned_count}")

    if unassigned_count > 0 and bool(st.session_state.get("include_unassigned_docs", True)):
        if st.button("🗂️ 一键归档未归属资料到当前项目", use_container_width=True, key="assign_unassigned_btn"):
            ok, message = _assign_unassigned_docs(st.session_state.current_conv_id)
            if ok:
                docs_raw = _load_recent_docs(
                    st.session_state.current_conv_id,
                    include_unassigned=bool(st.session_state.get("include_unassigned_docs", True)),
                )
                docs = filter_docs(
                    docs_raw,
                    only_unassigned=bool(st.session_state.get("only_unassigned_docs", False)),
                )
                st.session_state.latest_docs = docs_raw
                st.toast(message, icon="✅")
                st.rerun()
            else:
                st.toast(message, icon="⚠️")

    uploaded = st.file_uploader(
        "上传资料",
        type=["pdf", "md", "txt", "docx", "xlsx", "pptx"],
        label_visibility="collapsed",
        key="workspace_uploader",
    )
    if uploaded is not None:
        if st.button("📤 上传并处理", use_container_width=True, key="upload_submit"):
            with st.spinner("正在处理资料..."):
                ok, message = _upload_document(uploaded, st.session_state.current_conv_id)
            if ok:
                docs_raw = _load_recent_docs(
                    st.session_state.current_conv_id,
                    include_unassigned=bool(st.session_state.get("include_unassigned_docs", True)),
                )
                docs = filter_docs(
                    docs_raw,
                    only_unassigned=bool(st.session_state.get("only_unassigned_docs", False)),
                )
                st.session_state.latest_docs = docs_raw
                st.toast(message, icon="✅")
                st.rerun()
            else:
                st.toast(message, icon="⚠️")

    if docs:
        for i, doc in enumerate(docs[:3]):
            col_file, col_del = st.columns([0.85, 0.15])
            file_type = doc.get("file_type", "")
            chunk_count = doc.get("chunk_count", 0)
            tags = doc.get("tags", [])
            doc_project_id = doc.get("project_id") or ""
            type_icons = {"pdf": "📄", "md": "📝", "txt": "📃", "docx": "📘", "xlsx": "📊", "pptx": "📑"}
            icon = type_icons.get(file_type, "📎")
            tags_html = ""
            if tags:
                tags_html = " ".join(f'<span style="background:#e8f4fd;color:#1976d2;padding:1px 5px;border-radius:3px;font-size:10px;">{escape(t)}</span>' for t in tags[:3])
                tags_html = f'<div style="margin-top:2px;">{tags_html}</div>'
            project_badge = ""
            if not doc_project_id:
                project_badge = '<span style="background:#fff3cd;color:#b45309;padding:1px 6px;border-radius:999px;font-size:10px;margin-left:6px;">未归属</span>'
            with col_file:
                st.markdown(
                    f'<div class="file-item">{icon} {escape(str(doc.get("file_name", "未命名资料")))}{project_badge}'
                    f'<span style="color:#bbb;font-size:11px;margin-left:4px;">{chunk_count}片</span></div>'
                    f'{tags_html}',
                    unsafe_allow_html=True,
                )
            with col_del:
                if not doc_project_id:
                    if st.button("归档", key=f"assign_doc_{doc.get('id')}", help="归档到当前项目"):
                        doc_id = doc.get("id")
                        if doc_id:
                            ok, message = _assign_doc_to_project(doc_id, st.session_state.current_conv_id)
                            if ok:
                                docs_raw = _load_recent_docs(
                                    st.session_state.current_conv_id,
                                    include_unassigned=bool(st.session_state.get("include_unassigned_docs", True)),
                                )
                                docs = filter_docs(
                                    docs_raw,
                                    only_unassigned=bool(st.session_state.get("only_unassigned_docs", False)),
                                )
                                st.session_state.latest_docs = docs_raw
                                st.toast(message, icon="✅")
                                st.rerun()
                            else:
                                st.toast(message, icon="⚠️")

                pending_key = f"pending_delete_doc_{doc.get('id')}"
                if st.session_state.get(pending_key):
                    if st.button("✓", key=f"confirm_doc_{i}", help="确认删除"):
                        doc_id = doc.get("id")
                        if doc_id:
                            try:
                                resp = _api_delete(f"/documents/{doc_id}")
                                if resp.status_code == 200:
                                    st.session_state.latest_docs = [
                                        d for d in st.session_state.latest_docs if d.get("id") != doc_id
                                    ]
                                else:
                                    st.toast("删除失败，请重试", icon="⚠️")
                            except Exception as exc:
                                st.toast(f"删除失败：{exc}", icon="⚠️")
                        st.session_state.pop(pending_key, None)
                        st.rerun()
                else:
                    if st.button("x", key=f"delete_doc_{i}", help="删除此资料"):
                        st.session_state[pending_key] = True
                        st.rerun()

            # 文档详情预览
            detail_key = f"show_detail_{doc.get('id')}"
            if st.button("📋 详情", key=f"detail_btn_{i}", help="查看文档详情"):
                st.session_state[detail_key] = not st.session_state.get(detail_key, False)
            if st.session_state.get(detail_key):
                try:
                    detail_resp = _api_get(f"/documents/{doc.get('id')}")
                    detail_data = detail_resp.json().get("data", {})
                    preview = detail_data.get("preview", "")
                    if preview:
                        with st.expander("📄 内容预览", expanded=True):
                            st.text(preview[:500])
                    # 标签编辑
                    current_tags = detail_data.get("tags", [])
                    new_tags = st.text_input(
                        "标签（逗号分隔）",
                        value=",".join(current_tags),
                        key=f"tags_input_{i}",
                    )
                    if st.button("💾 保存标签", key=f"save_tags_{i}"):
                        tag_list = [t.strip() for t in new_tags.split(",") if t.strip()]
                        _api_put_json(f"/documents/{doc.get('id')}/tags", {"tags": tag_list})
                        docs_raw = _load_recent_docs(
                            st.session_state.current_conv_id,
                            include_unassigned=bool(st.session_state.get("include_unassigned_docs", True)),
                        )
                        docs = filter_docs(
                            docs_raw,
                            only_unassigned=bool(st.session_state.get("only_unassigned_docs", False)),
                        )
                        st.session_state.latest_docs = docs_raw
                        st.toast("标签已保存", icon="✅")
                except Exception as exc:
                    st.error(f"加载详情失败：{exc}")

        if doc_count > 3:
            st.markdown(f'<div style="font-size:12px;color:#999;padding:4px 8px;">还有 {doc_count - 3} 个文件...</div>', unsafe_allow_html=True)

    st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)

    st.markdown("---")

    model_names = [m["name"] for m in st.session_state.available_models]
    current_index = 0
    for i, m in enumerate(st.session_state.available_models):
        if m["id"] == st.session_state.selected_model:
            current_index = i
            break
    selected = st.selectbox(
        "模型选择", model_names, index=current_index,
        key="model_selector_sidebar", label_visibility="collapsed",
    )
    for m in st.session_state.available_models:
        if m["name"] == selected and st.session_state.selected_model != m["id"]:
            st.session_state.selected_model = m["id"]
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
        _, mid, _ = st.columns([1, 8, 1])
        with mid:
            st.error(assistant.get("answer", "发生未知错误"))

    else:
        _, mid, _ = st.columns([1, 8, 1])
        with mid:
            steps = assistant.get("steps", [])
            if steps:
                with st.expander("思考步骤", expanded=False):
                    steps_html = ""
                    for step in steps:
                        steps_html += f"""
                        <div class="thinking-step">
                            <span class="thinking-check">&#10003;</span>
                            <span>{escape(str(step))}</span>
                        </div>
                        """
                    st.markdown(steps_html, unsafe_allow_html=True)

            answer_text = assistant.get("answer", "")
            if answer_text:
                st.markdown(answer_text)
                # 复制按钮
                copy_col1, copy_col2, copy_col3 = st.columns([0.85, 0.1, 0.05])
                with copy_col2:
                    if st.button("📋", key=f"copy_{hash(answer_text[:50])}", help="复制回答"):
                        st.toast("已复制到剪贴板", icon="✅")

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

            if answer_text:
                btn_key = f"task_btn_{hash(answer_text[:50])}"
                if st.button("📋 生成任务", key=btn_key):
                    conv_id = st.session_state.get("current_conv_id", "")
                    with st.spinner("正在生成任务拆解..."):
                        ok, result = _generate_tasks(answer_text[:2000], answer_text[:500], 5, conv_id)
                    if ok:
                        tasks = result.get("tasks", [])
                        st.success(f"✅ 已生成 {len(tasks)} 个任务并保存到看板")
                        render_task_result(result)
                    else:
                        st.error(str(result))


def _format_reference_label(ref: dict) -> str:
    parts = [str(ref.get("source_file") or "未命名资料")]
    if ref.get("page_no") is not None:
        parts.append(f"第 {ref.get('page_no')} 页")
    if ref.get("section"):
        parts.append(str(ref.get("section")))
    if ref.get("chunk_id"):
        parts.append(str(ref.get("chunk_id")))
    return " / ".join(parts)


def render_references(refs: list[dict], *, title: str = "引用来源"):
    if not refs:
        st.caption("暂无引用来源。")
        return
    st.caption(title)
    for ref in refs:
        score = ref.get("score")
        score_text = f" · 相似度 {float(score):.4f}" if score is not None else ""
        preview = ref.get("preview") or ref.get("content") or ""
        st.markdown(f"**{_format_reference_label(ref)}{score_text}**")
        if preview:
            st.caption(preview)


def render_workflow_summary(workflow: dict):
    if not workflow:
        return
    engine = workflow.get("engine", "unknown")
    review = workflow.get("review", {})
    status = "通过" if review.get("passed") else "需要检查"
    st.caption(f"编排引擎：{engine} · Review：{status}")
    steps = workflow.get("steps", [])
    if steps:
        st.write(" / ".join(str(step) for step in steps))
    issues = review.get("issues", [])
    if issues:
        st.warning("ReviewAgent 发现任务需要检查。")
        st.json(issues)


def render_task_result(result: dict):
    render_workflow_summary(result.get("workflow", {}))
    tasks = result.get("tasks", [])
    refs = result.get("references", [])
    if not tasks:
        st.info("暂无任务结果。")
        return
    for task in tasks:
        title = task.get("title", "未命名任务")
        status = task.get("status", "TODO")
        source_count = len(refs)
        with st.expander(f"{title} · {status} · {source_count} 个来源", expanded=True):
            st.write(task.get("description", ""))
            cols = st.columns(4)
            cols[0].metric("类型", task.get("task_type", "-"))
            cols[1].metric("优先级", task.get("priority", "-"))
            cols[2].metric("难度", task.get("difficulty", "-"))
            cols[3].metric("预估工时", task.get("estimated_hours", "-"))
            st.write(f"依赖：{task.get('dependency') or '无'}")
            st.write(f"交付物：{task.get('deliverable') or '未填写'}")
            render_references(refs, title="任务来源")


def render_recent_tasks():
    conv_id = st.session_state.get("current_conv_id", "")
    tasks = _load_tasks(conv_id)
    if not tasks:
        st.caption("暂无已保存任务。")
        return
    for task in tasks[:8]:
        task_id = task.get("id")
        label = f"#{task_id} {task.get('title', '未命名任务')} · {task.get('status', '-')}"
        with st.expander(label, expanded=False):
            cols = st.columns(4)
            cols[0].metric("类型", task.get("task_type", "-"))
            cols[1].metric("优先级", task.get("priority", "-"))
            cols[2].metric("工时", task.get("estimated_hours", "-"))
            cols[3].metric("来源数", task.get("source_count", 0))
            if task_id and st.button("查看详情和来源", key=f"task_detail_{task_id}"):
                ok, detail = _load_task_detail(int(task_id))
                if ok:
                    st.session_state[f"task_detail_result_{task_id}"] = detail
                else:
                    st.error(detail)
            detail = st.session_state.get(f"task_detail_result_{task_id}")
            if detail:
                task_detail = detail.get("task", {})
                st.write(task_detail.get("description", ""))
                st.write(f"交付物：{task_detail.get('deliverable') or '未填写'}")
                render_references(detail.get("sources", []), title="已绑定来源")


# ── Chat Area ──────────────────────────────────────────────────────────

def render_chat_area():
    current_messages = _get_current_messages()
    if not current_messages:
        st.markdown(
            """
            <div class="welcome-container">
                <div style="font-size: 13px; color: #d97706; font-weight: 600; margin-bottom: 8px; letter-spacing: 1px;">RACEAGENT</div>
                <div class="welcome-greeting">你好，我是 RaceAgent</div>
                <div class="welcome-desc">大学生科技竞赛 AI 备赛助手，帮你分析赛题、拆解任务、制定计划</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for item in current_messages:
            render_message(item)


def _handle_query(text: str):
    """添加用户消息，执行查询，通过 st.write_stream 实时流式展示回答"""
    import queue
    import threading

    # 1. 显示用户消息
    st.markdown(
        f'<div class="user-message"><div class="user-bubble">{escape(text)}</div></div>',
        unsafe_allow_html=True,
    )

    # 2. 保存用户消息
    conv_id = st.session_state.current_conv_id
    try:
        _api_post_json(f"/conversations/{conv_id}/messages", {
            "role": "user",
            "content": text,
        })
    except Exception as e:
        print(f"[Handle] 保存用户消息失败: {type(e).__name__}: {e}")

    # 3. 构建历史消息
    history = []
    for item in _get_current_messages()[-4:]:
        history.append({"role": "user", "content": item["user"][:2000]})
        if item["assistant"].get("answer") and item["assistant"].get("kind") != "loading":
            history.append({"role": "assistant", "content": item["assistant"]["answer"][:2000]})

    # 4. 后台线程读 SSE，主线程通过 st.write_stream 实时渲染
    token_queue: queue.Queue = queue.Queue()
    references: list[dict] = []
    collected_answer: list[str] = []
    stream_error: list[str] = []

    def _sse_reader():
        try:
            resp = requests.post(
                f"{API_BASE_URL}/rag/query",
                json={
                    "question": text,
                    "top_k": DEFAULT_TOP_K,
                    "stream": True,
                    "history": history,
                    "model": st.session_state.get("selected_model"),
                },
                headers=_api_headers(),
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

            if "text/event-stream" not in content_type:
                resp.close()
                try:
                    payload = resp.json()
                except (ValueError, TypeError):
                    token_queue.put(("error", "模型服务返回异常，请稍后重试"))
                    return
                if payload.get("code") == 200:
                    data = payload.get("data", {})
                    references.extend(data.get("references", []))
                    token_queue.put(("answer", data.get("answer", "")))
                else:
                    token_queue.put(("error", _error_message(payload.get("message", ""))))
                return

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
                    references.extend(event.get("references", []))
                elif event_type == "token":
                    token = event.get("token", "")
                    if token:
                        token_queue.put(("token", token))
            resp.close()
            token_queue.put(("done", ""))
        except Exception as e:
            print(f"[Handle] SSE 异常: {type(e).__name__}: {e}")
            token_queue.put(("error", f"请求失败：{e}"))

    t = threading.Thread(target=_sse_reader, daemon=True)
    t.start()

    # 5. st.write_stream 是 Streamlit 唯一支持实时流式渲染的 API
    def _token_stream():
        first_token = True
        while True:
            try:
                kind, value = token_queue.get(timeout=120)
            except queue.Empty:
                yield "\n\n⚠️ 响应超时，请稍后重试。"
                break
            if kind == "token":
                if first_token:
                    first_token = False
                collected_answer.append(value)
                yield value
            elif kind == "answer":
                collected_answer.clear()
                collected_answer.append(value)
                yield value
                break
            elif kind == "error":
                stream_error.clear()
                message = _error_message(value)
                stream_error.append(message)
                yield f"\n\n⚠️ {message}"
                break
            elif kind == "done":
                break

    loading_placeholder = st.empty()
    loading_placeholder.markdown(
        '<div style="color:#888;font-size:14px;padding:8px 0;">🤖 正在思考中...</div>',
        unsafe_allow_html=True,
    )

    _, mid, _ = st.columns([1, 8, 1])
    with mid:
        def _stream_with_loading():
            for token in _token_stream():
                if loading_placeholder:
                    loading_placeholder.empty()
                yield token

        st.write_stream(_stream_with_loading())

    full_answer = "".join(collected_answer).strip()
    st.session_state["pending_references"] = references
    st.session_state["pending_answer"] = full_answer

    try:
        if stream_error:
            result = {"kind": "error", "answer": stream_error[-1]}
        else:
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
        _api_post_json(f"/conversations/{conv_id}/messages", {
            "role": "assistant",
            "content": json.dumps(result, ensure_ascii=False),
        })
    except Exception as e:
        print(f"[Handle] 保存助手回复失败: {type(e).__name__}: {e}")


def render_kanban_board():
    conv_id = st.session_state.get("current_conv_id")
    if not conv_id:
        st.info("请先在左侧选择或创建一个对话，然后在聊天中生成任务。")
        return

    try:
        resp = _api_get(f"/tasks?conversation_id={conv_id}")
        data = resp.json()
        items = data.get("data", {}).get("items", [])
    except Exception as exc:
        st.toast(f"加载任务失败：{exc}", icon="⚠️")
        items = []

    if not items:
        st.info("当前对话暂无任务。在聊天中输入「帮我拆解任务」即可生成。")
        return

    # ── 优先级筛选 ──────────────────────────────────────────────────
    filter_col1, filter_col2 = st.columns([1, 3])
    with filter_col1:
        priority_options = ["全部", "HIGH", "MEDIUM", "LOW"]
        priority_labels = {"全部": "全部优先级", "HIGH": "🔴 高", "MEDIUM": "🟡 中", "LOW": "🟢 低"}
        selected_priority = st.selectbox(
            "筛选优先级", priority_options,
            format_func=lambda x: priority_labels[x],
            key="kanban_priority_filter",
        )
    if selected_priority != "全部":
        items = [t for t in items if t.get("priority") == selected_priority]

    todo = [t for t in items if t.get("status") == "TODO"]
    doing = [t for t in items if t.get("status") == "IN_PROGRESS"]
    done = [t for t in items if t.get("status") == "DONE"]

    # ── 统计栏 ──────────────────────────────────────────────────────
    total = len(items)
    done_count = len(done)
    progress = done_count / total if total > 0 else 0
    st.markdown(f"### 📋 任务看板 — 共 {total} 项")
    prog_col1, prog_col2 = st.columns([3, 1])
    with prog_col1:
        st.progress(progress)
    with prog_col2:
        st.markdown(f"**完成率 {progress:.0%}**")

    stat_cols = st.columns(3)
    stat_cols[0].markdown(f"🟢 待办 **{len(todo)}** 项")
    stat_cols[1].markdown(f"🔵 进行中 **{len(doing)}** 项")
    stat_cols[2].markdown(f"✅ 已完成 **{done_count}** 项")

    st.markdown("")

    col_todo, col_doing, col_done = st.columns(3)

    def _deadline_color(deadline_str: str) -> str:
        """根据截止日期返回颜色：过期红、今天橙、本周黄、其他灰"""
        if not deadline_str:
            return "#999"
        try:
            from datetime import date, datetime
            deadline_date = datetime.strptime(deadline_str[:10], "%Y-%m-%d").date()
            today = date.today()
            delta = (deadline_date - today).days
            if delta < 0:
                return "#e74c3c"  # 已过期
            if delta == 0:
                return "#e67e22"  # 今天到期
            if delta <= 3:
                return "#f1c40f"  # 3 天内
            return "#27ae60"      # 充裕
        except Exception:
            return "#999"

    def _render_card(task: dict, col_idx: int):
        tid = task["id"]
        priority_colors = {"HIGH": "#e74c3c", "MEDIUM": "#f39c12", "LOW": "#27ae60"}
        p_color = priority_colors.get(task.get("priority", ""), "#888")
        priority_labels_short = {"HIGH": "高", "MEDIUM": "中", "LOW": "低"}
        p_label = priority_labels_short.get(task.get("priority", ""), "")
        deadline = task.get("deadline", "")
        assignee = task.get("assignee", "")
        description = task.get("description", "")

        deadline_color = _deadline_color(deadline)
        deadline_html = f'<span style="color:{deadline_color};font-size:12px;">⏰ {deadline}</span>' if deadline else ""
        assignee_html = f'<span style="color:#666;font-size:12px;">👤 {escape(assignee)}</span>' if assignee else ""
        priority_html = f'<span style="background:{p_color};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px;">{p_label}</span>'

        st.markdown(
            f'<div style="background:#fff;border:1px solid #e8e8e8;border-left:3px solid {p_color};'
            f'border-radius:8px;padding:12px;margin-bottom:10px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
            f'<span style="font-weight:600;font-size:14px;">{escape(task["title"])}</span>'
            f'{priority_html}</div>'
            f'<div style="font-size:12px;color:#888;margin-bottom:4px;">{escape(task.get("task_type", ""))} · '
            f'{task.get("estimated_hours", 0)}h</div>'
            f'{deadline_html} {assignee_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 折叠显示长描述
        if description and len(description) > 50:
            with st.expander("📄 查看描述", expanded=False):
                st.markdown(description)

        options = ["TODO", "IN_PROGRESS", "DONE"]
        labels = {"TODO": "待办", "IN_PROGRESS": "进行中", "DONE": "已完成"}
        current_idx = options.index(task.get("status", "TODO")) if task.get("status") in options else 0
        new_status = st.selectbox(
            "状态", options, index=current_idx,
            format_func=lambda x: labels[x],
            key=f"status_{tid}_{col_idx}",
        )
        if new_status != task.get("status"):
            try:
                resp = _api_put_json(f"/tasks/{tid}", {"status": new_status})
                if resp.status_code == 200:
                    st.rerun()
                else:
                    st.toast("更新状态失败，请重试", icon="⚠️")
            except Exception as exc:
                st.toast(f"更新状态失败：{exc}", icon="⚠️")

        if st.button("🗑", key=f"del_{tid}_{col_idx}"):
            try:
                resp = _api_delete(f"/tasks/{tid}")
                if resp.status_code == 200:
                    st.rerun()
                else:
                    st.toast("删除任务失败，请重试", icon="⚠️")
            except Exception as exc:
                st.toast(f"删除任务失败：{exc}", icon="⚠️")

    with col_todo:
        st.markdown(f"**🟢 待办 ({len(todo)})**")
        for t in todo:
            _render_card(t, 0)

    with col_doing:
        st.markdown(f"**🔵 进行中 ({len(doing)})**")
        for t in doing:
            _render_card(t, 1)

    with col_done:
        st.markdown(f"**✅ 已完成 ({len(done)})**")
        for t in done:
            _render_card(t, 2)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    # [关键修复点 1] 使用 layout="wide" 启用全宽布局
    st.set_page_config(
        page_title="RaceAgent",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 注入自定义 CSS，移除所有 max-width 限制
    inject_custom_css()

    init_session_state()

    with st.sidebar:
        render_sidebar()

    tab_chat, tab_kanban = st.tabs(["💬 聊天", "📋 任务看板"])

    with tab_chat:
        render_chat_area()

        user_input = st.chat_input("输入消息，Enter 发送，Shift+Enter 换行...", max_chars=2000)
        if user_input:
            _handle_query(user_input)

        pending_refs = st.session_state.pop("pending_references", None)
        if pending_refs:
            _, mid, _ = st.columns([1, 8, 1])
            with mid:
                refs_html = '<div class="ref-section">'
                refs_html += '<div style="font-size:12px;color:#888;margin-bottom:4px;font-weight:600;">引用来源</div>'
                for ref in pending_refs:
                    score = round(float(ref.get("score", 0)), 4)
                    ref_file = escape(str(ref.get("source_file", "未命名资料")))
                    refs_html += f'<div class="ref-item">{ref_file} (相似度 {score})</div>'
                refs_html += '</div>'
                st.markdown(refs_html, unsafe_allow_html=True)

    with tab_kanban:
        render_kanban_board()


main()
