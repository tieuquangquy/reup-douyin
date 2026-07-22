"use client";

import type { ReactNode } from "react";

export type AsyncContentStatus = "loading" | "error" | "empty" | "success";

type AsyncSkeletonProps = {
  variant: "gallery" | "list" | "detail" | "form";
  count?: number;
  label?: string;
};

export function AsyncSkeleton({ variant, count, label = "Loading content…" }: AsyncSkeletonProps) {
  const itemCount = count ?? (variant === "gallery" ? 6 : variant === "list" ? 5 : 1);
  return (
    <div aria-label={label} className={`async-skeleton is-${variant}`} role="status">
      <span className="sr-only">{label}</span>
      {Array.from({ length: itemCount }, (_, index) => (
        <div aria-hidden="true" className="async-skeleton__item" key={index}>
          {variant === "gallery" || variant === "detail" ? <span className="async-skeleton__block is-media" /> : null}
          <span className="async-skeleton__block is-line is-wide" />
          <span className="async-skeleton__block is-line" />
          {variant === "form" ? <span className="async-skeleton__block is-field" /> : null}
        </div>
      ))}
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
