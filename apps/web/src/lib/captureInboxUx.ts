import type { CapturedItem, CaptureSession } from "../types/capture-inbox";

export type CaptureInboxSortMode =
  | "ready_first"
  | "recently_captured"
  | "newest_posted"
  | "oldest_posted"
  | "highest_views"
  | "highest_likes"
  | "highest_comments"
  | "highest_shares"
  | "highest_engagement"
  | "highest_reup_score"
  | "lowest_reup_score"
  | "shortest_duration"
  | "longest_duration";

export const CAPTURE_INBOX_SIMPLE_DEFAULT_SORT: CaptureInboxSortMode = "highest_reup_score";
export const CAPTURE_INBOX_SIMPLE_DEFAULT_FILTER = "ready" as const;
export const CAPTURE_INBOX_POWER_DEFAULT_SORT: CaptureInboxSortMode = "ready_first";

export function isCaptureInboxPromotableStatus(status: CapturedItem["status"]): boolean {
  return status === "READY" || status === "ENRICHED" || status === "PREVIEW_MISSING";
}

export function sortCaptureSessionsNewestFirst(sessions: CaptureSession[]): CaptureSession[] {
  return [...sessions].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
}

export function pickLatestCaptureSessionId(sessions: CaptureSession[]): string | null {
  return sortCaptureSessionsNewestFirst(sessions)[0]?.id ?? null;
}

export function isLatestCaptureSession(session: CaptureSession, sessions: CaptureSession[]): boolean {
  const latestId = pickLatestCaptureSessionId(sessions);
  return latestId != null && session.id === latestId;
}

export function selectTopPromotableCaptureItems(items: CapturedItem[], limit: number): CapturedItem[] {
  const safeLimit = Math.max(0, Math.floor(limit));
  if (safeLimit === 0) return [];
  return items.filter((item) => isCaptureInboxPromotableStatus(item.status)).slice(0, safeLimit);
}

export function captureInboxSortLabel(sortMode: CaptureInboxSortMode): string {
  const labels: Record<CaptureInboxSortMode, string> = {
    ready_first: "Ready first",
    recently_captured: "Recently captured",
    newest_posted: "Newest posted",
    oldest_posted: "Oldest posted",
    highest_views: "Highest views",
    highest_likes: "Highest likes",
    highest_comments: "Highest comments",
    highest_shares: "Highest shares",
    highest_engagement: "Highest engagement",
    highest_reup_score: "Highest Reup Score",
    lowest_reup_score: "Lowest Reup Score",
    shortest_duration: "Shortest duration",
    longest_duration: "Longest duration"
  };
  return labels[sortMode];
}
