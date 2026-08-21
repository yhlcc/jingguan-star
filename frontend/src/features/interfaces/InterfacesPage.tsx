import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { StatusPill } from "../../components/ui/StatusPill";
import { api } from "../../services/api";
import type { QueryInterface } from "../../types/api";
import styles from "./InterfacesPage.module.css";

const defaultParams = [
  { name: "year", type: "int", required: false, defaultValue: "2026", description: "年份" },
];

const defaultFields = [
  { name: "metric", label: "指标", type: "string", unit: "", sensitiveLevel: "internal", description: "指标名称" },
  { name: "value", label: "数值", type: "decimal", unit: "万元", sensitiveLevel: "internal", description: "指标值" },
];

const emptyInterface = {
  __new: true,
  interfaceCode: "",
  interfaceName: "",
  groupName: "自定义接口",
  method: "POST",
  path: "",
  ownerDept: "经营管理部",
  description: "",
  params: defaultParams,
  fields: defaultFields,
  status: "启用",
  approvalPolicy: "none",
};

function approvalPolicyText(value: unknown): string {
  return value === "manual" ? "调用前审批" : "无需审批";
}

function ApprovalPolicyBadge({ value }: { value: unknown }) {
  const manual = value === "manual";
  return <span className={`${styles.policyBadge} ${manual ? styles.policyManual : ""}`}>{approvalPolicyText(value)}</span>;
}

function formatSpec(value: unknown): string {
  return JSON.stringify(Array.isArray(value) ? value : [], null, 2);
}

function parseSpec(text: string, label: string): unknown[] {
  const parsed = JSON.parse(text);
  if (!Array.isArray(parsed) || parsed.length === 0) {
    throw new Error(`${label}必须是非空数组`);
  }
  return parsed;
}

