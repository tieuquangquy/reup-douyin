"use client";

import {
  formatOffsetLoadMoreLabel,
  formatOffsetLoadedLabel,
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
};

export function OffsetLoadMoreFooter({
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
}: OffsetLoadMoreFooterProps) {
  if (totalCount <= 0 && loadedCount <= 0) return null;

  const hasMore = hasMoreOffsetItems(loadedCount, totalCount);
  const remaining = nextOffsetPageSize(pageSize, loadedCount, totalCount);
  const showPageSize = Boolean(pageSizeOptions?.length && onPageSizeChange);

  return (
    <div className={className}>
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
