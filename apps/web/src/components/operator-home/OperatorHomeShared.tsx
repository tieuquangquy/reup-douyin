import type { ReactNode } from "react";

export type OperatorHomeTone = "good" | "warn" | "danger" | "muted";

export function OperatorHomeChip({ label, tone }: { label: string; tone: OperatorHomeTone }) {
  return <span className={`operator-home-chip tone-${tone}`}>{label}</span>;
}

function OperatorHomeOpenIcon() {
  return (
    <svg className="operator-home-open-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function OperatorHomeOpenLink({ href, label }: { href: string; label: string }) {
  return (
    <a className="operator-home-open" href={href} aria-label={label} title={label}>
      <OperatorHomeOpenIcon />
    </a>
  );
}

export function OperatorHomePanel({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="operator-home-panel">
      <div className="operator-home-panel__head">
        <div>
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {action}
      </div>
      <div className="operator-home-panel__body">{children}</div>
    </section>
  );
}

export function formatCompactActivityTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const time = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  const day = date.getDate();
  const month = date.getMonth() + 1;
  return `${time} · ${day}/${month}`;
}
