"use client";

import type { ReactNode } from "react";

export type AsyncContentStatus = "loading" | "error" | "empty" | "success";

export type AsyncSkeletonVariant = "gallery" | "list" | "detail" | "form" | "table" | "dashboard";

type AsyncSkeletonProps = {
  variant: AsyncSkeletonVariant;
  count?: number;
  label?: string;
};

function SkeletonStatus({ label }: { label: string }) {
  return (
    <div className="async-skeleton__status">
      <span aria-hidden="true" className="async-skeleton__spinner" />
      <span className="async-skeleton__label">{label}</span>
    </div>
  );
}

export function AsyncSkeleton({ variant, count, label = "Loading content…" }: AsyncSkeletonProps) {
  if (variant === "dashboard") {
    return (
      <div aria-busy="true" className="async-skeleton is-dashboard" role="status">
        <SkeletonStatus label={label} />
        <div aria-hidden="true" className="async-skeleton__dashboard">
          <div className="async-skeleton__kpi-row">
            {Array.from({ length: 4 }, (_, index) => (
              <div className="async-skeleton__kpi" key={index}>
                <span className="async-skeleton__block is-line is-wide" />
                <span className="async-skeleton__block is-line" />
              </div>
            ))}
          </div>
          <div className="async-skeleton__panels">
            {Array.from({ length: 2 }, (_, index) => (
              <div className="async-skeleton__item" key={index}>
                <span className="async-skeleton__block is-line is-wide" />
                <span className="async-skeleton__block is-line" />
                <span className="async-skeleton__block is-line" />
                <span className="async-skeleton__block is-field" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const itemCount = count ?? (variant === "gallery" ? 6 : variant === "list" || variant === "table" ? 5 : 1);
  return (
    <div aria-busy="true" className={`async-skeleton is-${variant}`} role="status">
      <SkeletonStatus label={label} />
      <div aria-hidden="true" className="async-skeleton__grid">
        {Array.from({ length: itemCount }, (_, index) => (
          <div className={`async-skeleton__item${variant === "table" ? " is-table-row" : ""}`} key={index}>
            {variant === "table" ? (
              <>
                <span className="async-skeleton__block is-line is-cell" />
                <span className="async-skeleton__block is-line is-cell is-wide" />
                <span className="async-skeleton__block is-line is-cell" />
                <span className="async-skeleton__block is-line is-cell is-narrow" />
              </>
            ) : (
              <>
                {variant === "gallery" || variant === "detail" ? <span className="async-skeleton__block is-media" /> : null}
                <span className="async-skeleton__block is-line is-wide" />
                <span className="async-skeleton__block is-line" />
                {variant === "form" ? <span className="async-skeleton__block is-field" /> : null}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

type AsyncContentBoundaryProps = {
  status: AsyncContentStatus;
  children: ReactNode;
  refreshing?: boolean;
  skeleton?: ReactNode;
  skeletonVariant?: AsyncSkeletonProps["variant"];
  emptyState?: ReactNode;
  errorState?: ReactNode;
  loadingLabel?: string;
  refreshLabel?: string;
  className?: string;
};

export function AsyncContentBoundary({
  status,
  children,
  refreshing = false,
  skeleton,
  skeletonVariant = "list",
  emptyState,
  errorState,
  loadingLabel = "Loading content…",
  refreshLabel = "Refreshing…",
  className = "",
}: AsyncContentBoundaryProps) {
  if (status === "loading") {
    return <>{skeleton ?? <AsyncSkeleton label={loadingLabel} variant={skeletonVariant} />}</>;
  }
  if (status === "error") {
    return (
      <div className="async-content-state is-error" role="alert">
        {errorState ?? <p>We could not load this content. Please try again.</p>}
      </div>
    );
  }
  if (status === "empty") {
    return (
      <div className="async-content-state is-empty">
        {emptyState ?? <p>No items to show.</p>}
      </div>
    );
  }

  return (
    <section aria-busy={refreshing || undefined} className={`async-content-boundary ${className}`.trim()}>
      {refreshing ? (
        <div className="async-content-refresh" role="status">
          <span aria-hidden="true" className="async-content-refresh__spinner" />
          <span>{refreshLabel}</span>
        </div>
      ) : null}
      {children}
    </section>
  );
}
