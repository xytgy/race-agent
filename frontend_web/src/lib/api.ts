import type {
  ApiEnvelope,
  Conversation,
  DocDetail,
  DocItem,
  RagQueryResponse,
  TaskDetail,
  TaskItem
} from "@/lib/types";

class ApiError extends Error {
  status: number;
  code?: number;
  requestId?: string;

  constructor(message: string, status: number, opts?: { code?: number; requestId?: string }) {
    super(message);
    this.status = status;
    this.code = opts?.code;
    this.requestId = opts?.requestId;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {})
    },
    cache: "no-store"
  });

  const contentType = resp.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    if (!resp.ok) {
      throw new ApiError(`请求失败（HTTP ${resp.status}）`, resp.status);
    }
    return (await resp.text()) as unknown as T;
  }

  const payload = (await resp.json()) as ApiEnvelope<T>;
  if (!resp.ok || payload.code !== 200) {
    throw new ApiError(payload.message || `请求失败（HTTP ${resp.status}）`, resp.status, {
      code: payload.code,
      requestId: payload.request_id
    });
  }
  return payload.data;
}

export const api = {
  async listConversations(): Promise<Conversation[]> {
    const data = await apiFetch<{ items: Conversation[] }>("/conversations");
    return data.items || [];
  },

  async createConversation(): Promise<Conversation> {
    return apiFetch<Conversation>("/conversations", { method: "POST", body: JSON.stringify({}) });
  },

  async deleteConversation(id: string): Promise<void> {
    await apiFetch(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  },

  async updateConversationTitle(id: string, title: string): Promise<void> {
    await apiFetch(`/conversations/${encodeURIComponent(id)}/title`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title })
    });
  },

  async listMessages(conversationId: string): Promise<{ id: number; role: string; content: any; created_at: string }[]> {
    const data = await apiFetch<{ items: { id: number; role: string; content: any; created_at: string }[] }>(
      `/conversations/${encodeURIComponent(conversationId)}/messages`
    );
    return data.items || [];
  },

  async addMessage(conversationId: string, role: string, content: any): Promise<void> {
    await apiFetch(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, content })
    });
  },

  async listDocuments(projectId: string, includeUnassigned: boolean): Promise<DocItem[]> {
    const qs = new URLSearchParams({
      project_id: projectId,
      include_unassigned: includeUnassigned ? "true" : "false"
    });
    const data = await apiFetch<{ items: DocItem[] }>(`/documents/recent?${qs.toString()}`);
    return data.items || [];
  },

  async uploadDocument(file: File, projectId: string): Promise<void> {
    const form = new FormData();
    form.append("file", file);
    form.append("project_id", projectId);
    await apiFetch("/documents/upload", { method: "POST", body: form });
  },

  async deleteDocument(docId: string): Promise<void> {
    await apiFetch(`/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
  },

  async getDocumentDetail(docId: string): Promise<DocDetail> {
    return apiFetch<DocDetail>(`/documents/${encodeURIComponent(docId)}`);
  },

  async updateDocumentTags(docId: string, tags: string[]): Promise<void> {
    await apiFetch(`/documents/${encodeURIComponent(docId)}/tags`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tags })
    });
  },

  async assignDocument(docId: string, projectId: string): Promise<void> {
    await apiFetch(`/documents/${encodeURIComponent(docId)}/project`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId })
    });
  },

  async assignUnassigned(projectId: string): Promise<number> {
    const data = await apiFetch<{ assigned: number }>("/documents/assign_unassigned", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId })
    });
    return data.assigned || 0;
  },

  async ragQuery(question: string, opts: { topK: number; history?: { role: string; content: string }[] }) {
    return apiFetch<RagQueryResponse>("/rag/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: opts.topK, stream: false, history: opts.history || [] })
    });
  },

  async listTasks(conversationId: string): Promise<TaskItem[]> {
    const qs = new URLSearchParams({ conversation_id: conversationId });
    const data = await apiFetch<{ items: TaskItem[] }>(`/tasks?${qs.toString()}`);
    return data.items || [];
  },

  async getTaskDetail(taskId: number): Promise<TaskDetail> {
    return apiFetch<TaskDetail>(`/tasks/${taskId}`);
  },

  async updateTask(taskId: number, payload: { status?: string; assignee?: string; deadline?: string }): Promise<TaskItem> {
    return apiFetch<TaskItem>(`/tasks/${taskId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  },

  async deleteTask(taskId: number): Promise<void> {
    await apiFetch(`/tasks/${taskId}`, { method: "DELETE" });
  },

  async generateTasks(conversationId: string, query: string, contextHint: string): Promise<void> {
    await apiFetch("/tasks/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, context_hint: contextHint, top_k: 5, conversation_id: conversationId })
    });
  }
};

export { ApiError };
