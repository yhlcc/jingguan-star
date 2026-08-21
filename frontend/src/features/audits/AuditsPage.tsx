import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Card, MetricCard } from "../../components/ui/Card";
import { StatusPill } from "../../components/ui/StatusPill";
import { api } from "../../services/api";
import type { AuditRecord } from "../../types/api";

export function AuditsPage() {
  const [detail, setDetail] = useState<AuditRecord>();
  const query = useQuery({ queryKey: ["audits"], queryFn: () => api.get<{ items: AuditRecord[] }>("/api/audits?pageSize=100") });
  const items = query.data?.items ?? [];
  const success = items.filter((x) => x.status === "成功").length;
  const avg = items.length ? Math.round(items.reduce((sum, x) => sum + (x.durationMs ?? 0), 0) / items.length) : 0;
  async function open(id: number) { setDetail(await api.get<AuditRecord>(`/api/audits/${id}`)); }
  return <div className="page">
    <div className="page-heading"><div><h1>调用审计</h1><p>追踪 Agent 规划后的每一次白名单接口执行</p></div></div>
    <div className="grid cols-4"><MetricCard label="审计调用" value={String(items.length)} suffix="次" /><MetricCard label="成功调用" value={String(success)} suffix="次" tone="green" /><MetricCard label="平均耗时" value={String(avg)} suffix="ms" tone="amber" /><MetricCard label="返回数据" value={String(items.reduce((sum, x) => sum + (x.responseRowCount ?? 0), 0))} suffix="行" /></div>
    {query.error && <div className="error">{query.error.message}</div>}
    <Card><div className="table-wrap"><table><thead><tr><th>时间</th><th>请求 ID</th><th>接口</th><th>行数</th><th>耗时</th><th>状态</th><th /></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.createdAt}</td><td><code>{item.requestId?.slice(0, 12)}</code></td><td>{item.interfaceCode}</td><td>{item.responseRowCount}</td><td>{item.durationMs} ms</td><td><StatusPill status={item.status} /></td><td><Button variant="ghost" onClick={() => open(item.id)}>查看</Button></td></tr>)}</tbody></table></div></Card>
    {detail && <Card title="审计详情" extra={<Button variant="ghost" onClick={() => setDetail(undefined)}>关闭</Button>}><pre style={{ whiteSpace: "pre-wrap", overflow: "auto" }}>{JSON.stringify(detail, null, 2)}</pre></Card>}
  </div>;
}
