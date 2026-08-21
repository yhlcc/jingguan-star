import styles from "./StatusPill.module.css";

export function StatusPill({ status }: { status: string }) {
  const good = ["成功", "启用", "已处理", "已完成", "ok"].some((item) => status.includes(item));
  const warn = ["待", "中", "warning"].some((item) => status.includes(item));
  return <span className={`${styles.pill} ${good ? styles.good : warn ? styles.warn : styles.bad}`}>{status}</span>;
}
