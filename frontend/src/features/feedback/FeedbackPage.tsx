import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { StatusPill } from "../../components/ui/StatusPill";
import { api } from "../../services/api";
import type { FeedbackRecord } from "../../types/api";
import styles from "./FeedbackPage.module.css";

function summaryOnly(value: string): string {
  const text = value.trim();
  if (!text) return "暂无数据结果总结";
  if (text.startsWith("•") || text.startsWith("总记录数：")) return text;
  const marker = text.includes("## 数据统计结果总结") ? "## 数据统计结果总结" : "## 数据统计";
  const start = text.indexOf(marker);
  if (start >= 0) {
    const content = text.slice(start + marker.length).trim();
    return content.split("\n## ")[0].trim() || "暂无数据结果总结";
  }
  return "历史反馈未保存数据统计结果总结。";
}

export function FeedbackPage() {
  const client = useQueryClient();
  const [selected, setSelected] = useState<FeedbackRecord>();
  const [status, setStatus] = useState("待处理");
  const [remark, setRemark] = useState("");
  const query = useQuery({ queryKey: ["feedback"], queryFn: () => api.get<{ items: FeedbackRecord[] }>("/api/qa/feedback") });
  const update = useMutation({ mutationFn: ({ id, nextStatus, handlerRemark }: { id: number; nextStatus: string; handlerRemark: string }) => api.patch(`/api/qa/feedback/${id}`, { status: nextStatus, handlerName: "经营管理部", handlerRemark }), onSuccess: () => { client.invalidateQueries({ queryKey: ["feedback"] }); setSelected(undefined); } });
  const openFeedback = (item: FeedbackRecord) => {
    setSelected(item);
    setStatus(item.status || "待处理");
    setRemark(item.handlerRemark || "");
  };
  return <div className="page">
    <div className="page-heading"><div><h1>回复校对</h1><p>把业务人员反馈转化为可追踪的 Agent 质量闭环</p></div></div>
    {query.error && <div className="error">{query.error.message}</div>}
    <Card><div className="table-wrap"><table><thead><tr><th>用户提问</th><th>AI 数据结果总结</th><th>反馈原因</th><th>提交时间</th><th>状态</th><th /></tr></thead><tbody>{query.data?.items.map((item) => <tr key={item.id} className={styles.row} tabIndex={0} onClick={() => openFeedback(item)} onKeyDown={(event) => { if (event.key === "Enter") openFeedback(item); }}><td><strong>{item.question || "未关联问题"}</strong></td><td><div className={styles.snippet}>{summaryOnly(item.answerSnippet)}</div></td><td><div className={styles.feedbackReason}>{item.reason || "未填写反馈原因"}</div></td><td>{item.createdAt}</td><td><StatusPill status={item.status} /></td><td><Button variant="ghost" onClick={(event) => { event.stopPropagation(); openFeedback(item); }}>处理</Button></td></tr>)}</tbody></table></div>{query.data?.items.length === 0 && <div className="empty">暂无待校对反馈</div>}</Card>
    {selected && <div className={styles.overlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(undefined); }}>
      <section className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="feedback-dialog-title">
        <header><h2 id="feedback-dialog-title">反馈处理</h2><button className={styles.close} onClick={() => setSelected(undefined)} aria-label="关闭">×</button></header>
        <div className={styles.dialogBody}>
          <div className={styles.context}>
            <div><label>用户提问</label><div className={styles.question}>{selected.question || "未关联问题"}</div></div>
            <div><label>AI 回复（数据结果总结）</label><div className={styles.answer}>{summaryOnly(selected.answerSnippet)}</div></div>
            <div><label>用户反馈</label><div className={styles.reason}>{selected.reason || "未填写反馈原因"}</div></div>
          </div>
          <div className={styles.handleForm}>
            <div className="field"><label>处理状态</label><select className="select" value={status} onChange={(event) => setStatus(event.target.value)}>{["待处理", "处理中", "已处理", "已关闭"].map((item) => <option key={item}>{item}</option>)}</select></div>
            <div className="field"><label>处理备注</label><textarea autoFocus className="textarea" value={remark} onChange={(event) => setRemark(event.target.value)} placeholder="请填写核查结论或后续处理说明…" /></div>
            {update.error && <div className="error">{update.error.message}</div>}
          </div>
        </div>
        <footer><Button variant="ghost" onClick={() => setSelected(undefined)}>取消</Button><Button onClick={() => update.mutate({ id: selected.id, nextStatus: status, handlerRemark: remark })} disabled={update.isPending}>{update.isPending ? "保存中…" : "确认处理"}</Button></footer>
      </section>
    </div>}
  </div>;
}
