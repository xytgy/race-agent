"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import type { Conversation, DocItem } from "@/lib/types";
import { useToast } from "./Toast";
import ChatArea from "./ChatArea";
import TaskBoard from "./TaskBoard";

const MODELS = [
  { value: "mimo-v2.5-pro", label: "MiMo v2.5 Pro" },
  { value: "mimo-v2-flash", label: "MiMo v2 Flash" },
  { value: "deepseek-v3", label: "DeepSeek V3" },
] as const;

const FILE_TYPE_STYLES: Record<string, string> = {
  pdf: "bg-red-500/20 text-red-400",
  md: "bg-blue-500/20 text-blue-400",
  txt: "bg-white/10 text-white/50",
};

const PARSE_STATUS: Record<string, { label: string; dot: string }> = {
  completed: { label: "已解析", dot: "bg-emerald-400" },
  parsing: { label: "解析中", dot: "bg-amber-400" },
  failed: { label: "解析失败", dot: "bg-red-400" },
  pending: { label: "等待中", dot: "bg-white/30" },
};

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none group">
      <div
        className={`relative w-8 h-[18px] rounded-full transition-colors flex-shrink-0 ${
          checked ? "bg-indigo-500" : "bg-white/15"
        }`}
        onClick={() => onChange(!checked)}
      >
        <div
          className={`absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform ${
            checked ? "translate-x-[14px]" : ""
          }`}
        />
      </div>
      <span className="text-xs text-white/50 group-hover:text-white/70 transition-colors">
        {label}
      </span>
    </label>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? "bg-[#1a1f2e] text-white"
          : "text-white/40 hover:text-white/60 hover:bg-white/[0.04]"
      }`}
    >
      {children}
    </button>
  );
}



export default function AppShell() {
  const { toast } = useToast();
  const [projects, setProjects] = useState<Conversation[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState("");
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [activeTab, setActiveTab] = useState<"chat" | "tasks">("chat");
  const [includeUnassigned, setIncludeUnassigned] = useState(true);
  const [onlyUnassigned, setOnlyUnassigned] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>(MODELS[0].value);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listConversations().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    if (projects.length > 0 && !currentProjectId) {
      setCurrentProjectId(projects[0].id);
    }
    if (projects.length === 0) {
      setCurrentProjectId("");
    }
  }, [projects, currentProjectId]);

  useEffect(() => {
    if (!currentProjectId) {
      setDocs([]);
      return;
    }
    const effective = includeUnassigned || onlyUnassigned;
    api
      .listDocuments(currentProjectId, effective)
      .then(setDocs)
      .catch(() => setDocs([]));
  }, [currentProjectId, includeUnassigned, onlyUnassigned]);

  const unassignedCount = docs.filter((d) => !d.project_id).length;

  const displayDocs = onlyUnassigned ? docs.filter((d) => !d.project_id) : docs;

  const refreshDocs = () => {
    if (!currentProjectId) return;
    const effective = includeUnassigned || onlyUnassigned;
    api
      .listDocuments(currentProjectId, effective)
      .then(setDocs)
      .catch(() => {});
  };

  const handleCreateProject = async () => {
    try {
      const conversation = await api.createConversation();
      setProjects((prev) => [conversation, ...prev]);
      setCurrentProjectId(conversation.id);
      toast("项目已创建", "success");
    } catch { toast("创建失败", "error"); }
  };

  const handleDeleteProject = async (id: string) => {
    try {
      await api.deleteConversation(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      if (currentProjectId === id) setCurrentProjectId("");
      toast("项目已删除", "success");
    } catch { toast("删除失败", "error"); }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !currentProjectId) return;
    setUploading(true);
    try {
      await api.uploadDocument(file, currentProjectId);
      refreshDocs();
      toast("上传成功", "success");
    } catch { toast("上传失败", "error"); }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleAssignDoc = async (docId: string) => {
    if (!currentProjectId) return;
    try {
      await api.assignDocument(docId, currentProjectId);
      refreshDocs();
      toast("已归档", "success");
    } catch { toast("归档失败", "error"); }
  };

  const handleAssignAll = async () => {
    if (!currentProjectId) return;
    try {
      await api.assignUnassigned(currentProjectId);
      refreshDocs();
      toast("已全部归档", "success");
    } catch { toast("归档失败", "error"); }
  };

  const handleDeleteDoc = async (docId: string) => {
    try {
      await api.deleteDocument(docId);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
      toast("资料已删除", "success");
    } catch { toast("删除失败", "error"); }
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-[280px] flex-shrink-0 bg-[#0f1219] border-r border-white/[0.06] flex flex-col">
        <div className="px-4 py-5 border-b border-white/[0.06]">
          <h1 className="text-lg font-bold text-white tracking-tight">
            RaceAgent
          </h1>
          <p className="text-[11px] text-white/35 mt-0.5">竞赛项目工作台</p>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
          <div>
            <div className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2 px-1">
              项目
            </div>
            <div className="space-y-0.5">
              {projects.map((p) => (
                <div
                  key={p.id}
                  onClick={() => setCurrentProjectId(p.id)}
                  className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                    currentProjectId === p.id
                      ? "bg-[#1a1f2e] text-white"
                      : "text-white/55 hover:bg-[#1a1f2e]/60 hover:text-white/75"
                  }`}
                >
                  <svg
                    className="w-3.5 h-3.5 flex-shrink-0 opacity-40"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                    />
                  </svg>
                  <span className="flex-1 truncate text-[13px]">{p.title}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteProject(p.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-white/25 hover:text-red-400 transition-all p-0.5"
                  >
                    <svg
                      className="w-3.5 h-3.5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
            <button
              onClick={handleCreateProject}
              className="w-full mt-2 px-3 py-2 rounded-lg border border-dashed border-white/10 text-xs text-white/35 hover:text-white/55 hover:border-white/20 transition-colors"
            >
              + 新建项目
            </button>
          </div>

          <div className="border-t border-white/[0.06]" />

          {currentProjectId && (
            <div>
              <div className="flex items-center justify-between mb-2 px-1">
                <span className="text-[10px] font-semibold text-white/30 uppercase tracking-widest">
                  资料
                </span>
                {unassignedCount > 0 && (
                  <span className="text-[10px] bg-amber-500/15 text-amber-400 px-1.5 py-0.5 rounded-full font-medium">
                    {unassignedCount} 未归属
                  </span>
                )}
              </div>

              <div className="space-y-1.5 mb-3 px-1">
                <Toggle
                  checked={includeUnassigned}
                  onChange={setIncludeUnassigned}
                  label="包含未归属"
                />
                <Toggle
                  checked={onlyUnassigned}
                  onChange={(v) => {
                    setOnlyUnassigned(v);
                    if (v) setIncludeUnassigned(true);
                  }}
                  label="只看未归属"
                />
              </div>

              {onlyUnassigned && displayDocs.length > 0 && (
                <button
                  onClick={handleAssignAll}
                  className="w-full mb-2 px-3 py-1.5 rounded-lg bg-indigo-500/15 text-indigo-400 text-xs font-medium hover:bg-indigo-500/25 transition-colors"
                >
                  一键归档到当前项目
                </button>
              )}

              <div className="space-y-0.5">
                {displayDocs.map((doc) => {
                  const status = PARSE_STATUS[doc.parse_status] || PARSE_STATUS.pending;
                  const typeStyle =
                    FILE_TYPE_STYLES[doc.file_type] || FILE_TYPE_STYLES.txt;
                  const isUnassigned = !doc.project_id;

                  return (
                    <div
                      key={doc.id}
                      className="group px-2 py-2 rounded-lg hover:bg-[#1a1f2e]/60 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded flex-shrink-0 ${typeStyle}`}
                        >
                          {doc.file_type}
                        </span>
                        <span className="flex-1 truncate text-xs text-white/65">
                          {doc.file_name}
                        </span>
                        {isUnassigned && (
                          <button
                            onClick={() => handleAssignDoc(doc.id)}
                            className="text-[10px] text-indigo-400 hover:text-indigo-300 flex-shrink-0 transition-colors"
                          >
                            归档
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteDoc(doc.id)}
                          className="opacity-0 group-hover:opacity-100 text-white/25 hover:text-red-400 transition-all flex-shrink-0 p-0.5"
                        >
                          <svg
                            className="w-3 h-3"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M6 18L18 6M6 6l12 12"
                            />
                          </svg>
                        </button>
                      </div>
                      <div className="flex items-center gap-1.5 mt-1 pl-[30px]">
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${status.dot}`}
                        />
                        <span className="text-[10px] text-white/30">
                          {status.label}
                          {doc.chunk_count > 0 && ` · ${doc.chunk_count} 切片`}
                        </span>
                      </div>
                    </div>
                  );
                })}
                {displayDocs.length === 0 && (
                  <div className="text-center text-xs text-white/20 py-4">
                    暂无资料
                  </div>
                )}
              </div>

              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="w-full mt-2 px-3 py-2 rounded-lg border border-dashed border-white/10 text-xs text-white/35 hover:text-white/55 hover:border-white/20 transition-colors disabled:opacity-40"
              >
                {uploading ? "上传中..." : "+ 上传资料"}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.md,.txt,.docx,.xlsx,.pptx"
                className="hidden"
                onChange={handleFileUpload}
              />
            </div>
          )}
        </div>

        <div className="px-3 py-3 border-t border-white/[0.06]">
          <label className="text-[10px] text-white/30 block mb-1.5 px-1 font-semibold uppercase tracking-widest">
            模型
          </label>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="w-full bg-[#1a1f2e] text-white/80 text-xs rounded-lg px-3 py-2 border border-white/[0.06] focus:outline-none focus:border-indigo-500/50 appearance-none cursor-pointer"
          >
            {MODELS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center gap-1 px-4 py-2 border-b border-white/[0.06] bg-[#0f1219]/40 backdrop-blur-sm">
          <TabButton
            active={activeTab === "chat"}
            onClick={() => setActiveTab("chat")}
          >
            问答
          </TabButton>
          <TabButton
            active={activeTab === "tasks"}
            onClick={() => setActiveTab("tasks")}
          >
            任务
          </TabButton>
        </div>

        <div className="flex-1 overflow-hidden">
          {currentProjectId ? (
            activeTab === "chat" ? (
              <ChatArea
                conversationId={currentProjectId}
                model={selectedModel}
              />
            ) : (
              <TaskBoard conversationId={currentProjectId} />
            )
          ) : (
            <div className="flex items-center justify-center h-full text-white/20 text-sm">
              请先选择或创建一个项目
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
