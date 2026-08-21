import type { PropsWithChildren, ReactNode } from "react";
import styles from "./Card.module.css";

export function Card({ children, title, extra, className = "" }: PropsWithChildren<{ title?: string; extra?: ReactNode; className?: string }>) {
  return <section className={`${styles.card} ${className}`}>{(title || extra) && <header><h2>{title}</h2>{extra}</header>}{children}</section>;
}

export function MetricCard({ label, value, suffix, tone = "blue", hint }: { label: string; value: string; suffix?: string; tone?: string; hint?: string }) {
  return <Card className={`${styles.metric} ${styles[tone] ?? ""}`}><span>{label}</span><strong>{value}<small>{suffix}</small></strong>{hint && <em>{hint}</em>}</Card>;
}
