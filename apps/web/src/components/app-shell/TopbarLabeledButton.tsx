"use client";

import type { ReactNode } from "react";

type TopbarLabeledButtonProps = {
  label: string;
  icon: ReactNode;
  busy?: boolean;
  className?: string;
  disabled?: boolean;
  href?: string;
  onClick?: () => void;
  title?: string;
  type?: "button" | "submit";
};

export function TopbarLabeledButton({
  label,
  icon,
  busy = false,
  className = "",
  disabled = false,
  href,
  onClick,
  title,
  type = "button"
}: TopbarLabeledButtonProps) {
  const rootClass = ["app-topbar-btn", "is-labeled", busy ? "is-busy" : "", className].filter(Boolean).join(" ");
  const content = (
    <>
      <span aria-hidden="true" className="app-topbar-btn__icon-wrap">
        {icon}
      </span>
      <span className="app-topbar-btn__label">{label}</span>
    </>
  );

  if (href) {
    return (
      <a aria-busy={busy || undefined} className={rootClass} href={href} title={title ?? label}>
        {content}
      </a>
    );
  }

  return (
    <button
      aria-busy={busy || undefined}
      className={rootClass}
      disabled={disabled || busy}
      onClick={onClick}
      title={title ?? label}
      type={type}
    >
      {content}
    </button>
  );
}
