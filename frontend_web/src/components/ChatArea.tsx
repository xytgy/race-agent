"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { streamRagQuery } from "@/lib/sse";
import type { RagReference } from "@/lib/types";

type RawMessage = {
  id: number;
  role: string;
  content: any;
  created_at: string;
};

type PairedMessage = {
  user: string;
  assistant: { kind: string; answer: string; references: RagReference[] };
};

type Props = {
  conversationId: string;
  model?: string;
};

function parseAssistantContent(content: any): { answer: string; references: RagReference[] } {
  if (typeof content === "string") {
    try {
      const parsed = JSON.parse(content);
      if (parsed.kind === "qa") {
        return { answer: parsed.answer || "", references: parsed.references || [] };
      }
      return { answer: content, references: [] };
    } catch {
      return { answer: content, references: [] };
    }
  }
  if (content && typeof content === "object" && content.kind === "qa") {
    return { answer: content.answer || "", references: content.references || [] };
  }
  return { answer: JSON.stringify(content), references: [] };
}

function pairMessages(items: RawMessage[]): PairedMessage[] {
  const pairs: PairedMessage[] = [];
  let i = 0;
  while (i < items.length) {
    if (items[i].role === "user") {
      const userContent = typeof items[i].content === "string" ? items[i].content : JSON.stringify(items[i].content);
      let assistantMeta: { kind: string; answer: string; references: RagReference[] } = { kind: "qa", answer: "", references: [] };
      if (i + 1 < items.length && items[i + 1].role === "assistant") {
        const parsed = parseAssistantContent(items[i + 1].content);
        assistantMeta = { kind: "qa", ...parsed };
        i += 2;
      } else {
        i += 1;
      }
      pairs.push({ user: userContent, assistant: assistantMeta });
    } else {
      i += 1;
    }
  }
  return pairs;
}

function ReferenceList({ references }: { references: RagReference[] }) {
  if (!references.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {references.map((ref, idx) => (
        <span
          key={idx}
          className="inline-flex items-center gap-1 rounded-md bg-[#0f1219] border border-gray-700 px-2 py-0.5 text-xs text-gray-400"
        >
          {ref.source_file}
          {ref.page_no != null && <span className="text-gray-500">P{ref.page_no}</span>}
          {ref.score != null && (
            <span className="text-indigo-400">{(ref.score * 100).toFixed(0)}%</span>
          )}
        </span>
      ))}
    </div>
  );
}

function TypingCursor() {
  return (
    <span className="inline-block w-[2px] h-[1em] bg-indigo-400 ml-0.5 align-middle animate-pulse" />
  );
}

export default function ChatArea({ conversationId, model }: Props) {
  const [pairedMessages, setPairedMessages] = useState<PairedMessage[]>([]);
  const [rawMessages, setRawMessages] = useState<RawMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamAnswer, setStreamAnswer] = useState("");
  const [streamReferences, setStreamReferences] = useState<RagReference[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const items = await api.listMessages(conversationId);
        if (!cancelled) {
          setRawMessages(items);
          setPairedMessages(pairMessages(items));
        }
      } catch {
        if (!cancelled) {
          setRawMessages([]);
          setPairedMessages([]);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [conversationId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [pairedMessages, streamAnswer]);

  const buildHistory = useCallback(() => {
    const history: { role: string; content: string }[] = [];
    for (const pair of pairedMessages) {
      history.push({ role: "user", content: pair.user });
      if (pair.assistant.answer) {
        history.push({ role: "assistant", content: pair.assistant.answer });
      }
    }
    return history;
  }, [pairedMessages]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;

    setInput("");
    setStreaming(true);
    setStreamAnswer("");
    setStreamReferences([]);

    const tempUserMsg: RawMessage = {
      id: Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setRawMessages((prev) => [...prev, tempUserMsg]);
    setPairedMessages((prev) => [...prev, { user: text, assistant: { kind: "qa", answer: "", references: [] } }]);

    api.addMessage(conversationId, "user", text).catch(() => {});

    const history = buildHistory();

    try {
      const result = await streamRagQuery({
        question: text,
        topK: 3,
        history,
        model,
        onMeta: (meta) => {
          setStreamReferences(meta.references);
        },
        onToken: (token) => {
          setStreamAnswer((prev) => prev + token);
        },
      });

      const assistantContent = JSON.stringify({
        kind: "qa",
        answer: result.answer,
        references: result.references,
      });
      api.addMessage(conversationId, "assistant", assistantContent).catch(() => {});

      const assistantMsg: RawMessage = {
        id: Date.now(),
        role: "assistant",
        content: assistantContent,
        created_at: new Date().toISOString(),
      };
      setRawMessages((prev) => [...prev, assistantMsg]);
      setPairedMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last) {
          last.assistant = { kind: "qa", answer: result.answer, references: result.references };
        }
        return [...updated];
      });
    } catch {
      setPairedMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last) {
          last.assistant = { kind: "qa", answer: "请求失败，请稍后重试。", references: [] };
        }
        return [...updated];
      });
    } finally {
      setStreaming(false);
      setStreamAnswer("");
      setStreamReferences([]);
    }
  }, [input, streaming, conversationId, model, buildHistory]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0f1219]">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {pairedMessages.length === 0 && !streaming && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="text-2xl mb-2">💬</div>
              <div className="text-white/25 text-sm">输入问题开始对话</div>
              <div className="text-white/15 text-xs mt-1">基于你上传的资料进行智能问答</div>
            </div>
          </div>
        )}

        {pairedMessages.map((pair, idx) => (
          <div key={idx} className="space-y-3">
            <div className="flex justify-end">
              <div className="max-w-[75%] bg-indigo-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap">
                {pair.user}
              </div>
            </div>
            {pair.assistant.answer && (
              <div className="flex justify-start">
                <div className="max-w-[80%] bg-[#1a1f2e] rounded-xl px-4 py-3 text-sm text-gray-200 leading-relaxed">
                  <div className="whitespace-pre-wrap">{pair.assistant.answer}</div>
                  <ReferenceList references={pair.assistant.references} />
                </div>
              </div>
            )}
          </div>
        ))}

        {streaming && (
          <div className="space-y-3">
            <div className="flex justify-end">
              <div className="max-w-[75%] bg-indigo-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed opacity-50">
                {input || "..."}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[80%] bg-[#1a1f2e] rounded-xl px-4 py-3 text-sm text-gray-200 leading-relaxed">
                {streamAnswer ? (
                  <div className="whitespace-pre-wrap">
                    {streamAnswer}
                    <TypingCursor />
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-gray-400">
                    <span className="inline-block w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:0ms]" />
                    <span className="inline-block w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:150ms]" />
                    <span className="inline-block w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:300ms]" />
                    <span className="ml-1 text-xs">正在分析中...</span>
                  </div>
                )}
                <ReferenceList references={streamReferences} />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-gray-800 px-4 py-3">
        <div className="flex items-end gap-2 bg-[#1a1f2e] border border-gray-700 rounded-xl px-3 py-2 focus-within:border-indigo-500 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题..."
            rows={1}
            className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-500 outline-none resize-none max-h-32 leading-relaxed"
            style={{ minHeight: "24px" }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="shrink-0 p-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
              <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
