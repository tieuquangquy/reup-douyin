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

export function mergeOffsetItemsById<T extends { id: string }>(existing: T[], incoming: T[]): T[] {
  if (incoming.length === 0) return existing;
  const seen = new Set(existing.map((item) => item.id));
  const appended = incoming.filter((item) => !seen.has(item.id));
  return [...existing, ...appended];
}

export function replaceOffsetWindowById<T extends { id: string }>(incoming: T[]): T[] {
  return [...incoming];
}
