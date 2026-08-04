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

function SkeletonBlock({ className = "" }: { className?: string }) {
  return <span aria-hidden="true" className={`operator-home-skeleton__block ${className}`.trim()} />;
}

export function OperatorHomeLoadingSkeleton({ label = "Loading workspace…" }: { label?: string }) {
  return (
    <div aria-busy="true" className="operator-home operator-home-skeleton" role="status">
      <div className="operator-home-skeleton__hero">
        <span aria-hidden="true" className="operator-home-skeleton__glyph">
          <span className="operator-home-skeleton__spinner" />
        </span>
        <div className="operator-home-skeleton__copy">
          <span className="operator-home-skeleton__eyebrow">Operator Studio</span>
          <p className="operator-home-skeleton__title">{label}</p>
          <p className="operator-home-skeleton__detail">Preparing your daily command center</p>
        </div>
      </div>

      <div aria-hidden="true" className="operator-home-skeleton__strip">
        <SkeletonBlock className="is-headline" />
        <SkeletonBlock className="is-pill" />
        <SkeletonBlock className="is-pill is-narrow" />
      </div>

      <div aria-hidden="true" className="operator-home-skeleton__kpis">
        {Array.from({ length: 6 }, (_, index) => (
          <div className="operator-home-skeleton__kpi" key={index}>
            <SkeletonBlock className="is-label" />
            <SkeletonBlock className="is-value" />
            <SkeletonBlock className="is-meta" />
          </div>
        ))}
      </div>

      <div aria-hidden="true" className="operator-home-skeleton__panel">
        <div className="operator-home-skeleton__panel-head">
          <SkeletonBlock className="is-heading" />
          <SkeletonBlock className="is-subhead" />
        </div>
        <div className="operator-home-skeleton__rows">
          <SkeletonBlock className="is-row" />
          <SkeletonBlock className="is-row is-short" />
          <SkeletonBlock className="is-row" />
        </div>
      </div>

      <section aria-hidden="true" className="operator-home-layout">
        <div className="operator-home-main">
          <div className="operator-home-skeleton__panel">
            <div className="operator-home-skeleton__panel-head">
              <SkeletonBlock className="is-heading" />
              <SkeletonBlock className="is-subhead" />
            </div>
            <div className="operator-home-skeleton__rows">
              <SkeletonBlock className="is-row" />
              <SkeletonBlock className="is-row" />
              <SkeletonBlock className="is-row is-short" />
            </div>
          </div>
          <div className="operator-home-skeleton__chips">
            <SkeletonBlock className="is-chip" />
            <SkeletonBlock className="is-chip" />
            <SkeletonBlock className="is-chip is-narrow" />
            <SkeletonBlock className="is-chip" />
          </div>
        </div>
        <aside className="operator-home-side">
          <div className="operator-home-skeleton__panel">
            <div className="operator-home-skeleton__panel-head">
              <SkeletonBlock className="is-heading" />
              <SkeletonBlock className="is-subhead" />
            </div>
            <div className="operator-home-skeleton__rows">
              <SkeletonBlock className="is-row" />
              <SkeletonBlock className="is-row is-short" />
              <SkeletonBlock className="is-row" />
              <SkeletonBlock className="is-row is-short" />
            </div>
          </div>
        </aside>
      </section>
    </div>
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
