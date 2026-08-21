import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import styles from "./AppShell.module.css";

type IconName = "robot" | "dashboard" | "settings" | "feedback" | "interface" | "audit" | "skill" | "sliders" | "chevron" | "bell" | "collapse";

const iconPaths: Record<IconName, ReactNode> = {
  robot: <><path d="M12 2v3"/><rect x="4" y="7" width="16" height="12" rx="3"/><path d="M8 12h.01M16 12h.01M9 16h6M2 12h2M20 12h2"/></>,
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
  feedback: <><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z"/><path d="M8 9h8M8 13h5"/></>,
  interface: <><path d="M8 9 4 12l4 3M16 9l4 3-4 3M14 5l-4 14"/></>,
  audit: <><path d="M9 3h6l1 2h3v16H5V5h3Z"/><path d="M9 11h6M9 15h4"/></>,
  skill: <><path d="M12 3 4 7l8 4 8-4-8-4Z"/><path d="m4 12 8 4 8-4"/><path d="m4 17 8 4 8-4"/></>,
  sliders: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></>,
  chevron: <path d="m9 18 6-6-6-6"/>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
  collapse: <><path d="M15 18 9 12l6-6"/><path d="M4 4v16"/></>,
};

function Icon({ name }: { name: IconName }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true">{iconPaths[name]}</svg>;
}

const primaryItems = [
  { path: "/assistant", label: "智能问数", icon: "robot" as const },
];

const groups = [
  { id: "system", label: "系统管理", icon: "settings" as const, children: [
    { path: "/interfaces", label: "接口管理", icon: "interface" as const },
    { path: "/skills", label: "Skill 管理", icon: "skill" as const },
    // { path: "/audits", label: "调用审计", icon: "audit" as const },
    { path: "/settings", label: "应用配置", icon: "sliders" as const },
  ] },
  { id: "feedback", label: "反馈管理", icon: "feedback" as const, children: [
    { path: "/feedback", label: "回复校对", icon: "feedback" as const },
  ] },
];

export function AppShell() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [expanded, setExpanded] = useState(() => new Set(groups.filter((group) => group.children.some((item) => location.pathname.startsWith(item.path))).map((group) => group.id)));
  const toggleGroup = (id: string) => setExpanded((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  return (
    <div className={`${styles.shell} ${collapsed ? styles.shellCollapsed : ""}`}>
      <header className={styles.topbar}>
        <div className={styles.brand}><span className={styles.brandMark}>J</span><strong>经管之星 · AI问数</strong></div>
        <div className={styles.topActions}><button title="消息通知"><Icon name="bell"/><i /></button><span>经营管理部</span><b>管</b></div>
      </header>
      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <nav className={styles.nav}>
            {primaryItems.map((item) => <NavLink key={item.path} to={item.path} title={collapsed ? item.label : undefined} className={({ isActive }) => isActive ? styles.active : ""}><Icon name={item.icon}/><span>{item.label}</span></NavLink>)}
            {groups.map((group) => {
              const active = group.children.some((item) => location.pathname.startsWith(item.path));
              const open = expanded.has(group.id) && !collapsed;
              return <div className={styles.group} key={group.id}>
                <button className={`${styles.groupButton} ${active ? styles.groupActive : ""}`} title={collapsed ? group.label : undefined} onClick={() => { if (collapsed) setCollapsed(false); toggleGroup(group.id); }}><Icon name={group.icon}/><span>{group.label}</span><i className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`}><Icon name="chevron"/></i></button>
                <div className={`${styles.submenu} ${open ? styles.submenuOpen : ""}`}>{group.children.map((item) => <NavLink key={item.path} to={item.path} className={({ isActive }) => isActive ? styles.active : ""}><Icon name={item.icon}/><span>{item.label}</span></NavLink>)}</div>
              </div>;
            })}
          </nav>
          <div className={styles.sidebarFooter}><button onClick={() => setCollapsed((value) => !value)} title={collapsed ? "展开侧边栏" : "收起侧边栏"}><Icon name="collapse"/></button></div>
        </aside>
        <main className={styles.main}><div className={`${styles.content} ${location.pathname.startsWith("/assistant") ? styles.assistantContent : ""}`}><Outlet /></div></main>
      </div>
    </div>
  );
}
