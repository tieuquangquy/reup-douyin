"use client";

import { forwardRef, useEffect, useState } from "react";
import {
  formatOffsetAllLoadedLabel,
  formatOffsetLoadMoreLabel,
  formatOffsetLoadNextLabel,
  formatOffsetLoadedLabel,
  formatOffsetShowingLabel,
  hasMoreOffsetItems,
  nextOffsetPageSize,
} from "../../lib/offsetListPagination";

type OffsetLoadMoreFooterProps = {
  loadedCount: number;
  totalCount: number;
  pageSize: number;
  loadingMore?: boolean;
  noun?: string;
  onLoadMore?: () => void;
  disabled?: boolean;
  className?: string;
  pageSizeOptions?: readonly number[];
  onPageSizeChange?: (pageSize: number) => void;
  /** When true, studio variant uses scroll auto-load UI (no Load next button). */
  autoLoad?: boolean;
  /**
   * `inline` = Ops Jobs compact progress pager.
   * `studio` = Work Soft CTA centered pager (concept C).
   * Default keeps legacy two-block layout.
   */
  variant?: "default" | "inline" | "studio";
};

export const OffsetLoadMoreFooter = forwardRef<HTMLDivElement, OffsetLoadMoreFooterProps>(
  function OffsetLoadMoreFooter(
    {
      loadedCount,
      totalCount,
      pageSize,
      loadingMore = false,
      noun = "items",
      onLoadMore,
      disabled = false,
      className = "capture-inbox-gallery-footer",
      pageSizeOptions,
      onPageSizeChange,
      autoLoad = false,
      variant = "default",
    },
    ref
  ) {
    const [holdLoadingHint, setHoldLoadingHint] = useState(false);

    useEffect(() => {
      if (loadingMore) {
        setHoldLoadingHint(true);
        return;
      }
      if (!holdLoadingHint) return;
      const timer = window.setTimeout(() => setHoldLoadingHint(false), 280);
      return () => window.clearTimeout(timer);
    }, [holdLoadingHint, loadingMore]);

    if (totalCount <= 0 && loadedCount <= 0) return null;

    const hasMore = hasMoreOffsetItems(loadedCount, totalCount);
    const remaining = nextOffsetPageSize(pageSize, loadedCount, totalCount);
    const showPageSize = Boolean(pageSizeOptions?.length && onPageSizeChange);
    const loadedPercent =
      totalCount <= 0 ? 0 : Math.max(0, Math.min(100, Math.round((loadedCount / totalCount) * 100)));
    const showLoadingHint = loadingMore || holdLoadingHint;

    if (variant === "studio") {
      const rootClass = [
        "work-studio-pager",
        autoLoad ? "is-auto-load" : "",
        className === "capture-inbox-gallery-footer" ? "" : className,
      ]
        .filter(Boolean)
        .join(" ");

      if (autoLoad) {
        return (
          <div aria-busy={showLoadingHint} className={rootClass} ref={ref}>
            <div className="work-studio-pager__row">
              <p className="work-studio-pager__meta">{formatOffsetShowingLabel(loadedCount, totalCount, noun)}</p>
              {showPageSize ? (
                <div className="work-studio-pager__pages" role="group" aria-label="Items per page">
                  <span className="work-studio-pager__pages-label">Per page</span>
                  {pageSizeOptions!.map((option) => (
                    <button
                      className={`work-studio-pager__page${option === pageSize ? " is-active" : ""}`}
                      disabled={disabled}
                      key={option}
                      type="button"
                      onClick={() => onPageSizeChange?.(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="work-studio-pager__track" aria-hidden={!hasMore && !showLoadingHint}>
              <div className="work-studio-pager__bar">
                <span style={{ width: `${loadedPercent}%` }} />
              </div>
              <p className="work-studio-pager__hint">
                {showLoadingHint
                  ? "Loading more…"
                  : hasMore
                    ? "Scroll for more"
                    : formatOffsetAllLoadedLabel(noun)}
              </p>
            </div>
          </div>
        );
      }

      return (
        <div className={rootClass} ref={ref}>
          <p className="work-studio-pager__meta">{formatOffsetShowingLabel(loadedCount, totalCount, noun)}</p>
          {hasMore && onLoadMore ? (
            <button
              className="work-studio-pager__cta"
              disabled={disabled || loadingMore || remaining <= 0}
              onClick={onLoadMore}
              type="button"
            >
              {formatOffsetLoadNextLabel(pageSize, loadedCount, totalCount, noun, loadingMore)}
            </button>
          ) : (
            <p className="work-studio-pager__complete">{formatOffsetAllLoadedLabel(noun)}</p>
          )}
          {showPageSize ? (
            <div className="work-studio-pager__pages" role="group" aria-label="Items per page">
              <span className="work-studio-pager__pages-label">Per page</span>
              {pageSizeOptions!.map((option) => (
                <button
                  className={`work-studio-pager__page${option === pageSize ? " is-active" : ""}`}
                  disabled={disabled || loadingMore}
                  key={option}
                  type="button"
                  onClick={() => onPageSizeChange?.(option)}
                >
                  {option}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      );
    }

    if (variant === "inline") {
      const rootClass = ["offset-load-more is-inline", className].filter(Boolean).join(" ");
      return (
        <div className={rootClass} ref={ref}>
          <div className="offset-load-more__progress" aria-label={`${loadedPercent}% loaded`}>
            <div className="offset-load-more__bar">
              <span style={{ width: `${loadedPercent}%` }} />
            </div>
            <p className="offset-load-more__meta">
              <strong>{loadedPercent}%</strong>
              <span>
                {loadedCount.toLocaleString("en-US")}/{totalCount.toLocaleString("en-US")} {noun}
              </span>
            </p>
          </div>

          <div className="offset-load-more__actions">
            {showPageSize ? (
              <label className="offset-load-more-page-size">
                <span>Per page</span>
                <select
                  aria-label="Items per page"
                  disabled={disabled || loadingMore}
                  onChange={(event) => onPageSizeChange?.(Number(event.target.value))}
                  value={pageSize}
                >
                  {pageSizeOptions!.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {hasMore && onLoadMore ? (
              <button
                className="offset-load-more__next"
                disabled={disabled || loadingMore || remaining <= 0}
                onClick={onLoadMore}
                type="button"
              >
                {loadingMore ? "Loading…" : `Load more · ${remaining.toLocaleString("en-US")}`}
              </button>
            ) : (
              <span className="offset-load-more__complete">All loaded</span>
            )}
          </div>
        </div>
      );
    }

    return (
      <div className={className} ref={ref}>
        <p>{formatOffsetLoadedLabel(loadedCount, totalCount, noun)}</p>
        <div className="offset-load-more-actions">
          {showPageSize ? (
            <label className="offset-load-more-page-size">
              <span>Per page</span>
              <select
                aria-label="Items per page"
                disabled={disabled || loadingMore}
                onChange={(event) => onPageSizeChange?.(Number(event.target.value))}
                value={pageSize}
              >
                {pageSizeOptions!.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {hasMore && onLoadMore ? (
            <button
              className="primary"
              disabled={disabled || loadingMore || remaining <= 0}
              onClick={onLoadMore}
              type="button"
            >
              {formatOffsetLoadMoreLabel(pageSize, loadedCount, totalCount, loadingMore)}
            </button>
          ) : null}
        </div>
      </div>
    );
  }
);
