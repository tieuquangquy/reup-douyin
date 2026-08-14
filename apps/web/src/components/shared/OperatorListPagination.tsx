/**
 * Numbered list pagination dock shared by Ops Jobs and operator worklists.
 * Visual classes stay `ops-jobs-pagination*` (existing CSS).
 */
"use client";

function paginationItems(currentPage: number, totalPages: number): Array<number | string> {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1);
  if (currentPage <= 4) return [1, 2, 3, 4, 5, "ellipsis-right", totalPages];
  if (currentPage >= totalPages - 3) {
    return [1, "ellipsis-left", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  }
  return [1, "ellipsis-left", currentPage - 1, currentPage, currentPage + 1, "ellipsis-right", totalPages];
}

function PaginationArrow({ direction }: { direction: "previous" | "next" }) {
  return (
    <svg className="ops-jobs-pagination__arrow" viewBox="0 0 20 20" aria-hidden="true">
      <path d={direction === "previous" ? "m12 5-5 5 5 5" : "m8 5 5 5-5 5"} />
    </svg>
  );
}

export type OperatorListPaginationLabels = {
  pagination: string;
  perPage: string;
  previous: string;
  next: string;
  page: string;
  noun: string;
};

export function OperatorListPagination({
  currentPage,
  totalCount,
  pageSize,
  pageSizeOptions,
  busy,
  onPageChange,
  onPageSizeChange,
  labels,
}: {
  currentPage: number;
  totalCount: number;
  pageSize: number;
  pageSizeOptions: readonly number[];
  busy: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  labels: OperatorListPaginationLabels;
}) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const start = totalCount > 0 ? (safePage - 1) * pageSize + 1 : 0;
  const end = Math.min(safePage * pageSize, totalCount);
  const items = paginationItems(safePage, totalPages);
  return (
    <nav className="ops-jobs-pagination" aria-label={labels.pagination}>
      <div className="ops-jobs-pagination__size" role="group" aria-label={labels.perPage}>
        <span>{labels.perPage}</span>
        <div>
          {pageSizeOptions.map((option) => (
            <button
              type="button"
              className={option === pageSize ? "is-active" : ""}
              aria-pressed={option === pageSize}
              disabled={busy}
              key={option}
              onClick={() => onPageSizeChange(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className="ops-jobs-pagination__pages">
        <button type="button" className="ops-jobs-pagination__nav" aria-label={labels.previous} disabled={busy || safePage <= 1} onClick={() => onPageChange(safePage - 1)}>
          <PaginationArrow direction="previous" />
        </button>
        <div className="ops-jobs-pagination__numbers">
          {items.map((item) => typeof item === "number" ? (
            <button
              type="button"
              className={item === safePage ? "is-active" : ""}
              aria-current={item === safePage ? "page" : undefined}
              aria-label={`${labels.page} ${item}`}
              disabled={busy}
              key={item}
              onClick={() => onPageChange(item)}
            >
              {item}
            </button>
          ) : <span key={item} aria-hidden="true">…</span>)}
        </div>
        <span className="ops-jobs-pagination__compact">{labels.page} {safePage} / {totalPages}</span>
        <button type="button" className="ops-jobs-pagination__nav" aria-label={labels.next} disabled={busy || safePage >= totalPages} onClick={() => onPageChange(safePage + 1)}>
          <PaginationArrow direction="next" />
        </button>
      </div>

      <p className="ops-jobs-pagination__range">
        <strong>{start.toLocaleString("en-US")}–{end.toLocaleString("en-US")}</strong>
        <span>/ {totalCount.toLocaleString("en-US")} {labels.noun}</span>
      </p>
    </nav>
  );
}
