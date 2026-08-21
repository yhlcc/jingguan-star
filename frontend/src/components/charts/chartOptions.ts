import type { EChartsOption } from "echarts";
import type { ChartPayload } from "../../types/api";

const palette = ["#315efb", "#24a6a4", "#ed9b32", "#8a63d2", "#dc5a64"];

export function categoryChart(data: Array<{ name: string; value: number }>, title?: string): EChartsOption {
  return { color: palette, title: title ? { text: title, textStyle: { fontSize: 13 } } : undefined, tooltip: { trigger: "axis" }, grid: { left: 20, right: 20, bottom: 15, top: title ? 45 : 20, containLabel: true }, xAxis: { type: "category", data: data.map((x) => x.name), axisLabel: { color: "#77869a" } }, yAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1f6" } } }, series: [{ type: "bar", data: data.map((x) => x.value), barMaxWidth: 30, itemStyle: { borderRadius: [6, 6, 0, 0] } }] };
}

export function payloadChart(chart: ChartPayload): EChartsOption {
  if (chart.series?.length) {
    const labels = chart.series[0]?.data.map((x) => x.label) ?? [];
    return { color: palette, tooltip: { trigger: "axis" }, legend: { top: 0 }, grid: { top: 45, left: 20, right: 20, bottom: 10, containLabel: true }, xAxis: { type: "category", data: labels }, yAxis: [{ type: "value" }, { type: "value" }], series: chart.series.map((s) => ({ name: s.name, type: s.chartType === "line" ? "line" : "bar", yAxisIndex: s.axisIndex ?? 0, data: s.data.map((x) => x.value), smooth: true })) };
  }
  const data = chart.data ?? [];
  if (chart.chartType === "pie") return { color: palette, tooltip: { trigger: "item" }, series: [{ type: "pie", radius: ["42%", "70%"], data: data.map((x) => ({ name: x.label, value: x.value })) }] };
  return categoryChart(data.map((x) => ({ name: x.label, value: x.value })), chart.title);
}
