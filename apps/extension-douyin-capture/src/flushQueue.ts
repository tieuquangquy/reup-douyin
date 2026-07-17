import type { ExtensionBackendErrorCode, FullModalHarvestItemPayload, FullModalHarvestPendingFlushItem } from "./types.js";

export const FULL_MODAL_HARVEST_FLUSH_QUEUE_KEY = "reupDouyinFullModalHarvestFlushQueue";

export function buildPendingFlushItem(item: FullModalHarvestItemPayload, captureSessionId: string | null, now = new Date()): FullModalHarvestPendingFlushItem {
  return {
    id: `${captureSessionId ?? "no-session"}:${item.aweme_id}`,
    capture_session_id: captureSessionId,
    aweme_id: item.aweme_id,
    payload_item: item,
    created_at: now.toISOString(),
    attempts: 0,
    last_error: null,
    last_error_code: null,
    status: "pending"
  };
}

export function upsertPendingFlushItem(queue: FullModalHarvestPendingFlushItem[], item: FullModalHarvestPendingFlushItem): FullModalHarvestPendingFlushItem[] {
  const existingIndex = queue.findIndex((entry) => entry.id === item.id || entry.aweme_id === item.aweme_id);
  if (existingIndex < 0) return [...queue, item];
  const next = queue.slice();
  const existing = next[existingIndex];
  if (!existing) return [...queue, item];
  next[existingIndex] = {
    ...existing,
    payload_item: item.payload_item,
    capture_session_id: item.capture_session_id,
    status: existing.status === "flushed" ? "flushed" : item.status
  };
  return next;
}

export function markQueueFlushing(queue: FullModalHarvestPendingFlushItem[], awemeIds: string[]): FullModalHarvestPendingFlushItem[] {
  const ids = new Set(awemeIds);
  return queue.map((item) => (ids.has(item.aweme_id) ? { ...item, attempts: item.attempts + 1, status: "flushing" } : item));
}

export function markQueueFlushed(queue: FullModalHarvestPendingFlushItem[], awemeIds: string[]): FullModalHarvestPendingFlushItem[] {
  const ids = new Set(awemeIds);
  return queue.map((item) => (ids.has(item.aweme_id) ? { ...item, status: "flushed", last_error: null, last_error_code: null } : item));
}

export function markQueueFailed(queue: FullModalHarvestPendingFlushItem[], awemeIds: string[], error: { code?: ExtensionBackendErrorCode | null; message: string; retryable: boolean }): FullModalHarvestPendingFlushItem[] {
  const ids = new Set(awemeIds);
  return queue.map((item) =>
    ids.has(item.aweme_id)
      ? {
          ...item,
          status: error.retryable ? "failed_retryable" : "failed_terminal",
          last_error: error.message,
          last_error_code: error.code ?? null
        }
      : item
  );
}

export function retryablePendingItems(queue: FullModalHarvestPendingFlushItem[]): FullModalHarvestPendingFlushItem[] {
  return queue.filter((item) => item.status === "pending" || item.status === "failed_retryable" || item.status === "flushing");
}

export function isRetryableFlushError(code: ExtensionBackendErrorCode | null | undefined, statusCode: number | null | undefined): boolean {
  if (code === "http_422_schema_error" || code === "http_4xx_client_error") return false;
  if (typeof statusCode === "number" && statusCode >= 400 && statusCode < 500 && statusCode !== 408 && statusCode !== 429) return false;
  return true;
}
