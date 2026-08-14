export type CaptureInboxItemsLoadScope = "profile" | "session";

export type CaptureItemMergeIdentity = {
  id: string;
  source_video_external_id?: string | null;
  aweme_id?: string | null;
};

export type CaptureSessionProfileCandidate = {
  id: string;
  captured_item_count: number;
  normalized_profile_identifier: string | null;
  submitted_profile_url?: string | null;
};

export function hasMoreCapturedItems(loadedCount: number, totalCount: number): boolean {
  return loadedCount < totalCount;
}

export function hasMoreCapturedItemsAfterPage(
  loadedCount: number,
  totalCount: number,
  incomingCount: number,
  appendedCount: number
): boolean {
  if (loadedCount >= totalCount) return false;
  if (incomingCount === 0) return false;
  if (appendedCount === 0) return false;
  return loadedCount < totalCount;
}

export function shouldUseProfileItemsScope(
  profileUrlFromQuery: string | null,
  itemsLoadScope: CaptureInboxItemsLoadScope
): boolean {
  return Boolean(profileUrlFromQuery) && itemsLoadScope === "profile";
}

export type CaptureSessionSummaryCounts = {
  captured_item_count: number;
  ready_item_count: number;
  duplicate_item_count: number;
  failed_item_count: number;
  promoted_item_count?: number;
};

export function computeSessionNeedsActionCount(session: CaptureSessionSummaryCounts): number {
  return Math.max(
    0,
    session.captured_item_count
      - session.ready_item_count
      - session.duplicate_item_count
      - session.failed_item_count
      - (session.promoted_item_count ?? 0)
  );
}

export function resolveItemsLoadScopeForSession(
  profileUrlFromQuery: string | null,
  sessionId: string | null,
  matchedProfileSessionId: string | null,
  manualSessionSelection = false
): CaptureInboxItemsLoadScope {
  if (!profileUrlFromQuery) return "session";
  if (manualSessionSelection) return "session";
  if (!matchedProfileSessionId) return "session";
  return sessionId === matchedProfileSessionId ? "profile" : "session";
}

export function captureItemMergeKey(item: CaptureItemMergeIdentity, scope: CaptureInboxItemsLoadScope): string {
  if (scope === "profile") {
    return item.source_video_external_id ?? item.aweme_id ?? item.id;
  }
  return item.id;
}

export function mergeCapturedItemsPage<T extends CaptureItemMergeIdentity>(
  current: T[],
  incoming: T[],
  scope: CaptureInboxItemsLoadScope
): { merged: T[]; appendedCount: number } {
  if (!incoming.length) {
    return { merged: current, appendedCount: 0 };
  }
  const seen = new Set(current.map((item) => captureItemMergeKey(item, scope)));
  const appended: T[] = [];
  for (const item of incoming) {
    const key = captureItemMergeKey(item, scope);
    if (seen.has(key)) continue;
    seen.add(key);
    appended.push(item);
  }
  return {
    merged: appended.length ? [...current, ...appended] : current,
    appendedCount: appended.length
  };
}

export function resolveGalleryTotalCount(
  scope: CaptureInboxItemsLoadScope,
  apiTotalCount: number,
  uniqueVideoCount?: number | null
): number {
  if (scope === "profile" && uniqueVideoCount != null && uniqueVideoCount >= 0) {
    return uniqueVideoCount;
  }
  return apiTotalCount;
}

export function reconcileGalleryTotalAfterStall(loadedCount: number, apiTotalCount: number): number {
  return loadedCount < apiTotalCount ? loadedCount : apiTotalCount;
}

export function stripProfileUrlQuery(url: string): string {
  try {
    const parsed = new URL(url);
    parsed.search = "";
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return url.split("?")[0]?.replace(/\/$/, "") ?? url;
  }
}

export function sessionMatchesProfileContext(
  session: CaptureSessionProfileCandidate,
  profileUrl: string,
  profileIdentifier: string | null
): boolean {
  if (profileIdentifier && session.normalized_profile_identifier === profileIdentifier) {
    return true;
  }
  const submitted = session.submitted_profile_url?.trim();
  if (!submitted) {
    return false;
  }
  return stripProfileUrlQuery(submitted) === stripProfileUrlQuery(profileUrl);
}

export function pickProfileMatchedSessionId(
  sessions: CaptureSessionProfileCandidate[],
  profileUrl: string,
  profileIdentifier: string | null
): string | null {
  const matches = sessions.filter((session) => sessionMatchesProfileContext(session, profileUrl, profileIdentifier));
  if (!matches.length) return null;
  return matches.reduce((best, session) => (
    session.captured_item_count > best.captured_item_count ? session : best
  )).id;
}

export function shouldAutoLoadCaptureTail(
  loadedCount: number,
  totalCount: number,
  pageSize: number
): boolean {
  const remaining = totalCount - loadedCount;
  return remaining > 0 && remaining <= pageSize * 2;
}

export function shouldKeepManualSessionSelection(
  manualSessionId: string | null,
  matchedProfileSessionId: string | null,
  selectedSessionId: string | null
): boolean {
  if (!manualSessionId || !matchedProfileSessionId) return false;
  return manualSessionId !== matchedProfileSessionId && manualSessionId === selectedSessionId;
}
