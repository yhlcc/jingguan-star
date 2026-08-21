import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
// import { Button } from "../../components/ui/Button";
import { SettingFilled } from '@ant-design/icons'; 
import { Button, Switch } from 'antd';
import { api } from "../../services/api";
import type { AppConfig, LlmConfig } from "../../types/api";
import styles from "./SettingsPage.module.css";

type Panel = "greeting" | "suggestions" | "frequent" | "model";

// function Switch({ checked, label, onChange }: { checked: boolean; label: string; onChange: () => void }) {
//   return <Button type="p" role="switch" aria-checked={checked} aria-label={label} className={`${styles.toggle} ${checked ? styles.toggleOn : ""}`} onClick={onChange}><span /></button>;
// }

export function SettingsPage() {
  const client = useQueryClient();
  const appQuery = useQuery({ queryKey: ["app-config"], queryFn: () => api.get<AppConfig>("/api/app-config") });
  const llmQuery = useQuery({ queryKey: ["llm-config"], queryFn: () => api.get<LlmConfig>("/api/llm-config") });
  const [app, setApp] = useState<AppConfig>();
  const [llm, setLlm] = useState<LlmConfig>();
  const [panel, setPanel] = useState<Panel>();
  const [notice, setNotice] = useState("");
  useEffect(() => { if (appQuery.data) setApp({ ...appQuery.data, greetingEnabled: appQuery.data.greetingEnabled ?? true, frequentThreshold: appQuery.data.frequentThreshold ?? 3 }); }, [appQuery.data]);
  useEffect(() => { if (llmQuery.data) setLlm(llmQuery.data); }, [llmQuery.data]);

  const saveApp = useMutation({
    mutationFn: (value: AppConfig) => api.put<AppConfig>("/api/app-config", value),
    onSuccess: (value) => { setApp(value); client.setQueryData(["app-config"], value); setPanel(undefined); setNotice("应用配置已保存，并同步到智能问数对话框"); },
  });
  const saveLlm = useMutation({
    mutationFn: (value: LlmConfig) => api.put<LlmConfig>("/api/llm-config", value),
    onSuccess: (value) => { setLlm(value); client.setQueryData(["llm-config"], value); setPanel(undefined); setNotice("模型配置已保存"); },
  });

  if (appQuery.isLoading || llmQuery.isLoading || !app || !llm) return <div className="empty">正在读取应用配置…</div>;
  if (appQuery.error || llmQuery.error) return <div className="error">{(appQuery.error ?? llmQuery.error)?.message}</div>;

  const provider = llm.providerOptions[llm.provider];
  const updateToggle = (next: AppConfig) => { setApp(next); setNotice(""); saveApp.mutate(next); };
  const closePanel = () => { setPanel(undefined); if (appQuery.data) setApp(appQuery.data); if (llmQuery.data) setLlm(llmQuery.data); };
  const addQuestion = () => { if (app.openingQuestions.length < 10) setApp({ ...app, openingQuestions: [...app.openingQuestions, ""] }); };
  const updateQuestion = (index: number, value: string) => setApp({ ...app, openingQuestions: app.openingQuestions.map((item, i) => i === index ? value : item) });
  const removeQuestion = (index: number) => setApp({ ...app, openingQuestions: app.openingQuestions.filter((_, i) => i !== index) });

  return <div className={styles.page}>
    <div className={styles.breadcrumb}>系统管理 <span>/</span> <b>应用配置</b></div>
    {notice && <div className={styles.notice}>✓ {notice}</div>}
    <section className={styles.configSurface}>
      <div className={styles.configGrid}>
        <article className={styles.configCard}>
          <div className={styles.cardTop}><i className={`${styles.cardIcon} ${styles.blue}`}>✦</i><strong>对话开场白</strong><div className={styles.cardActions}><SettingFilled onClick={() => setPanel("greeting")} /><Switch checked={app.greetingEnabled} onChange={() => updateToggle({ ...app, greetingEnabled: !app.greetingEnabled })}/></div></div>
          <p>开启后，新对话将展示欢迎语和开场问题，引导用户快速开始问数。</p>
        </article>
        <article className={styles.configCard}>
          <div className={styles.cardTop}><i className={`${styles.cardIcon} ${styles.amber}`}>☷</i><strong>下一步问题建议</strong><div className={styles.cardActions}><SettingFilled onClick={() => setPanel("suggestions")} /><Switch checked={app.nextSuggestionsEnabled} onChange={() => updateToggle({ ...app, nextSuggestionsEnabled: !app.nextSuggestionsEnabled })}/></div></div>
          <p>开启后，AI 回复下方自动生成 {app.nextSuggestionsCount} 条相关延伸问题。</p>
        </article>
        <article className={styles.configCard}>
          <div className={styles.cardTop}><i className={`${styles.cardIcon} ${styles.violet}`}>◆</i><strong>模型配置</strong><div className={styles.cardActions}><SettingFilled onClick={() => setPanel("model")} /></div></div>
          <p>当前使用 {provider?.label ?? llm.provider} · {llm.modelName}，用于智能问数和经营数据分析。</p>
        </article>
        <article className={styles.configCard}>
          <div className={styles.cardTop}><i className={`${styles.cardIcon} ${styles.orange}`}>♨</i><strong>常问设置</strong><div className={styles.cardActions}><SettingFilled onClick={() => setPanel("frequent")} /><Switch checked={app.frequentEnabled} onChange={() => updateToggle({ ...app, frequentEnabled: !app.frequentEnabled })}/></div></div>
          <p>同一问题连续出现 {app.frequentThreshold} 次后进入常问列表，并在对话框中提供快捷入口。</p>
        </article>
      </div>
    </section>

    {panel && <div className={styles.overlay} onMouseDown={(event) => { if (event.target === event.currentTarget) closePanel(); }}>
      <section className={styles.modal} role="dialog" aria-modal="true">
        <header><h2>{panel === "greeting" ? "✦ 对话开场白" : panel === "frequent" ? "♨ 常问设置" : panel === "suggestions" ? "☷ 下一步问题建议" : "◆ 模型配置"}</h2><button className={styles.close} onClick={closePanel}>×</button></header>
        <div className={styles.modalBody}>
          {panel === "greeting" && <div className={styles.formGrid}>
            <div className="field"><label>开场白文案</label><textarea className="textarea" maxLength={240} value={app.openingGreeting} placeholder="请输入欢迎开场白…" onChange={(event) => setApp({ ...app, openingGreeting: event.target.value })}/><small>{app.openingGreeting.length}/240</small></div>
            <div className={styles.questionHeader}><label>开场问题 · {app.openingQuestions.length}/10</label><button onClick={addQuestion} disabled={app.openingQuestions.length >= 10}>＋ 添加开场问题</button></div>
            <div className={styles.questions}>{app.openingQuestions.map((question, index) => <div key={index}><input className="input" maxLength={120} value={question} placeholder="请输入快捷问题" onChange={(event) => updateQuestion(index, event.target.value)}/><button title="删除" onClick={() => removeQuestion(index)}>×</button></div>)}</div>
          </div>}
          {panel === "frequent" && <div className={styles.formGrid}><div className="field"><label>问题频次阈值</label><div className={styles.threshold}><input className="input" type="number" min="1" max="20" value={app.frequentThreshold} onChange={(event) => setApp({ ...app, frequentThreshold: Number(event.target.value) })}/><span>次（同一问题连续出现达到此值即视为常问）</span></div></div><div className={styles.tip}>当前已收录 {app.frequentQuestions.length} 个常问问题。关闭常问功能后将停止统计，并从对话框隐藏常问入口。</div></div>}
          {panel === "suggestions" && <div className={styles.formGrid}><div className="field"><label>每次生成的建议数量</label><input className="input" type="number" min="1" max="6" value={app.nextSuggestionsCount} onChange={(event) => setApp({ ...app, nextSuggestionsCount: Number(event.target.value) })}/></div><div className={styles.tip}>建议问题由 Agent 根据本轮问题、回答和数据动态生成。</div></div>}
          {panel === "model" && <div className={styles.formGrid}>
            <div className="field"><label>模型服务</label><select className="select" value={llm.provider} onChange={(event) => { const name = event.target.value as LlmConfig["provider"]; const meta = llm.providerOptions[name]; setLlm({ ...llm, provider: name, baseUrl: meta.baseUrl, modelName: meta.models[0] }); }}><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option></select></div>
            <div className="field"><label>Base URL</label><input className="input" value={llm.baseUrl} onChange={(event) => setLlm({ ...llm, baseUrl: event.target.value })}/></div>
            <div className="field"><label>模型</label><select className="select" value={llm.modelName} onChange={(event) => setLlm({ ...llm, modelName: event.target.value })}>{provider?.models.map((model) => <option key={model}>{model}</option>)}</select></div>
            <div className="field"><label>API Key {llm.hasApiKey && "（已配置）"}</label><input className="input" type="password" value={llm.apiKey} placeholder="保留空值则继续使用原密钥" onChange={(event) => setLlm({ ...llm, apiKey: event.target.value })}/></div>
            <div className={styles.twoCols}><div className="field"><label>Temperature</label><input className="input" type="number" min="0" max="2" step="0.1" value={llm.temperature} onChange={(event) => setLlm({ ...llm, temperature: Number(event.target.value) })}/></div><div className="field"><label>最大输出 Token</label><input className="input" type="number" min="256" max="16384" value={llm.maxOutputTokens} onChange={(event) => setLlm({ ...llm, maxOutputTokens: Number(event.target.value) })}/></div></div>
          </div>}
          {(saveApp.error || saveLlm.error) && <div className="error">{(saveApp.error ?? saveLlm.error)?.message}</div>}
        </div>
        <footer><Button onClick={closePanel}>取消</Button><Button disabled={saveApp.isPending || saveLlm.isPending || (panel === "greeting" && !app.openingGreeting.trim())} onClick={() => panel === "model" ? saveLlm.mutate(llm) : saveApp.mutate({ ...app, openingQuestions: app.openingQuestions.map((item) => item.trim()).filter(Boolean) })}>{saveApp.isPending || saveLlm.isPending ? "保存中…" : "保存"}</Button></footer>
      </section>
    </div>}
  </div>;
}
