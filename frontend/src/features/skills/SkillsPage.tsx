import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { StatusPill } from "../../components/ui/StatusPill";
import { api } from "../../services/api";
import type { AgentSkill } from "../../types/api";
import styles from "./SkillsPage.module.css";

const emptySkill = {
  skillCode: "custom.analysis.skill",
  skillName: "自定义经营分析 Skill",
  description: "描述这个 Skill 适合处理的经营分析目标。",
  instructions: [
    "当用户询问这个业务场景时，按下面流程执行：",
    "1. 先调用最能回答基础口径的原子接口，使用用户问题中的年份、经营单元、行业或产品作为参数。",
    "2. 如果后续接口需要前一步的返回值作为条件，明确写出从哪个结果字段提取，例如从 rows[].unitName 提取经营单元。",
    "3. 如果需要合并、筛选、排序或计算，写明按哪个字段关联、计算什么指标、如何排序和限制条数。",
    "4. 最后围绕数据发现、异常原因和建议动作组织回答。",
  ].join("\n"),
  triggerKeywords: ["目标", "分析"],
  steps: [],
  derivedMetrics: [],
  answerSections: ["数据发现", "建议动作"],
  status: "启用",
};

function skillJson(skill: Partial<AgentSkill> | typeof emptySkill): string {
  return JSON.stringify({
    skillCode: skill.skillCode,
    skillName: skill.skillName,
    description: skill.description,
    instructions: skill.instructions ?? "",
    triggerKeywords: skill.triggerKeywords ?? [],
    steps: skill.steps ?? [],
    derivedMetrics: skill.derivedMetrics ?? [],
    answerSections: skill.answerSections ?? [],
    status: skill.status ?? "启用",
  }, null, 2);
}

