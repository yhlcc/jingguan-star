import type { ButtonHTMLAttributes, PropsWithChildren } from "react";
import styles from "./Button.module.css";

export function Button({ children, variant = "primary", className = "", ...props }: PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }>) {
  return <button className={`${styles.button} ${styles[variant]} ${className}`} {...props}>{children}</button>;
}
