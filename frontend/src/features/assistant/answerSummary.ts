import type { AnswerPayload, JsonRecord } from "../../types/api";

function formatNumber(value: unknown): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(number);
}

export function dataStatsSummary(payload?: AnswerPayload): string[] {
  if (!payload || payload.type !== "structuredAnswer") return [];
  const lines = [`总记录数：${payload.table?.totalRows ?? payload.stats?.rowCount ?? 0} 条`];
  const numeric = (payload.stats?.numeric ?? []) as JsonRecord[];
  for (const metric of numeric) {
    const label = String(metric.label ?? metric.field ?? "数值指标");
    const unit = String(metric.unit ?? "");
    const total = unit === "%" ? "" : `合计 ${formatNumber(metric.sum)}${unit}，`;
    lines.push(`${label}：${total}平均 ${formatNumber(metric.avg)}${unit}，最大 ${formatNumber(metric.max)}${unit}，最小 ${formatNumber(metric.min)}${unit}`);
  }
  const derived = (payload.stats?.derived ?? payload.derivedMetrics?.items ?? []) as JsonRecord[];
  for (const metric of derived.slice(0, 6)) {
    const label = String(metric.label ?? metric.name ?? "派生指标");
    const unit = String(metric.unit ?? "");
    const dimension = metric.dimension ? `（${String(metric.dimension)}）` : "";
    lines.push(`${label}${dimension}：${formatNumber(metric.value)}${unit}`);
  }
  if (numeric.length === 0 && derived.length === 0) lines.push("当前结果无可统计的数值指标。");
  return lines;
}

export function dataStatsSummaryText(payload?: AnswerPayload): string {
  return dataStatsSummary(payload).map((line) => `• ${line.trim()}`).join("\n");
}

function displayCell(value: unknown): string {
  return typeof value === "object" ? JSON.stringify(value) : String(value ?? "-");
}

function visualizationText(payload: AnswerPayload): string {
  const chart = payload.visualization;
  if (!chart) return "";
  const lines = [chart.title || "数据可视化"];
  if (chart.series?.length) {
    for (const series of chart.series) {
      lines.push(`${series.name}：${series.data.map((item) => `${item.label} ${formatNumber(item.value)}${series.unit || ""}`).join("；")}`);
    }
  } else if (chart.data?.length) {
    lines.push(chart.data.map((item) => `${item.label} ${formatNumber(item.value)}${chart.unit || ""}`).join("；"));
  } else if (chart.charts?.length) {
    for (const item of chart.charts) {
      lines.push(item.title || "图表");
      if (item.data?.length) lines.push(item.data.map((point) => `${point.label} ${formatNumber(point.value)}${item.unit || ""}`).join("；"));
    }
  }
  return lines.join("\n");
}

export function answerTextForCopy(payload: AnswerPayload | undefined, content: string): string {
  if (!payload || payload.type === "directAnswer") return content.trim();
  const sections: string[] = [];
  if (payload.dataFindings?.length) sections.push(`数据发现\n${payload.dataFindings.map((item) => `• ${item}`).join("\n")}`);
  if (payload.table?.rows.length) {
    const headers = payload.table.columns.map((column) => `${column.label}${column.unit ? `（${column.unit}）` : ""}`);
    const rows = payload.table.rows.map((row) => payload.table!.columns.map((column) => displayCell(row[column.field])).join("\t"));
    sections.push(`数据表格\n${[headers.join("\t"), ...rows].join("\n")}`);
  }
  const stats = dataStatsSummaryText(payload);
  if (stats) sections.push(`数据统计结果总结\n${stats}`);
  const chart = visualizationText(payload);
  if (chart) sections.push(`数据可视化\n${chart}`);
  return sections.join("\n\n") || content.trim();
}
