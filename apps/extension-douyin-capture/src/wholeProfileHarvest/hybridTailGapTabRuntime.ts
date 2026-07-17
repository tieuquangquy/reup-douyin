import type { ExtensionMessage, ExtensionMessageResponse } from "../types.js";
import { profileIdentifierFromUrl } from "./profileTargetRepository.js";

const PROFILE_POST_PAGE_MESSAGE = "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B" as const;

/** Hard caps for optional tail-gap DOM scroll — never reuse full-profile 80×120s scan. */
export const TAIL_GAP_DOM_SCROLL_MAX_ROUNDS = 6;
export const TAIL_GAP_DOM_SCROLL_MAX_DURATION_MS = 15_000;

export type TailGapDomScrollPolicy = {
  shouldScroll: boolean;
  maxRounds: number;
  maxDurationMs: number;
  reason: string;
};

/**
 * Tail-gap collect must not force infinite/full-grid scroll.
 * Default: quick DOM probe only. Capped scroll only when explicitly allowed and probe is empty.
 */
export function resolveTailGapDomScrollPolicy(args: {
  forceDomScroll?: boolean;
  allowCappedDomScroll?: boolean;
  quickProbeIdCount: number;
}): TailGapDomScrollPolicy {
  const caps = {
    maxRounds: TAIL_GAP_DOM_SCROLL_MAX_ROUNDS,
    maxDurationMs: TAIL_GAP_DOM_SCROLL_MAX_DURATION_MS
  };
  // forceDomScroll is intentionally ignored for infinite-scroll safety; use allowCappedDomScroll.
  if (args.forceDomScroll === true && args.allowCappedDomScroll !== true) {
    return { shouldScroll: false, ...caps, reason: "force_dom_scroll_disabled_use_profile_post" };
  }
  if (args.allowCappedDomScroll === true && args.quickProbeIdCount <= 0) {
    return { shouldScroll: true, ...caps, reason: "capped_scroll_empty_quick_probe" };
  }
  return { shouldScroll: false, ...caps, reason: "quick_probe_only" };
}

function isSupportedDouyinUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.hostname.includes("douyin.com");
  } catch {
    return false;
  }
}

async function sleepMs(delayMs: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, Math.max(0, delayMs)));
}

export async function ensureDouyinTabForHybridTailGapCollect(
  profileUrl: string,
  resolvePreferredTab: (profileUrl: string | null) => Promise<{ id: number | null; url: string | null }>
): Promise<{
  id: number;
  url: string | null;
  navigated: boolean;
  created: boolean;
}> {
  const trimmed = profileUrl.trim();
  if (!trimmed) throw new Error("profile_url_missing");
  const preferredProfileId = profileIdentifierFromUrl(trimmed);
  const preferred = await resolvePreferredTab(trimmed);
  if (preferred.id && isSupportedDouyinUrl(preferred.url ?? "")) {
    const tabProfileId = profileIdentifierFromUrl(preferred.url ?? "");
    if (!preferredProfileId || tabProfileId === preferredProfileId) {
      return { id: preferred.id, url: preferred.url ?? trimmed, navigated: false, created: false };
    }
  }
  const douyinTabs = [
    ...(await chrome.tabs.query({ url: "https://www.douyin.com/*" })),
    ...(await chrome.tabs.query({ url: "https://*.douyin.com/*" }))
  ].filter((tab, index, all) => tab.id && isSupportedDouyinUrl(tab.url ?? "") && all.findIndex((candidate) => candidate.id === tab.id) === index);
  if (douyinTabs[0]?.id) {
    const tabId = douyinTabs[0].id;
    await chrome.tabs.update(tabId, { url: trimmed, active: true });
    await sleepMs(2_500);
    return { id: tabId, url: trimmed, navigated: true, created: false };
  }
  const created = await chrome.tabs.create({ url: trimmed, active: true });
  if (!created.id) throw new Error("douyin_tab_create_failed");
  await sleepMs(3_500);
  return { id: created.id, url: trimmed, navigated: false, created: true };
}

export async function fetchProfilePostPageFromHybridTab(
  tabId: number,
  profileUrl: string,
  cursor: string | number | null,
  pageIndex: number
): Promise<{
  ok: boolean;
  verified_target_details: Array<Record<string, unknown>>;
  has_more: boolean | null;
  next_cursor: string | number | null;
  stop_reason: string;
}> {
  const response = await chrome.tabs.sendMessage(tabId, {
    type: PROFILE_POST_PAGE_MESSAGE,
    profileUrl,
    expected_profile_url: profileUrl,
    cursor: cursor ?? 0,
    page_index: pageIndex,
    traceVersion: "22C-14B"
  } satisfies ExtensionMessage).catch((error) => ({
    ok: false,
    stop_reason: "page_fetch_message_failed",
    verified_target_details: [],
    diagnostics: { scan_job_last_error: error instanceof Error ? error.message : String(error) }
  })) as ExtensionMessageResponse;
  const responseDiagnostics = response.diagnostics && typeof response.diagnostics === "object"
    ? response.diagnostics as Record<string, unknown>
    : {};
  const nextCursor = responseDiagnostics.scan_job_cursor
    ?? responseDiagnostics.active_profile_post_page_fetch_next_cursor_22C14B
    ?? null;
  const hasMoreRaw = responseDiagnostics.scan_job_has_more_state
    ?? responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B
    ?? null;
  const hasMore = typeof hasMoreRaw === "boolean" ? hasMoreRaw : null;
  return {
    ok: response.ok === true,
    verified_target_details: Array.isArray(response.verified_target_details)
      ? response.verified_target_details.filter((detail): detail is Record<string, unknown> => Boolean(detail) && typeof detail === "object")
      : [],
    has_more: hasMore,
    next_cursor: typeof nextCursor === "string" || typeof nextCursor === "number" ? nextCursor : null,
    stop_reason: String(
      responseDiagnostics.active_profile_post_page_fetch_stop_reason_22C14B
        ?? response.stop_reason
        ?? response.reason
        ?? "unknown"
    )
  };
}

