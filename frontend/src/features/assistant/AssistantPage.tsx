import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { api, answerFromEvent, streamAgentMessage, streamApproval } from "../../services/api";
import type { AnswerPayload, AppConfig, ChatMessage, JsonRecord, Session } from "../../types/api";
import { AnswerView } from "./AnswerView";
import { dataStatsSummaryText } from "./answerSummary";
import styles from "./AssistantPage.module.css";

type SessionMessages = { messages: Array<ChatMessage & { chart?: AnswerPayload }>; session: Session };

function mergeAnswerPayload(current: AnswerPayload | undefined, next: AnswerPayload): AnswerPayload {
  if (current?.type === "structuredAnswer" && next.type === "structuredAnswer") {
    return { ...current, ...next };
  }
  return next;
}

type FrequentQuestion = AppConfig["frequentQuestions"][number];

function Composer({
  disabled,
  cancellable,
  frequent,
  frequentEnabled,
  frequentThreshold,
  onCancel,
  onSend,
}: {
  disabled: boolean;
  cancellable: boolean;
  frequent: FrequentQuestion[];
  frequentEnabled: boolean;
  frequentThreshold: number;
  onCancel: () => void;
  onSend: (value: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const [quickOpen, setQuickOpen] = useState(false);
  const canSend = !disabled && !!draft.trim();

  function submit(value = draft) {
    const content = value.trim();
    if (!content || disabled) return;
    setDraft("");
    setQuickOpen(false);
    onSend(content);
  }

  return <footer className={styles.composer}><div className={styles.inputWrap}>
    <button className={styles.quickButton} title="常问问题" onClick={() => setQuickOpen((value) => !value)}>⚡</button>
    {quickOpen && <div className={styles.quickPanel}><header><strong>⚡ 常问问题</strong><button onClick={() => setQuickOpen(false)}>×</button></header><div>{frequent.length > 0 ? frequent.map((item) => <button key={item.id} onClick={() => submit(item.question)}><span>{item.question}</span><small>{item.hitCount} 次</small></button>) : <p>{frequentEnabled ? `暂无达到 ${frequentThreshold} 次阈值的常问问题` : "常问功能未开启"}</p>}</div></div>}
    <textarea rows={1} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } }} placeholder="请写下您的想法…" />
    {/* <button className={styles.micButton} title="语音输入暂未启用">⌁</button> */}
    {cancellable ? <button className={styles.stopButton} aria-label="取消本次回答" title="取消本次回答" onClick={onCancel}>停止</button> : <button className={styles.sendButton} aria-label="发送" onClick={() => submit()} disabled={!canSend}>→</button>}
  </div></footer>;
}

