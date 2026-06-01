import type { RagReference } from "@/lib/types";

type RagMeta = { references: RagReference[]; embedding_mode?: string };

export async function streamRagQuery(opts: {
  question: string;
  topK: number;
  history: { role: string; content: string }[];
  model?: string;
  onMeta?: (meta: RagMeta) => void;
  onToken?: (token: string) => void;
}): Promise<{ answer: string; references: RagReference[]; embeddingMode?: string }> {
  const resp = await fetch("/api/rag/query", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      question: opts.question,
      top_k: opts.topK,
      stream: true,
      history: opts.history,
      model: opts.model
    })
  });

  if (!resp.ok || !resp.body) {
    throw new Error(`请求失败（HTTP ${resp.status}）`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  let answer = "";
  let references: RagReference[] = [];
  let embeddingMode: string | undefined;

  const handleEvent = (raw: string) => {
    const lines = raw.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const jsonText = trimmed.slice(5).trim();
      if (!jsonText) continue;
      const payload = JSON.parse(jsonText) as any;
      if (payload.type === "meta") {
        references = Array.isArray(payload.references) ? payload.references : [];
        embeddingMode = payload.embedding_mode;
        opts.onMeta?.({ references, embedding_mode: embeddingMode });
        continue;
      }
      if (payload.type === "token") {
        const token = String(payload.token || "");
        answer += token;
        opts.onToken?.(token);
      }
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.trim()) {
        handleEvent(part);
      }
    }
  }

  if (buffer.trim()) {
    handleEvent(buffer);
  }

  return { answer, references, embeddingMode };
}