export function InterfacesPage() {
  const client = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);
  const [paramsText, setParamsText] = useState(formatSpec(defaultParams));
  const [fieldsText, setFieldsText] = useState(formatSpec(defaultFields));
  const [specError, setSpecError] = useState("");
  const query = useQuery({ queryKey: ["interfaces", keyword], queryFn: () => api.get<{ items: QueryInterface[] }>(`/api/query-interfaces?keyword=${encodeURIComponent(keyword)}`) });
  const toggle = useMutation({ mutationFn: (item: QueryInterface) => api.patch(`/api/query-interfaces/${item.interfaceCode}/status`, { status: item.status === "启用" ? "停用" : "启用" }), onSuccess: () => client.invalidateQueries({ queryKey: ["interfaces"] }) });
  const save = useMutation({ mutationFn: (form: Record<string, unknown>) => {
    const code = String(form.interfaceCode ?? "").trim();
    const path = String(form.path ?? "").trim() || `/api/ai-query/${code}`;
    return form.__new ? api.post("/api/query-interfaces", { ...form, interfaceCode: code, path }) : api.put(`/api/query-interfaces/${code}`, { ...form, path });
  }, onSuccess: () => { setEditing(null); client.invalidateQueries({ queryKey: ["interfaces"] }); } });
  function openCreate() {
    setSelected(null);
    setEditing({ ...emptyInterface });
    setParamsText(formatSpec(defaultParams));
    setFieldsText(formatSpec(defaultFields));
    setSpecError("");
  }
  async function detail(code: string) { setSelected(await api.get<Record<string, unknown>>(`/api/query-interfaces/${code}`)); }
  async function edit(code: string) {
    const item = await api.get<Record<string, unknown>>(`/api/query-interfaces/${code}`);
    setEditing(item);
    setParamsText(formatSpec(item.params));
    setFieldsText(formatSpec(item.fields));
    setSpecError("");
  }
  const setField = (name: string, value: unknown) => setEditing((current) => current ? { ...current, [name]: value } : current);
  function submit() {
    if (!editing) return;
    try {
      const params = parseSpec(paramsText, "入参格式 params");
      const fields = parseSpec(fieldsText, "出参格式 fields");
      setSpecError("");
      save.mutate({ ...editing, params, fields });
    } catch (error) {
      setSpecError(error instanceof Error ? error.message : "入参或出参 JSON 格式不正确");
    }
  }
  return <div className="page">
    <div className="page-heading"><div><h1>问数接口管理</h1><p>模型只允许规划并调用这里登记且启用的受控接口</p></div><div className="toolbar"><input className="input" placeholder="搜索编码、名称或路径" value={keyword} onChange={(event) => setKeyword(event.target.value)} /><Button onClick={openCreate}>＋ 新建接口</Button></div></div>
    {query.error && <div className="error">{query.error.message}</div>}
    <Card>
        <div className="table-wrap"><table><thead><tr><th>接口</th><th>分组</th><th>路径</th><th>参数 / 字段</th><th>审批策略</th><th>状态</th><th>操作</th></tr></thead><tbody>{query.data?.items.map((item) => <tr key={item.interfaceCode}><td><strong>{item.interfaceName}</strong><div className="muted">{item.interfaceCode}</div></td><td>{item.groupName}</td><td><code>{item.method} {item.path}</code></td><td>{item.paramCount} 个参数<div className="muted">{item.fields}</div></td><td><ApprovalPolicyBadge value={item.approvalPolicy} /></td><td><StatusPill status={item.status} /></td><td><div className="toolbar"><Button variant="ghost" onClick={() => detail(item.interfaceCode)}>详情</Button><Button variant="ghost" onClick={() => edit(item.interfaceCode)}>编辑</Button><Button variant="secondary" onClick={() => toggle.mutate(item)}>{item.status === "启用" ? "停用" : "启用"}</Button></div></td></tr>)}</tbody></table></div>
    </Card>
    {selected && <Card title={String(selected.interfaceName ?? "接口详情")} extra={<Button variant="ghost" onClick={() => setSelected(null)}>关闭</Button>}><div className="grid cols-2"><div><p><b>接口编码：</b>{String(selected.interfaceCode)}</p><p><b>审批策略：</b>{approvalPolicyText(selected.approvalPolicy)}</p><p><b>安全策略：</b>{String(selected.securityPolicy ?? "-")}</p><p><b>限流：</b>{String(selected.rateLimitPolicy ?? "-")}</p></div><pre style={{ margin: 0, padding: 14, borderRadius: 10, overflow: "auto", background: "#f5f7fb" }}>{JSON.stringify({ params: selected.params, fields: selected.fields }, null, 2)}</pre></div></Card>}
    {editing && <div className={styles.overlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditing(null); }}>
      <section className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="interface-dialog-title">
        <header><div><h2 id="interface-dialog-title">{editing.__new ? "新建受控接口" : "编辑接口"}</h2><p>登记接口基础信息，保存后会立即出现在接口目录中。</p></div><button className={styles.close} onClick={() => setEditing(null)} aria-label="关闭">×</button></header>
        <form onSubmit={(event) => { event.preventDefault(); submit(); }}>
          <div className="grid cols-2">
            <div className="field"><label>接口编码 *</label><input autoFocus className="input" required disabled={!editing.__new} value={String(editing.interfaceCode ?? "")} onChange={(e) => setField("interfaceCode", e.target.value)} placeholder="例如 biz.sales.query" /></div>
            <div className="field"><label>接口名称 *</label><input className="input" required value={String(editing.interfaceName ?? "")} onChange={(e) => setField("interfaceName", e.target.value)} placeholder="例如 销售数据查询" /></div>
            <div className="field"><label>接口分组</label><input className="input" value={String(editing.groupName ?? "")} onChange={(e) => setField("groupName", e.target.value)} /></div>
            <div className="field"><label>责任部门</label><input className="input" value={String(editing.ownerDept ?? "")} onChange={(e) => setField("ownerDept", e.target.value)} /></div>
            <div className="field"><label>HTTP 方法</label><select className="select" value={String(editing.method ?? "POST")} onChange={(e) => setField("method", e.target.value)}><option>GET</option><option>POST</option></select></div>
            <div className="field"><label>路径</label><input className="input" value={String(editing.path ?? "")} onChange={(e) => setField("path", e.target.value)} placeholder="留空时按接口编码自动生成" /></div>
            <div className="field"><label>审批策略</label><select className="select" value={String(editing.approvalPolicy ?? "none")} onChange={(e) => setField("approvalPolicy", e.target.value)}><option value="none">无需审批</option><option value="manual">调用前审批</option></select></div>
          </div>
          <div className="field" style={{ marginTop: 14 }}><label>接口说明</label><textarea className="textarea" value={String(editing.description ?? "")} onChange={(e) => setField("description", e.target.value)} placeholder="说明接口用途和可查询的数据范围" /></div>
          <div className={styles.specGrid}>
            <div className="field"><label>入参格式 params *</label><textarea className={`textarea ${styles.codeEditor}`} required value={paramsText} onChange={(e) => { setParamsText(e.target.value); setSpecError(""); }} /></div>
            <div className="field"><label>出参格式 fields *</label><textarea className={`textarea ${styles.codeEditor}`} required value={fieldsText} onChange={(e) => { setFieldsText(e.target.value); setSpecError(""); }} /></div>
          </div>
          {(specError || save.error) && <div className="error" style={{ marginTop: 14 }}>{specError || save.error?.message}</div>}
          <footer><Button type="button" variant="ghost" onClick={() => setEditing(null)}>取消</Button><Button type="submit" disabled={save.isPending || !String(editing.interfaceCode ?? "").trim() || !String(editing.interfaceName ?? "").trim()}>{save.isPending ? "保存中…" : "保存接口"}</Button></footer>
        </form>
      </section>
    </div>}
  </div>;
}
