import { useQuery } from "@tanstack/react-query";
import { Card, MetricCard } from "../../components/ui/Card";
import { EChart } from "../../components/charts/EChart";
import { categoryChart } from "../../components/charts/chartOptions";
import { api } from "../../services/api";
import type { DashboardData } from "../../types/api";

const number = (value?: number) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value ?? 0);

export function DashboardPage() {
  const query = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<DashboardData>("/api/dashboard?year=2026") });
  const data = query.data;
  if (query.isLoading) return <div className="empty">正在汇总经营数据…</div>;
  if (query.error) return <div className="error">{query.error.message}</div>;
  const summary = data?.summary ?? {};
  const units = data?.charts?.unitRank ?? [];
  const industries = data?.charts?.industryTop ?? [];
  const products = data?.charts?.productLineMix ?? [];
  return (
    <div className="page">
      <div className="page-heading"><div><h1>经营驾驶舱</h1><p>截至 2026 年 5 月 · 目标、收入与风险的统一视图</p></div><span className="muted">数据口径：万元</span></div>
      <div className="grid cols-4">
        <MetricCard label="年度经营目标" value={number(summary.totalTargetAmount)} suffix="万元" hint="年度目标基线" />
        <MetricCard label="累计确认收入" value={number(summary.totalIncomeAmount)} suffix="万元" tone="green" hint={`完成率 ${number(summary.completionRate)}%`} />
        <MetricCard label="收入同比" value={number(summary.yoyRate)} suffix="%" tone={Number(summary.yoyRate) >= 0 ? "green" : "red"} hint="较上年同期" />
        <MetricCard label="高风险商机" value={number(summary.riskProjectCount)} suffix="个" tone="amber" hint="需重点推进" />
      </div>
      <div className="grid cols-2">
        <Card title="经营单元收入排名" extra={<span className="muted">TOP {units.length}</span>}><EChart option={categoryChart(units)} height={330} /></Card>
        <Card title="重点行业收入"><EChart option={categoryChart(industries)} height={330} /></Card>
      </div>
      <Card title="产品线结构">
        <EChart height={280} option={{ color: ["#315efb", "#24a6a4", "#ed9b32"], tooltip: { trigger: "item" }, legend: { bottom: 0 }, series: [{ type: "pie", radius: ["45%", "72%"], data: products, itemStyle: { borderColor: "#fff", borderWidth: 4 } }] }} />
      </Card>
    </div>
  );
}