export function AssistantPage() {
  const client = useQueryClient();
  const [sessionId, setSessionId] = useState<number>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [events, setEvents] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<{ runId: string; calls: JsonRecord[]; message: string } | null>(null);
  const [resuming, setResuming] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api.get<{ items: Session[] }>("/api/qa/sessions") });
  const config = useQuery({ queryKey: ["app-config"], queryFn: () => api.get<AppConfig>("/api/app-config") });
  const history = useQuery({ queryKey: ["session", sessionId], enabled: !!sessionId, queryFn: () => api.get<SessionMessages>(`/api/qa/sessions/${sessionId}/messages`) });
  const createSession = useMutation({ mutationFn: () => api.post<Session>("/api/qa/sessions", { title: "新的问数会话" }), onSuccess: (item) => { setSessionId(item.id); setMessages([]); client.invalidateQueries({ queryKey: ["sessions"] }); } });
  const removeSession = useMutation({ mutationFn: (id: number) => api.delete(`/api/qa/sessions/${id}`), onSuccess: (_, id) => {
    const current = client.getQueryData<{ items: Session[] }>(["sessions"]);
    const next = current?.items.filter((item) => item.id !== id) ?? [];
    client.setQueryData(["sessions"], { items: next });
    if (sessionId === id) { setSessionId(next[0]?.id); setMessages([]); }
    client.invalidateQueries({ queryKey: ["sessions"] });
  } });

  useEffect(() => {
    if (!sessionId && sessions.data?.items[0]) setSessionId(sessions.data.items[0].id);
    if (!sessionId && sessions.data && sessions.data.items.length === 0 && !createSession.isPending) createSession.mutate();
  }, [sessions.data, sessionId]);
  useEffect(() => { if (history.data) setMessages(history.data.messages.map((m) => ({ ...m, answerPayload: m.answerPayload ?? m.chart }))); }, [history.data]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ block: "end" }));
    return () => cancelAnimationFrame(frame);
  }, [messages, events.length]);

  const greeting = config.data?.openingGreeting ?? "欢迎使用智能问数，我可以帮你分析经营数据。";
  const questions = useMemo(() => config.data?.openingQuestions ?? [], [config.data]);
  const frequent = useMemo(() => config.data?.frequentEnabled !== false ? config.data?.frequentQuestions?.slice(0, 8) ?? [] : [], [config.data]);

  async function report(messageIndex: number, reason: string) {
    if (!sessionId) throw new Error("当前会话尚未就绪");
    try {
      const message = messages[messageIndex];
      const question = [...messages.slice(0, messageIndex)].reverse().find((item) => item.role === "user")?.content ?? "";
      const answerSnippet = dataStatsSummaryText(message.answerPayload) || "该回复不包含数据统计结果总结。";
      await api.post("/api/qa/feedback", { sessionId, messageId: message.id, question, answerSnippet, reason });
      setEvents((items) => [...items, "已提交回复校对反馈"]);
    } catch (cause) { throw new Error(cause instanceof Error ? cause.message : "反馈提交失败"); }
  }

  async function send(value: string) {
    const content = value.trim();
    if (!content || running || pending || resuming || !sessionId) return;
    setError(""); setEvents([]); setRunning(true);
    setPending(null);
    setMessages((items) => [...items, { role: "user", content }, { role: "assistant", content: "" }]);
    let answer = ""; let payload: AnswerPayload | undefined;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamAgentMessage(sessionId, content, ({ event, data }) => {
        if (event === "cancelled") setEvents((items) => [...items, String(data.message ?? "已取消本次回答")]);
        if (event === "status") setEvents((items) => [...items, String(data.message ?? "处理中")]);
        if (event === "skill") setEvents((items) => [...items, data.matched ? `命中 Skill：${String(data.name ?? data.code ?? "业务分析")}` : "未命中固定 Skill，使用动态规划"]);
        if (event === "plan") setEvents((items) => [...items, `生成查询计划：${Array.isArray(data.calls) ? data.calls.length : 0} 个接口步骤`]);
        if (event === "node_started") setEvents((items) => [...items, `开始：${String(data.label ?? data.node ?? "Agent 节点")}`]);
        if (event === "node_completed") setEvents((items) => [...items, `完成：${String(data.label ?? data.node ?? "Agent 节点")}`]);
        if (event === "pending_approval") setPending({ runId: String(data.runId ?? ""), calls: Array.isArray(data.calls) ? (data.calls as JsonRecord[]) : [], message: String(data.message ?? "查询计划等待审批") });
        if (event === "answer") {
          payload = mergeAnswerPayload(payload, answerFromEvent(data));
          setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, answerPayload: payload } : item));
        }
        if (event === "delta") {
          answer += String(data.content ?? "");
          if (payload?.type !== "structuredAnswer") setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, content: answer, answerPayload: payload } : item));
        }
        if (event === "done") {
          const finalPayload = (data.answerPayload as AnswerPayload) ?? payload;
          setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, id: Number(data.messageId) || item.id, content: finalPayload?.type === "structuredAnswer" ? "" : answer, answerPayload: finalPayload } : item));
        }
      }, { signal: controller.signal });
      client.invalidateQueries({ queryKey: ["sessions"] });
    } catch (cause) {
      if (isAbortError(cause)) {
        setEvents((items) => [...items, "已取消本次回答"]);
        setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, content: answer || "已取消本次回答。" } : item));
      } else {
        setError(cause instanceof Error ? cause.message : "问答失败");
      }
    }
    finally { if (abortRef.current === controller) abortRef.current = null; setRunning(false); }
  }

  async function decideApproval(approve: boolean) {
    if (!sessionId || !pending || resuming) return;
    setResuming(true); setError("");
    let answer = ""; let payload: AnswerPayload | undefined;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamApproval(sessionId, { approve, runId: pending.runId }, ({ event, data }) => {
        if (event === "cancelled") setEvents((items) => [...items, String(data.message ?? "已取消本次回答")]);
        if (event === "status") setEvents((items) => [...items, String(data.message ?? "处理中")]);
        if (event === "node_started") setEvents((items) => [...items, `开始：${String(data.label ?? data.node ?? "Agent 节点")}`]);
        if (event === "node_completed") setEvents((items) => [...items, `完成：${String(data.label ?? data.node ?? "Agent 节点")}`]);
        if (event === "answer") {
          payload = mergeAnswerPayload(payload, answerFromEvent(data));
          setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, answerPayload: payload } : item));
        }
        if (event === "delta") {
          answer += String(data.content ?? "");
          if (payload?.type !== "structuredAnswer") setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, content: answer, answerPayload: payload } : item));
        }
        if (event === "done") {
          const finalPayload = (data.answerPayload as AnswerPayload) ?? payload;
          setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, id: Number(data.messageId) || item.id, content: finalPayload?.type === "structuredAnswer" ? "" : answer, answerPayload: finalPayload } : item));
        }
      }, controller.signal);
      setPending(null);
      client.invalidateQueries({ queryKey: ["sessions"] });
    } catch (cause) {
      if (isAbortError(cause)) {
        setEvents((items) => [...items, "已取消本次回答"]);
        setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, content: answer || "已取消本次回答。" } : item));
      } else {
        setError(cause instanceof Error ? cause.message : "审批恢复失败");
      }
    }
    finally { if (abortRef.current === controller) abortRef.current = null; setResuming(false); }
  }

  function cancelCurrentRun() {
    abortRef.current?.abort();
    setRunning(false);
    setResuming(false);
    setEvents((items) => [...items, "正在取消本次回答…"]);
  }

  return (
    <div className={`${styles.workspace} ${sessionsOpen ? styles.sessionsOpen : ""}`}>
      <aside className={styles.sessions}>
        <div className={styles.sessionsHeader}><button title="收起会话记录" onClick={() => setSessionsOpen(false)}>‹</button><strong>近30天记录</strong></div>
        <Button className={styles.newChat} onClick={() => createSession.mutate()} disabled={createSession.isPending}>＋ 开启新对话</Button>
        <div className={styles.sessionList}>{sessions.data?.items.map((item) => <div key={item.id} className={`${styles.sessionItem} ${sessionId === item.id ? styles.selected : ""}`}><button className={styles.sessionButton} onClick={() => setSessionId(item.id)}><strong className={styles.sessionTitle}>{item.title}</strong><span className={styles.sessionMeta}>{item.messageCount} 条消息</span></button><button className={styles.remove} title="删除会话" onClick={() => removeSession.mutate(item.id)}>×</button></div>)}</div>
      </aside>
      <section className={styles.chat}>
        <header><button className={styles.historyButton} onClick={() => setSessionsOpen((value) => !value)} title="会话记录">☰</button><h1>{history.data?.session.title || "AI 智能问数对话"}</h1></header>
        <div className={styles.messages}>
          {messages.length === 0 && <div className={styles.welcome}><h1>你好</h1><h2>我是经管之星 · AI问数助手</h2>{config.data?.greetingEnabled !== false && <><p>{greeting}</p>{questions.length > 0 && <section><strong>你可以这么问我</strong><div>{questions.map((item) => <button key={item} onClick={() => send(item)}>{item}</button>)}</div></section>}</>}</div>}
          {messages.map((message, index) => {
            const isLatestAssistant = message.role === "assistant" && index === messages.length - 1;
            const showLiveTrace = isLatestAssistant && (running || resuming) && events.length > 0;
            return <article key={index} className={message.role === "user" ? styles.userMessage : styles.assistantMessage}><div className={styles.avatar}>{message.role === "user" ? "你" : "J"}</div><div className={styles.bubble}>{message.role === "assistant" ? <AnswerView content={message.content} payload={message.answerPayload} traceEvents={showLiveTrace ? events : undefined} onSuggestion={send} onFeedback={(reason) => report(index, reason)} /> : message.content}</div></article>;
          })}
          {pending && <div className={styles.approvalPanel}>
            <strong>{resuming ? "正在执行审批…" : "查询计划待人工审批"}</strong>
            <p>{pending.message}</p>
            {pending.calls.length > 0 && <div className={styles.approvalCalls}>{pending.calls.map((call, index) => <span key={index}>{String(call.interfaceCode ?? "")} · {String(call.purpose ?? "接口调用")}</span>)}</div>}
            {!resuming && <div className={styles.approvalActions}><button className={styles.approveButton} onClick={() => decideApproval(true)}>通过并执行</button><button className={styles.rejectButton} onClick={() => decideApproval(false)}>拒绝</button></div>}
          </div>}
          {error && <div className="error">{error}</div>}<div ref={bottomRef} />
        </div>
        <Composer
          disabled={running || resuming || !!pending || !sessionId}
          cancellable={running || resuming}
          frequent={frequent}
          frequentEnabled={config.data?.frequentEnabled !== false}
          frequentThreshold={config.data?.frequentThreshold ?? 3}
          onCancel={cancelCurrentRun}
          onSend={send}
        />
      </section>
    </div>
  );
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
