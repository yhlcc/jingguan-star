import { memo, useMemo, useState } from "react";
import { Card } from "../../components/ui/Card";
import { EChart } from "../../components/charts/EChart";
import { CopyFilled, MehFilled } from '@ant-design/icons';
import { payloadChart } from "../../components/charts/chartOptions";
import type { AnswerPayload, ChartPayload, JsonRecord } from "../../types/api";
import styles from "./AssistantPage.module.css";
import { answerTextForCopy, dataStatsSummary } from "./answerSummary";

const cell = (value: unknown) => typeof value === "object" ? JSON.stringify(value) : String(value ?? "-");

const ChartBlock = memo(function ChartBlock({ chart }: { chart: ChartPayload }) {
  const option = useMemo(() => payloadChart(chart), [chart]);
  if (chart.mode === "split" && chart.charts?.length) return <div className={`${styles.chartBlock} grid cols-2`}>{chart.charts.map((item, index) => <Card key={index} title={item.title}><SplitChart chart={item} /></Card>)}</div>;
  return <Card className={styles.chartBlock} title={chart.title ?? "数据可视化"}><EChart option={option} height={300} /></Card>;
});

const SplitChart = memo(function SplitChart({ chart }: { chart: ChartPayload }) {
  const option = useMemo(() => payloadChart(chart), [chart]);
  return <EChart option={option} height={250} />;
});

function formatProcessDetail(item: JsonRecord): string {
  const parts: string[] = [];
  if (item.detail) parts.push(String(item.detail));
  if (item.durationMs !== undefined) parts.push(`耗时 ${String(item.durationMs)} ms`);
  if (item.rowCount !== undefined) parts.push(`返回 ${String(item.rowCount)} 行`);
  if (item.requestId) parts.push(`requestId: ${String(item.requestId)}`);
  return parts.join(" · ");
}

function ProcessView({ process, events }: { process?: JsonRecord[]; events?: string[] }) {
  if (events?.length) return <div className={styles.trace}>
    <strong>分析过程</strong>
    {events.map((item, index) => <span key={`${item}-${index}`}><i />{item}</span>)}
  </div>;
  if (!process?.length) return null;
  return <details className={styles.processPanel}>
    <summary>分析过程</summary>
    <ol>{process.map((item, index) => <li key={index}>
      <strong>{String(item.title ?? item.type ?? "执行步骤")}</strong>
      {formatProcessDetail(item) && <p>{formatProcessDetail(item)}</p>}
      {Array.isArray(item.calls) && <div className={styles.processCalls}>{item.calls.map((call: JsonRecord, callIndex: number) => <span key={callIndex}>{String(call.interfaceCode)} · {String(call.purpose ?? "接口调用")}</span>)}</div>}
      {Boolean(item.params) && <pre>{JSON.stringify(item.params, null, 2)}</pre>}
    </li>)}</ol>
  </details>;
}

type AnswerViewProps = {
  payload?: AnswerPayload;
  content: string;
  traceEvents?: string[];
  onSuggestion: (value: string) => void;
  onFeedback: (reason: string) => Promise<void>;
};

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("浏览器未允许访问剪贴板");
}

export function AnswerView({ payload, content, traceEvents, onSuggestion, onFeedback }: AnswerViewProps) {
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [actionNotice, setActionNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const table = payload?.table;
  const statsSummary = dataStatsSummary(payload);
  const structured = payload && payload.type === "structuredAnswer";
  const canAct = structured ? Boolean(payload) : !!content.trim();

  async function copyAnswer() {
    setActionError("");
    try {
      await copyText(answerTextForCopy(payload, content));
      setActionNotice("回答已复制");
    } catch (cause) {
      setActionNotice("");
      setActionError(cause instanceof Error ? cause.message : "复制失败，请重试");
    }
  }

  async function submitFeedback() {
    const value = reason.trim();
    if (!value || submitting) return;
    setSubmitting(true);
    setActionError("");
    try {
      await onFeedback(value);
      setFeedbackOpen(false);
      setReason("");
      setActionNotice("反馈已提交");
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "反馈提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.answerRoot}>
      {structured ? <div className={styles.structured}>
        <ProcessView process={payload.process} events={traceEvents} />
        {!!payload.dataFindings?.length && <div><h3>数据发现</h3><ul>{payload.dataFindings.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
        {table && table.rows.length > 0 && <div><h3>数据表格</h3><div className="table-wrap"><table><thead><tr>{table.columns.map((col) => <th key={col.field}>{col.label}{col.unit ? `（${col.unit}）` : ""}</th>)}</tr></thead><tbody>{table.rows.map((row: JsonRecord, index) => <tr key={index}>{table.columns.map((col) => <td key={col.field}>{cell(row[col.field])}</td>)}</tr>)}</tbody></table></div></div>}
        {statsSummary.length > 0 && <div><h3>数据统计结果总结</h3><div className={styles.statsSummary}><ul>{statsSummary.map((item) => <li key={item}>{item}</li>)}</ul></div></div>}
        {payload.visualization && <div><h3>数据可视化</h3><ChartBlock chart={payload.visualization} /></div>}
      </div> : <><ProcessView process={payload?.process} events={traceEvents} />{!!content.trim() && <p className={styles.answerText}>{content}</p>}</>}
      {canAct && <div className={styles.answerActions}>
        <button type="button" onClick={copyAnswer} title="复制回答"><CopyFilled /><span>复制回答</span></button>
        <button type="button" onClick={() => { setActionError(""); setFeedbackOpen(true); }} title="反馈不准确"><MehFilled /><span>反馈不准确</span></button>
        <span className={styles.actionNotice} role="status" aria-live="polite">{actionNotice}</span>
      </div>}
      {actionError && !feedbackOpen && <div className={styles.actionError}>{actionError}</div>}
      {structured && !!payload.nextSuggestions?.length && <div className={styles.suggestions}>{payload.nextSuggestions.map((item) => <button key={item} onClick={() => onSuggestion(item)}>{item}</button>)}</div>}
      {feedbackOpen && <div className={styles.feedbackOverlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !submitting) setFeedbackOpen(false); }}>
        <section className={styles.feedbackDialog} role="dialog" aria-modal="true" aria-labelledby="answer-feedback-title">
          <header><div><h2 id="answer-feedback-title">反馈不准确</h2><p>请说明本次 Agent 回复存在的问题，提交后可在回复校对中跟进。</p></div><button type="button" className={styles.dialogClose} aria-label="关闭" onClick={() => setFeedbackOpen(false)}>×</button></header>
          <div className={styles.feedbackBody}>
            <label htmlFor="answer-feedback-reason">反馈原因 <b>*</b></label>
            <textarea id="answer-feedback-reason" autoFocus maxLength={1000} value={reason} onChange={(event) => { setReason(event.target.value); setActionError(""); }} placeholder="例如：统计口径不正确，收入金额应包含……" />
            <div className={styles.feedbackMeta}><span>{reason.length}/1000</span></div>
            {actionError && <div className={styles.actionError}>{actionError}</div>}
          </div>
          <footer><button type="button" className={styles.cancelAction} onClick={() => setFeedbackOpen(false)} disabled={submitting}>取消</button><button type="button" className={styles.submitAction} onClick={submitFeedback} disabled={submitting || !reason.trim()}>{submitting ? "提交中…" : "提交反馈"}</button></footer>
        </section>
      </div>}
    </div>
  );
}