export function SkillsPage() {
  const client = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [selected, setSelected] = useState<AgentSkill | null>(null);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [editor, setEditor] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState(skillJson(emptySkill));
  const [error, setError] = useState("");
  const query = useQuery({ queryKey: ["agent-skills", keyword], queryFn: () => api.get<{ items: AgentSkill[] }>(`/api/agent-skills?keyword=${encodeURIComponent(keyword)}`) });
  const refresh = () => client.invalidateQueries({ queryKey: ["agent-skills"] });
  const toggle = useMutation({ mutationFn: (item: AgentSkill) => api.patch(`/api/agent-skills/${item.skillCode}/status`, { status: item.status === "启用" ? "停用" : "启用" }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (item: AgentSkill) => api.delete(`/api/agent-skills/${item.skillCode}`), onSuccess: refresh });
  const save = useMutation({ mutationFn: ({ value, create }: { value: Record<string, unknown>; create: boolean }) => create ? api.post("/api/agent-skills", value) : api.put(`/api/agent-skills/${String(value.skillCode)}`, value), onSuccess: () => { setEditingCode(null); refresh(); } });
  const importSkill = useMutation({ mutationFn: (value: Record<string, unknown>) => api.post("/api/agent-skills/import", value), onSuccess: () => { setImportOpen(false); refresh(); } });

  async function openDetail(code: string) {
    setSelected(await api.get<AgentSkill>(`/api/agent-skills/${code}`));
  }

  async function openEdit(code: string) {
    const detail = await api.get<AgentSkill>(`/api/agent-skills/${code}`);
    setEditingCode(code);
    setEditor(skillJson(detail));
    setError("");
  }

  function submitEditor() {
    try {
      const value = JSON.parse(editor) as Record<string, unknown>;
      save.mutate({ value, create: editingCode === "__new__" });
    } catch {
      setError("JSON 格式不正确，请检查逗号、引号和括号。");
    }
  }

  function submitImport() {
    try {
      importSkill.mutate(JSON.parse(importText) as Record<string, unknown>);
    } catch {
      setError("导入 JSON 格式不正确。");
    }
  }
  return <div className="page">
    <div className="page-heading"><div><h1>Agent Skill 管理</h1><p>维护经营分析目标的自然语言流程、触发词和派生指标</p></div><div className="toolbar"><input className="input" placeholder="搜索 Skill 编码、名称或说明" value={keyword} onChange={(event) => setKeyword(event.target.value)} /><Button onClick={() => { setEditingCode("__new__"); setEditor(skillJson(emptySkill)); }}>＋ 新建 Skill</Button><Button variant="secondary" onClick={() => setImportOpen(true)}>导入 JSON</Button></div></div>
    {(query.error || error || save.error || importSkill.error || remove.error) && <div className="error">{error || query.error?.message || save.error?.message || importSkill.error?.message || remove.error?.message}</div>}
    <Card>
      <div className="table-wrap"><table><thead><tr><th>Skill</th><th>触发词</th><th>编排</th><th>状态</th><th>操作</th></tr></thead><tbody>{query.data?.items?.map((item) => <tr key={item.skillCode}><td><strong>{item.skillName}</strong><div className="muted">{item.skillCode}</div><div className="muted">{item.description}</div></td><td><div className={styles.keywords}>{item.triggerKeywords.slice(0, 8).map((keyword) => <span key={keyword}>{keyword}</span>)}</div></td><td>{item.stepCount > 0 ? `${item.stepCount} 个结构化步骤` : item.instructions ? "自然语言流程" : "未配置"}</td><td><StatusPill status={item.status} /></td><td><div className={styles.actions}><Button variant="ghost" onClick={() => openDetail(item.skillCode)}>详情</Button><Button variant="ghost" onClick={() => openEdit(item.skillCode)}>编辑</Button><Button variant="secondary" onClick={() => toggle.mutate(item)}>{item.status === "启用" ? "停用" : "启用"}</Button><Button variant="ghost" onClick={() => remove.mutate(item)}>删除</Button></div></td></tr>)}</tbody></table></div>
    </Card>
    {selected && <Card title={selected.skillName} extra={<Button variant="ghost" onClick={() => setSelected(null)}>关闭</Button>}>
      <p className="muted">{selected.description}</p>
      <div className={styles.keywords}>{selected.triggerKeywords.map((keyword) => <span key={keyword}>{keyword}</span>)}</div>
      {selected.instructions && <div className={styles.step}><strong>自然语言流程</strong><pre>{selected.instructions}</pre></div>}
      <div className={styles.steps}>{selected.steps?.map((step, index) => <div className={styles.step} key={`${step.stepId || step.interfaceCode}-${index}`}><strong>{index + 1}. {step.purpose || "操作步骤"}</strong><code>{step.stepId || step.interfaceCode}</code><pre>{JSON.stringify(step, null, 2)}</pre></div>)}</div>
    </Card>}
    {editingCode && <div className={styles.overlay} onMouseDown={(event) => { if (event.target === event.currentTarget) setEditingCode(null); }}>
      <section className={styles.dialog} role="dialog" aria-modal="true">
        <header><div><h2>{editingCode === "__new__" ? "新建 Skill" : "编辑 Skill"}</h2><p>使用 JSON 维护触发词、自然语言流程和回答结构；steps 可留空由系统编译。</p></div><button className={styles.close} onClick={() => setEditingCode(null)}>×</button></header>
        <div className={styles.body}><textarea className={`textarea ${styles.codeEditor}`} value={editor} onChange={(event) => { setEditor(event.target.value); setError(""); }} /></div>
        <footer><Button variant="ghost" onClick={() => setEditingCode(null)}>取消</Button><Button onClick={submitEditor} disabled={save.isPending}>{save.isPending ? "保存中…" : "保存 Skill"}</Button></footer>
      </section>
    </div>}
    {importOpen && <div className={styles.overlay} onMouseDown={(event) => { if (event.target === event.currentTarget) setImportOpen(false); }}>
      <section className={styles.dialog} role="dialog" aria-modal="true">
        <header><div><h2>导入 Skill JSON</h2><p>支持单个 Skill JSON，或 {"{"}"skills": [...]{"}"} 批量导入。</p></div><button className={styles.close} onClick={() => setImportOpen(false)}>×</button></header>
        <div className={styles.body}><textarea className={`textarea ${styles.codeEditor}`} value={importText} onChange={(event) => { setImportText(event.target.value); setError(""); }} /></div>
        <footer><Button variant="ghost" onClick={() => setImportOpen(false)}>取消</Button><Button onClick={submitImport} disabled={importSkill.isPending}>{importSkill.isPending ? "导入中…" : "导入"}</Button></footer>
      </section>
    </div>}
  </div>;
}
