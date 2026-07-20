export function hasMoreOffsetItems(loadedCount: number, totalCount: number): boolean {
  return loadedCount < totalCount;
}

export function nextOffsetPageSize(pageSize: number, loadedCount: number, totalCount: number): number {
  return Math.max(0, Math.min(pageSize, totalCount - loadedCount));
}

export function formatOffsetLoadedLabel(loadedCount: number, totalCount: number, noun = "items"): string {
  if (totalCount <= 0) return `No ${noun} loaded.`;
  if (loadedCount >= totalCount) return `All ${totalCount.toLocaleString("en-US")} ${noun} loaded.`;
  return `Loaded ${loadedCount.toLocaleString("en-US")} of ${totalCount.toLocaleString("en-US")} ${noun}.`;
}

export function formatOffsetLoadMoreLabel(pageSize: number, loadedCount: number, totalCount: number, loading = false): string {
  if (loading) return "Loading more…";
  const remaining = nextOffsetPageSize(pageSize, loadedCount, totalCount);
  return `Load more (${remaining.toLocaleString("en-US")})`;
}

/** Concept C — centered soft CTA meta */
export function formatOffsetShowingLabel(loadedCount: number, totalCount: number, noun = "items"): string {
  if (totalCount <= 0) return `No ${noun} to show`;
  if (loadedCount >= totalCount) return `Showing all ${totalCount.toLocaleString("en-US")} ${noun}`;
  return `Showing ${loadedCount.toLocaleString("en-US")} of ${totalCount.toLocaleString("en-US")} ${noun}`;
}

export function formatOffsetLoadNextLabel(
  pageSize: number,
  loadedCount: number,
  totalCount: number,
  noun = "items",
  loading = false
): string {
  if (loading) return "Loading…";
  const remaining = nextOffsetPageSize(pageSize, loadedCount, totalCount);
  return `Load next ${remaining.toLocaleString("en-US")} ${noun}`;
}

export function formatOffsetAllLoadedLabel(noun = "items"): string {
  return `All ${noun} loaded`;
}

export function mergeOffsetItemsById<T extends { id: string }>(existing: T[], incoming: T[]): T[] {
  if (incoming.length === 0) return existing;
  const seen = new Set(existing.map((item) => item.id));
  const appended = incoming.filter((item) => !seen.has(item.id));
  return [...existing, ...appended];
}

/** When offset tail returns duplicates or an empty page, stop infinite auto-load loops. */
export function reconcileOffsetTotalAfterStall(loadedCount: number, apiTotalCount: number): number {
  return loadedCount < apiTotalCount ? loadedCount : apiTotalCount;
}

export function resolveOffsetPageMerge<T extends { id: string }>(
  existing: T[],
  incoming: T[],
  apiTotalCount: number
): { merged: T[]; appendedCount: number; totalCount: number; hasMore: boolean } {
  const merged = mergeOffsetItemsById(existing, incoming);
  const appendedCount = merged.length - existing.length;
  let totalCount = apiTotalCount;
  let hasMore = hasMoreOffsetItems(merged.length, totalCount);

  if (appendedCount === 0 && merged.length < totalCount) {
    totalCount = reconcileOffsetTotalAfterStall(merged.length, totalCount);
    hasMore = false;
  }

  return { merged, appendedCount, totalCount, hasMore };
}

export function replaceOffsetWindowById<T extends { id: string }>(incoming: T[]): T[] {
  return [...incoming];
}
