"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type AsyncButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  children: ReactNode;
  pending?: boolean;
  pendingLabel?: ReactNode;
  leadingIcon?: ReactNode;
  statusId?: string;
};

export function AsyncButton({
  children,
  pending = false,
  pendingLabel = "Working…",
  leadingIcon,
  statusId,
  className = "",
  disabled = false,
  type = "button",
  ...props
}: AsyncButtonProps) {
  const showIcon = pending || leadingIcon != null;

  return (
    <button
      {...props}
      aria-busy={pending || undefined}
      aria-describedby={statusId}
      className={`async-button ${pending ? "is-pending" : ""} ${className}`.trim()}
      disabled={disabled || pending}
      type={type}
    >
      {showIcon ? (
        <span aria-hidden="true" className="async-button__icon">
          {pending ? <span className="async-button__spinner" /> : leadingIcon}
        </span>
      ) : null}
      <span className="async-button__label">{pending ? pendingLabel : children}</span>
    </button>
  );
}
