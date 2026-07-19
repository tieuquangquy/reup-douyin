import type { ReactNode } from "react";
import { StatusBadge } from "../app-shell/StatusBadge";

export type OpsTone = "good" | "warn" | "danger" | "muted";
export type OpsActionTone = "primary" | "secondary" | "danger" | "link";
export type OpsStateVariant = "loading" | "empty" | "error" | "info" | "success";

export type OpsSummaryCardItem = {
  key: string;
  label: string;
  value: string | number;
  description: string;
  tone?: OpsTone;
};

export type OpsMetadataItem = {
  label: string;
  value: ReactNode;
};

export type OpsItemAction = {
  key: string;
  label: string;
  href?: string;
  external?: boolean;
  disabled?: boolean;
  tone?: OpsActionTone;
  onClick?: () => void;
};

export function OpsPageHeader({
  eyebrow = "Ops Console",
  title,
  description,
  actions
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="ops-page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions ? <div className="ops-header-actions">{actions}</div> : null}
    </header>
  );
}

export function OpsMetricCard({ label, value, detail, tone = "muted" }: { label: string; value: string; detail: string; tone?: OpsTone }) {
  const badgeLabel = tone === "good" ? "Healthy" : tone === "warn" ? "Needs attention" : tone === "danger" ? "Blocked" : "Info";

  return (
    <div className="health-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
      <StatusBadge label={badgeLabel} tone={tone} />
    </div>
  );
}