export async function readDomTailReconcileProbeFromHybridTab(
  tabId: number,
  profileUrl: string,
  options: { forceDomScroll?: boolean; allowCappedDomScroll?: boolean } = {}
): Promise<Record<string, unknown>> {
  const countDomIds = (diag: Record<string, unknown>): number => {
    const ids = diag.tail_reconcile_candidate_ids;
    return Array.isArray(ids) ? ids.length : 0;
  };
  const readQuickProbe = async (): Promise<Record<string, unknown>> => {
    const response = await chrome.tabs.sendMessage(tabId, {
      type: "DOUYIN_PROFILE_DOM_PROBE_22C11B",
      expected_profile_url: profileUrl,
      traceVersion: "22C-14E"
    } satisfies ExtensionMessage).catch(() => null) as ExtensionMessageResponse | null;
    if (response?.diagnostics && typeof response.diagnostics === "object") {
      return response.diagnostics as Record<string, unknown>;
    }
    if (response?.profile_dom_probe && typeof response.profile_dom_probe === "object") {
      return response.profile_dom_probe as Record<string, unknown>;
    }
    return {};
  };
  let diagnostics = await readQuickProbe();
  diagnostics.hybrid_tail_gap_dom_probe_attempt = 1;
  if (countDomIds(diagnostics) < 15) {
    await sleepMs(1_500);
    diagnostics = {
      ...(await readQuickProbe()),
      hybrid_tail_gap_dom_probe_attempt: 2
    };
  }
  const policy = resolveTailGapDomScrollPolicy({
    ...(options.forceDomScroll === true ? { forceDomScroll: true } : {}),
    ...(options.allowCappedDomScroll === true ? { allowCappedDomScroll: true } : {}),
    quickProbeIdCount: countDomIds(diagnostics)
  });
  diagnostics.hybrid_tail_gap_dom_scroll_policy = policy.reason;
  diagnostics.hybrid_tail_gap_dom_scroll_used = "no";
  if (!policy.shouldScroll) {
    return diagnostics;
  }
  await sleepMs(500);
  const scrollResponse = await chrome.tabs.sendMessage(tabId, {
    type: "DOUYIN_HYBRID_TAIL_GAP_DOM_SCROLL_PROBE",
    expected_profile_url: profileUrl,
    profileUrl,
    max_rounds: policy.maxRounds,
    max_duration_ms: policy.maxDurationMs
  } satisfies ExtensionMessage).catch(() => null) as ExtensionMessageResponse | null;
  if (scrollResponse && typeof scrollResponse === "object") {
    const scrollIds = Array.isArray(scrollResponse.tail_reconcile_candidate_ids)
      ? scrollResponse.tail_reconcile_candidate_ids as string[]
      : [];
    const existingIds = Array.isArray(diagnostics.tail_reconcile_candidate_ids)
      ? diagnostics.tail_reconcile_candidate_ids as string[]
      : [];
    const mergedIds = [...new Set([...existingIds, ...scrollIds])];
    const scrollDiagnostics = scrollResponse.diagnostics && typeof scrollResponse.diagnostics === "object"
      ? scrollResponse.diagnostics as Record<string, unknown>
      : {};
    diagnostics = {
      ...diagnostics,
      ...scrollDiagnostics,
      tail_reconcile_candidate_ids: mergedIds,
      hybrid_tail_gap_dom_scroll_used: scrollIds.length > 0 ? "capped_yes" : "capped_attempted",
      hybrid_tail_gap_dom_scroll_found: scrollIds.length,
      hybrid_tail_gap_dom_scroll_stop_reason: typeof scrollResponse.stop_reason === "string"
        ? scrollResponse.stop_reason
        : scrollResponse.ok === false
          ? "scroll_probe_failed"
          : "unknown",
      hybrid_tail_gap_dom_scroll_policy: policy.reason
    };
  } else {
    diagnostics.hybrid_tail_gap_dom_scroll_used = "message_failed";
  }
  return diagnostics;
}

export function runtimeSupportsHybridTailGapDiscovery(runtime: {
  fetchProfilePostPageFromTab?: unknown;
  readDomTailReconcileProbeFromTab?: unknown;
}): boolean {
  return typeof runtime.fetchProfilePostPageFromTab === "function"
    && typeof runtime.readDomTailReconcileProbeFromTab === "function";
}
