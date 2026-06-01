"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { TaskItem, TaskDetail } from "@/lib/types";

type TaskBoardProps = {
  conversationId: string;
};

const STATUS_ORDER = ["TODO", "DOING", "DONE"] as const;

const STATUS_LABEL: Record<string, string> = {
  TODO: "待办",
  DOING: "进行中",
  DONE: "已完成",
};

const STATUS_COLOR: Record<string, string> = {
  TODO: "bg-gray-600 text-gray-200",
  DOING: "bg-blue-600 text-blue-100",
  DONE: "bg-green-600 text-green-100",
};

const PRIORITY_COLOR: Record<string, string> = {
  HIGH: "bg-red-600/30 text-red-300 border border-red-600/40",
  MEDIUM: "bg-yellow-600/30 text-yellow-300 border border-yellow-600/40",
  LOW: "bg-green-600/30 text-green-300 border border-green-600/40",
};

const PRIORITY_LABEL: Record<string, string> = {
  HIGH: "高",
  MEDIUM: "中",
  LOW: "低",
};

const DIFFICULTY_LABEL: Record<string, string> = {
  high: "难",
  medium: "中",
  low: "易",
};

const NEXT_STATUS: Record<string, string> = {
  TODO: "DOING",
  DOING: "DONE",
};

function TaskCard({
  task,
  expanded,
  detail,
  onToggle,
  onStatusChange,
  onDelete,
}: {
  task: TaskItem;
  expanded: boolean;
  detail: TaskDetail | null;
  onToggle: () => void;
  onStatusChange: (taskId: number, status: string) => void;
  onDelete: (taskId: number) => void;
}) {
  const next = NEXT_STATUS[task.status];

  return (
    <div className="bg-[#242a3d] rounded-lg p-3 cursor-pointer transition-colors hover:bg-[#2c3350]">
      <div className="flex items-start justify-between gap-2" onClick={onToggle}>
        <p className="text-sm text-gray-100 font-medium leading-snug flex-1">
          {task.title}
        </p>
        <button
          className="text-gray-500 hover:text-red-400 shrink-0 mt-0.5 text-xs"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(task.id);
          }}
        >
          ✕
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 mt-2">
        {task.priority && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${PRIORITY_COLOR[task.priority] || ""}`}>
            {PRIORITY_LABEL[task.priority] || task.priority}
          </span>
        )}
        {task.difficulty && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#3a4158] text-gray-300">
            {DIFFICULTY_LABEL[task.difficulty] || task.difficulty}
          </span>
        )}
        {task.estimated_hours > 0 && (
          <span className="text-[10px] text-gray-400">
            ≈{task.estimated_hours}h
          </span>
        )}
      </div>

      {next && (
        <button
          className="mt-2 text-[11px] text-blue-400 hover:text-blue-300 transition-colors"
          onClick={(e) => {
            e.stopPropagation();
            onStatusChange(task.id, next);
          }}
        >
          移至 → {STATUS_LABEL[next]}
        </button>
      )}

      {expanded && (
        <div className="mt-3 pt-3 border-t border-[#3a4158] text-xs text-gray-300 space-y-2">
          {task.description && (
            <p className="leading-relaxed whitespace-pre-wrap">{task.description}</p>
          )}
          {detail && (
            <>
              {detail.task.deliverable && (
                <div>
                  <span className="text-gray-400 font-medium">交付物：</span>
                  <span>{detail.task.deliverable}</span>
                </div>
              )}
              {detail.sources.length > 0 && (
                <div>
                  <span className="text-gray-400 font-medium">引用来源：</span>
                  <ul className="mt-1 space-y-1">
                    {detail.sources.map((s) => (
                      <li key={s.id} className="text-gray-400">
                        {s.source_file || "未知来源"}
                        {s.page_no ? ` · 第${s.page_no}页` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
          {!detail && (
            <p className="text-gray-500">加载详情中…</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function TaskBoard({ conversationId }: TaskBoardProps) {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [query, setQuery] = useState("");
  const [generating, setGenerating] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detailCache, setDetailCache] = useState<Record<number, TaskDetail>>({});

  const loadTasks = useCallback(async () => {
    try {
      const items = await api.listTasks(conversationId);
      setTasks(items);
    } catch {
      setTasks([]);
    }
  }, [conversationId]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const handleGenerate = async () => {
    const text = query.trim();
    if (!text || generating) return;
    setGenerating(true);
    try {
      await api.generateTasks(conversationId, text, text);
      setQuery("");
      await loadTasks();
    } finally {
      setGenerating(false);
    }
  };

  const handleStatusChange = async (taskId: number, status: string) => {
    try {
      await api.updateTask(taskId, { status });
      await loadTasks();
    } catch {
      // 状态切换失败时静默处理，避免干扰用户
    }
  };

  const handleDelete = async (taskId: number) => {
    try {
      await api.deleteTask(taskId);
      if (expandedId === taskId) setExpandedId(null);
      await loadTasks();
    } catch {
      // 删除失败时静默处理
    }
  };

  const handleToggle = async (taskId: number) => {
    if (expandedId === taskId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(taskId);
    if (!detailCache[taskId]) {
      try {
        const detail = await api.getTaskDetail(taskId);
        setDetailCache((prev) => ({ ...prev, [taskId]: detail }));
      } catch {
        // 详情加载失败时保持空详情
      }
    }
  };

  const grouped = STATUS_ORDER.map((status) => ({
    status,
    items: tasks.filter((t) => t.status === status),
  }));

  const isEmpty = tasks.length === 0 && !generating;

  return (
    <div className="flex flex-col h-full bg-[#0f1219]">
      <div className="p-4 border-b border-[#1a1f2e]">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
            placeholder="输入任务生成的主题…"
            disabled={generating}
            className="flex-1 bg-[#1a1f2e] text-sm text-gray-200 placeholder-gray-500 rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-blue-500/50 disabled:opacity-50"
          />
          <button
            onClick={handleGenerate}
            disabled={generating || !query.trim()}
            className="shrink-0 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            {generating ? "生成中…" : "生成任务"}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 text-sm space-y-3">
            <div className="text-4xl opacity-30">📋</div>
            <p>还没有任务</p>
            <p className="text-xs text-gray-600">在上方输入主题，自动生成任务拆解</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3 h-full">
            {grouped.map(({ status, items }) => (
              <div key={status} className="bg-[#1a1f2e] rounded-xl p-3 flex flex-col">
                <div className="flex items-center gap-2 mb-3">
                  <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${STATUS_COLOR[status]}`}>
                    {STATUS_LABEL[status]}
                  </span>
                  <span className="text-[11px] text-gray-500">{items.length}</span>
                </div>
                <div className="flex-1 space-y-2 overflow-y-auto">
                  {items.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      expanded={expandedId === task.id}
                      detail={detailCache[task.id] || null}
                      onToggle={() => handleToggle(task.id)}
                      onStatusChange={handleStatusChange}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