export function OpsPanel({
  title,
  children,
  actions,
  meta
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <section className="health-panel">
      <div className="ops-panel-heading">
        <div className="ops-panel-heading__lead">
          <h2>{title}</h2>
          {meta ? <div className="ops-panel-heading__meta">{meta}</div> : null}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function OpsState({ title, detail, retry }: { title: string; detail: string; retry?: () => void }) {
  return (
    <main className="ops-page">
      <div className="state-panel">
        <h1>{title}</h1>
        <p>{detail}</p>
        {retry ? <button type="button" onClick={retry}>Retry</button> : null}
      </div>
    </main>
  );
}

export function OpsConsolePage({ children }: { children: ReactNode }) {
  return <div className="ops-console-page">{children}</div>;
}

export function OpsSection({
  actions,
  children,
  description,
  title
}: {
  actions?: ReactNode;
  children: ReactNode;
  description?: string;
  title: string;
}) {
  return (
    <section className="operator-panel ops-console-section">
      <div className="operator-panel-heading ops-console-section-heading">
        <div>
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {actions ? <div className="ops-console-section-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function OpsContentGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={`ops-console-content-grid${className ? ` ${className}` : ""}`}>{children}</div>;
}

export function OpsMainColumn({ children }: { children: ReactNode }) {
  return <main className="ops-console-main-column">{children}</main>;
}

export function OpsSideColumn({ children }: { children: ReactNode }) {
  return <aside className="ops-console-side-column">{children}</aside>;
}

export function OpsToolbar({ children, description, title = "Find workflow records" }: { children: ReactNode; description?: string; title?: string }) {
  return (
    <section className="operator-panel ops-console-filter-bar ops-console-toolbar">
      <div className="operator-panel-heading">
        <div>
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
      </div>
      <div className="ops-console-toolbar-controls">{children}</div>
    </section>
  );
}

export function OpsToolbarGroup({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className="ops-console-toolbar-group">
      {label ? <span className="ops-console-toolbar-label">{label}</span> : null}
      {children}
    </div>
  );
}

export function OpsEmptyState({ action, detail, title }: { action?: ReactNode; detail: string; title: string }) {
  return <OpsStatePanel action={action} detail={detail} title={title} variant="empty" />;
}

export function OpsStatusBadge({ label, tone = "muted" }: { label: string; tone?: OpsTone }) {
  return <StatusBadge label={label} tone={tone} />;
}

export function OpsWorkflowContext({
  currentStep,
  metrics,
  steps
}: {
  currentStep: string;
  metrics: OpsMetadataItem[];
  steps: string[];
}) {
  return (
    <section className="operator-panel ops-console-workflow-context">
      <div className="operator-panel-heading">
        <div>
          <span className="intake-status-eyebrow">Workflow context</span>
          <h2>{currentStep}</h2>
          <p>{steps.join(" -> ")}</p>
        </div>
      </div>
      <OpsMetadataList items={metrics} />
    </section>
  );
}

export function OpsNextActionBanner({
  actions,
  description,
  title = "Recommended next action",
  tone = "warn"
}: {
  actions?: ReactNode;
  description: string;
  title?: string;
  tone?: OpsTone;
}) {
  return (
    <section className={`operator-panel intake-status ${tone} ops-console-next-action`}>
      <span className="intake-status-eyebrow">{title}</span>
      <p>{description}</p>
      {actions ? <div className="actions-row">{actions}</div> : null}
    </section>
  );
}

export function OpsSummaryCards({
  activeKey,
  cards,
  onSelect,
  title = "Queue state summary",
  hint = "Click a card to focus the list."
}: {
  activeKey?: string;
  cards: OpsSummaryCardItem[];
  hint?: string;
  onSelect?: (key: string) => void;
  title?: string;
}) {
  return (
    <section className="operator-panel ops-console-summary-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{hint}</p>
        </div>
      </div>
      <div className="ops-console-summary-grid">
        {cards.map((card) => {
          const active = activeKey === card.key;
          const className = `operator-metric-card ops-console-summary-card ${active ? "active" : ""} ${card.tone ?? "muted"}`;
          if (onSelect) {
            return (
              <button className={className} key={card.key} onClick={() => onSelect(card.key)} type="button">
                <span>{card.label}</span>
                <strong>{card.value}</strong>
                <p>{card.description}</p>
              </button>
            );
          }
          return (
            <div className={className} key={card.key}>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <p>{card.description}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function OpsFilterBar({ children, title = "Find workflow records", description }: { children: ReactNode; description?: string; title?: string }) {
  return <OpsToolbar description={description} title={title}>{children}</OpsToolbar>;
}

export function OpsItemCard({
  actions,
  children,
  focused = false,
  metadata,
  onFocus,
  onSelect,
  preview,
  selected = false,
  statusLabel,
  statusTone: badgeTone = "muted",
  title
}: {
  actions?: OpsItemAction[];
  children?: ReactNode;
  focused?: boolean;
  metadata?: OpsMetadataItem[];
  onFocus?: () => void;
  onSelect?: () => void;
  preview?: ReactNode;
  selected?: boolean;
  statusLabel?: string;
  statusTone?: OpsTone;
  title: ReactNode;
}) {
  return (
    <article className={`operator-panel ops-console-item-card ${focused ? "selected" : ""}`}>
      <div className="operator-panel-heading">
        <div className="ops-console-item-title-row">
          {onSelect ? (
            <label className="intake-checkbox-field ops-console-item-checkbox">
              <input checked={selected} onChange={onSelect} type="checkbox" />
              <span>Select</span>
            </label>
          ) : null}
          {preview ? <div className="ops-console-item-preview">{preview}</div> : null}
          <div>
            <h3>{title}</h3>
            {metadata ? <OpsMetadataList items={metadata} /> : null}
          </div>
        </div>
        {statusLabel ? <StatusBadge label={statusLabel} tone={badgeTone} /> : null}
      </div>
      {children}
      {actions && actions.length > 0 ? <OpsActionRow actions={actions} onFallbackFocus={onFocus} /> : null}
    </article>
  );
}

export function OpsDetailPanel({ children, emptyDetail, title = "Detail panel" }: { children?: ReactNode; emptyDetail?: string; title?: string }) {
  return (
    <section className="operator-panel ops-console-detail-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>{title}</h2>
          {emptyDetail ? <p>{emptyDetail}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

export function OpsDetailSection({ children, collapsed = false, description, title }: { children: ReactNode; collapsed?: boolean; description?: string; title: string }) {
  if (collapsed) {
    return (
      <details className="operator-panel advanced-panel ops-console-detail-section">
        <summary>
          <span>
            <strong>{title}</strong>
            {description ? <small>{description}</small> : null}
          </span>
        </summary>
        {children}
      </details>
    );
  }

  return (
    <section className="operator-panel advanced-panel ops-console-detail-section">
      <h3>{title}</h3>
      {description ? <p className="muted">{description}</p> : null}
      {children}
    </section>
  );
}

export function OpsBatchActionBar({
  actions,
  children,
  onClear,
  selectedCount,
  title = "Batch actions"
}: {
  actions: OpsItemAction[];
  children?: ReactNode;
  onClear?: () => void;
  selectedCount: number;
  title?: string;
}) {
  if (selectedCount === 0) return null;

  return (
    <section className="operator-panel intake-status good ops-console-batch-action-bar">
      <span className="intake-status-eyebrow">{title}</span>
      <div className="actions-row">
        <strong>{selectedCount} selected</strong>
        <OpsActionRow actions={actions} />
        {onClear ? <button type="button" onClick={onClear}>Clear selection</button> : null}
      </div>
      {children}
    </section>
  );
}

export function OpsStatePanel({ action, detail, title, variant = "info" }: { action?: ReactNode; detail: string; title: string; variant?: OpsStateVariant }) {
  return (
    <div className={`state-panel ops-console-state-panel ${variant}`}>
      <h2>{title}</h2>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function OpsMetadataList({ items }: { items: OpsMetadataItem[] }) {
  return (
    <dl className="summary-list ops-console-metadata-list">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function OpsActionRow({ actions, onFallbackFocus }: { actions: OpsItemAction[]; onFallbackFocus?: () => void }) {
  return (
    <div className="actions-row ops-console-action-row">
      {actions.map((action) => {
        const className = action.tone === "primary" ? "primary" : action.tone === "danger" ? "danger" : undefined;
        if (action.href) {
          return (
            <a href={action.href} key={action.key} rel={action.external ? "noreferrer" : undefined} target={action.external ? "_blank" : undefined}>
              {action.label}
            </a>
          );
        }
        return (
          <button className={className} disabled={action.disabled} key={action.key} onClick={action.onClick ?? onFallbackFocus} type="button">
            {action.label}
          </button>
        );
      })}
    </div>
  );
}

export function formatNumber(value: number | null | undefined): string {
  return String(value ?? 0);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function sumRecord(record: Record<string, number> | undefined): number {
  if (!record) return 0;
  return Object.values(record).reduce((total, value) => total + value, 0);
}

export function statusTone(status: string | null | undefined): OpsTone {
  if (!status) return "muted";
  if (["READY", "READY_FOR_REVIEW", "APPROVED", "READY_TO_EXPORT", "READY_TO_PUBLISH", "EXPORT_PACKAGE_CREATED", "PUBLISH_HANDOFF_CREATED", "EXPORTED", "HANDOFF_CREATED", "SUCCEEDED", "COMPLETED", "PUBLISHED", "RESOLVED", "WAIVED", "HEALTHY", "ACTIVE"].includes(status)) return "good";
  if (["FAILED", "FAILED_NEEDS_ATTENTION", "CRITICAL", "BLOCKING", "UNHEALTHY", "INVALID", "REJECTED", "BLOCKED"].includes(status)) return "danger";
  if (["PENDING", "NEEDS_REVIEW", "READY_TO_PROCESS", "NEEDS_METADATA", "NEEDS_MEDIA", "PROCESSING", "RETRYABLE", "NEEDS_RECONCILIATION", "RECONCILING", "OPEN", "DEGRADED", "HELD", "PAUSED"].includes(status)) return "warn";
  if (["CANCELLED", "SKIPPED", "ARCHIVED", "DUPLICATE", "INACTIVE"].includes(status)) return "muted";
  return "muted";
}
