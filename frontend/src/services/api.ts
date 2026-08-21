import type { AnswerPayload, JsonRecord } from "../types/api";

export class ApiError extends Error {
  constructor(message: string, readonly code?: string, readonly status?: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(body?.error?.message ?? "请求失败", body?.error?.code, response.status);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body ?? {}) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export interface AgentStreamEvent {
  event: string;
  data: JsonRecord;
}

export async function streamAgentAction(
  path: string,
  body: unknown,
  onEvent: (event: AgentStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) throw new ApiError("无法建立问答数据流", undefined, response.status);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      let event = "message";
      let data = "{}";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      const parsed = JSON.parse(data) as JsonRecord;
      onEvent({ event, data: parsed });
      if (event === "error") throw new ApiError(String(parsed.message ?? "问答失败"), String(parsed.code ?? ""));
    }
  }
}

export function streamAgentMessage(
  sessionId: number,
  content: string,
  onEvent: (event: AgentStreamEvent) => void,
  options?: { requireApproval?: boolean; resumeRunId?: string; signal?: AbortSignal },
): Promise<void> {
  const { signal, ...bodyOptions } = options ?? {};
  return streamAgentAction(`/api/qa/sessions/${sessionId}/messages/stream`, { content, ...bodyOptions }, onEvent, signal);
}

export function streamApproval(
  sessionId: number,
  body: { approve: boolean; runId: string },
  onEvent: (event: AgentStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamAgentAction(`/api/qa/sessions/${sessionId}/approve`, body, onEvent, signal);
}

export function answerFromEvent(data: JsonRecord): AnswerPayload {
  return data as unknown as AnswerPayload;
}
