"use client";

import type { ReactNode } from "react";

export function WorkStudioDeck({
  actions,
  ariaLabel,
  children,
  className = "",
  kicker,
  meta
}: {
  actions?: ReactNode;
  ariaLabel: string;
  children?: ReactNode;
  className?: string;
  kicker: string;
  meta?: ReactNode;
}) {
  return (
    <section
      aria-label={ariaLabel}
      className={`work-studio-deck capture-inbox-command-deck capture-inbox-studio-deck capture-inbox-hero-panel is-compact ${className}`.trim()}
    >
      <div className="work-studio-deck__header capture-inbox-command-deck-top capture-inbox-hero-toolbar">
        <div className="work-studio-deck__copy capture-inbox-command-deck-title capture-inbox-hero-head-compact">
          <span className="work-studio-deck__kicker capture-inbox-command-deck-kicker capture-inbox-hero-kicker">{kicker}</span>
          {meta ? <div className="work-studio-deck__meta">{meta}</div> : null}
        </div>
        {actions ? <div className="work-studio-deck__actions capture-inbox-command-deck-quick capture-inbox-hero-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function WorkBulkActionBar({
  active,
  ariaLabel,
  children,
  className = "",
  guidance,
  selectedCount,
  toolbar
}: {
  active: boolean;
  ariaLabel: string;
  children?: ReactNode;
  className?: string;
  guidance?: ReactNode;
  selectedCount: number;
  toolbar?: ReactNode;
}) {
  return (
    <section
      aria-label={ariaLabel}
      className={`work-bulk-action-bar capture-inbox-command-bar capture-inbox-bulk-command-bar is-compact ${active ? "is-active" : "is-idle"} ${className}`.trim()}
      data-sticky="true"
    >
      <div className="work-bulk-action-bar__status">
        <span className="work-bulk-action-bar__count">{active ? `${selectedCount} selected` : "Bulk actions"}</span>
        {guidance ? <span className="work-bulk-action-bar__guidance">{guidance}</span> : null}
        {toolbar ? <div className="work-bulk-action-bar__toolbar">{toolbar}</div> : null}
      </div>
      {children ? <div className="work-bulk-action-bar__actions">{children}</div> : null}
    </section>
  );
}

export function WorkGalleryHeader({
  actions,
  eyebrow = "Tile gallery",
  meta,
  title
}: {
  actions?: ReactNode;
  eyebrow?: string;
  meta?: ReactNode;
  title: ReactNode;
}) {
  return (
    <div className="work-gallery-header capture-inbox-media-gallery-heading">
      <div className="work-gallery-header__copy">
        <span className="work-gallery-header__eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {meta ? <div className="work-gallery-header__meta">{meta}</div> : null}
      </div>
      {actions ? <div className="work-gallery-header__actions">{actions}</div> : null}
    </div>
  );
}

export function WorkViewToggle<K extends string>({
  ariaLabel,
  onChange,
  options,
  value
}: {
  ariaLabel: string;
  onChange: (value: K) => void;
  options: ReadonlyArray<{ key: K; label: string }>;
  value: K;
}) {
  return (
    <div className="work-view-toggle" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          aria-pressed={value === option.key}
          className={`work-view-toggle__button ${value === option.key ? "is-active" : ""}`}
          key={option.key}
          onClick={() => onChange(option.key)}
          type="button"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function WorkGalleryEmptyState({
  action,
  className = "",
  detail,
  eyebrow = "Tile gallery",
  glyph,
  loading = false,
  title
}: {
  action?: ReactNode;
  className?: string;
  detail: ReactNode;
  eyebrow?: string;
  glyph?: ReactNode;
  loading?: boolean;
  title: ReactNode;
}) {
  return (
    <div aria-busy={loading || undefined} className={`work-gallery-empty capture-inbox-gallery-empty ${className}`.trim()}>
      <div className={`work-gallery-empty__card capture-inbox-gallery-empty__card ${loading ? "is-loading" : "is-filtered"}`}>
        {glyph ? <div aria-hidden="true" className="capture-inbox-gallery-empty__glyph">{glyph}</div> : null}
        <div className="capture-inbox-gallery-empty__copy">
          <span className="capture-inbox-gallery-empty__eyebrow">{eyebrow}</span>
          <h3 className="capture-inbox-gallery-empty__title">{title}</h3>
          <p className="capture-inbox-gallery-empty__detail">{detail}</p>
        </div>
        {action ? <div className="work-gallery-empty__action capture-inbox-gallery-empty__action">{action}</div> : null}
      </div>
    </div>
  );
}
