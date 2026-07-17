import { CAPTURE_CURRENT_PAGE_SCHEMA_VERSION } from "./requestPayloads.js";
import type { DouyinPageType, ExtensionCapturePayload, ExtensionMessageResponse, PageSnapshot, VideoPayload } from "./types.js";

const TARGET_DEBUG_AWEME_IDS = new Set(["7628281732369796388", "7631223404342857006", "7628596519502892307"]);

export type ExtensionDirectAction = "detect" | "capture";

export type ExtensionDirectExecutionErrorCode =
  | "no_active_tab"
  | "unsupported_tab"
  | "unsupported_douyin_page"
  | "login_page"
  | "challenge_page"
  | "capture_not_supported"
  | "direct_execution_failed";

export class ExtensionDirectExecutionError extends Error {
  readonly code: ExtensionDirectExecutionErrorCode;

  constructor(code: ExtensionDirectExecutionErrorCode, message: string) {
    super(message);
    this.name = "ExtensionDirectExecutionError";
    this.code = code;
  }
}

export type ActiveTab = {
  id?: number;
  url?: string;
};

export type DirectExecutionRuntime = {
  queryActiveTab(): Promise<ActiveTab | null>;
  executeInTab(tabId: number, action: ExtensionDirectAction): Promise<DirectExecutionResult>;
};

export type DirectExecutionResult = {
  ok: boolean;
  page?: PageSnapshot;
  payload?: ExtensionCapturePayload;
  error_code?: ExtensionDirectExecutionErrorCode;
  error?: string;
};

export const OPERATOR_MESSAGES: Record<ExtensionDirectExecutionErrorCode, string> = {
  no_active_tab: "No active tab is available. Open a supported Douyin tab and try again.",
  unsupported_tab: "Open a supported Douyin page and refresh it, then try again.",
  unsupported_douyin_page: "This Douyin page is not supported for capture. Open a profile, feed, or video page and try again.",
  login_page: "This Douyin page is asking for login. Log in in the browser, refresh the page, and try again.",
  challenge_page: "Douyin is showing a challenge. Solve it in the browser, refresh the page, and try again.",
  capture_not_supported: "Capture is not supported on this Douyin page. Open a profile, feed, or video page and try again.",
  direct_execution_failed: "Could not execute the Douyin detector in this tab. Reconnect Douyin Tab. If reconnect fails, reload the extension, then hard refresh the Douyin tab."
};

export function createChromeDirectExecutionRuntime(): DirectExecutionRuntime {
  return {
    async queryActiveTab() {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      return tab ?? null;
    },
    async executeInTab(tabId, action) {
      const contentScriptResponse = await tryContentScriptAction(tabId, action);
      if (contentScriptResponse) return attachTabContext(contentScriptResponse, tabId);
      const [result] = await chrome.scripting.executeScript({ target: { tabId }, func: runDouyinActionInPage, args: [action, CAPTURE_CURRENT_PAGE_SCHEMA_VERSION] });
      const value = result?.result;
      if (!value || typeof value !== "object") {
        return { ok: false, error_code: "direct_execution_failed", error: OPERATOR_MESSAGES.direct_execution_failed };
      }
      return attachTabContext(value as DirectExecutionResult, tabId);
    }
  };
}

export async function executeCurrentTabAction(
  action: ExtensionDirectAction,
  runtime: DirectExecutionRuntime = createChromeDirectExecutionRuntime(),
  options: { timeoutMs?: number } = {}
): Promise<DirectExecutionResult> {
  const timeoutMs = options.timeoutMs ?? 8_000;
  const tab = await withDirectExecutionTimeout(runtime.queryActiveTab(), timeoutMs);
  if (!tab?.id || !tab.url) throw friendlyError("no_active_tab");
  if (!isSupportedDouyinUrl(tab.url)) throw friendlyError("unsupported_tab");

  let response: DirectExecutionResult;
  try {
    response = await withDirectExecutionTimeout(runtime.executeInTab(tab.id, action), timeoutMs);
  } catch (error) {
    if (error instanceof ExtensionDirectExecutionError) throw error;
    throw friendlyError("direct_execution_failed");
  }

  return normalizeDirectExecutionResponse(response, action);
}

async function tryContentScriptAction(tabId: number, action: ExtensionDirectAction): Promise<DirectExecutionResult | null> {
  try {
    const response = (await chrome.tabs.sendMessage(tabId, { type: action === "detect" ? "REUP_DOUYIN_DETECT" : "REUP_DOUYIN_CAPTURE", tab_id: tabId })) as ExtensionMessageResponse;
    if (!response?.ok) return null;
    if (action === "detect" && response.page) return { ok: true, page: response.page };
    if (action === "capture" && response.payload) return { ok: true, payload: response.payload };
    return null;
  } catch {
    return null;
  }
}

export function isSupportedDouyinUrl(value: string): boolean {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }

  if (url.protocol !== "https:") return false;
  const hostname = url.hostname.toLowerCase();
  return hostname === "www.douyin.com" || hostname.endsWith(".douyin.com") || hostname.endsWith(".iesdouyin.com");
}

export function projectDirectExecutionError(error: unknown): { code: ExtensionDirectExecutionErrorCode; message: string } {
  if (error instanceof ExtensionDirectExecutionError) return { code: error.code, message: error.message };
  return { code: "direct_execution_failed", message: OPERATOR_MESSAGES.direct_execution_failed };
}

function attachTabContext(response: DirectExecutionResult, tabId: number): DirectExecutionResult {
  if (!response.payload) return response;
  const captureContext = {
    ...(response.payload.capture_context ?? {}),
    capture_id: response.payload.capture_id,
    captured_at: response.payload.captured_at,
    tab_id: tabId
  };
  return {
    ...response,
    payload: {
      ...response.payload,
      capture_context: captureContext,
      videos: response.payload.videos.map((video) => ({
        ...video,
        capture_context: { ...(video.capture_context ?? captureContext), tab_id: tabId }
      }))
    }
  };
}

function normalizeDirectExecutionResponse(response: DirectExecutionResult, action: ExtensionDirectAction): DirectExecutionResult {
  if (response.ok) {
    if (action === "detect" && response.page) return response;
    if (action === "capture" && response.payload) return response;
  }

  throw friendlyError(response.error_code ?? (action === "capture" ? "capture_not_supported" : "direct_execution_failed"));
}

function friendlyError(code: ExtensionDirectExecutionErrorCode): ExtensionDirectExecutionError {
  return new ExtensionDirectExecutionError(code, OPERATOR_MESSAGES[code]);
}

function withDirectExecutionTimeout<T>(operation: Promise<T>, timeoutMs: number): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => reject(friendlyError("direct_execution_failed")), timeoutMs);
  });

  return Promise.race([operation, timeout]).finally(() => {
    if (timeoutId) clearTimeout(timeoutId);
  });
}

function runDouyinActionInPage(action: ExtensionDirectAction, captureSchemaVersion: ExtensionCapturePayload["schema_version"]): DirectExecutionResult {
  const VERSION = "0.1.0";
  const MAX_BODY_SAMPLE_LENGTH = 1600;
  const MAX_VIDEOS = 120;

  try {
    const page = detectPage();
    const blockingCode = blockingPageCode(page.page_type);
    if (blockingCode) return { ok: false, page, error_code: blockingCode, error: blockingCode };

    if (action === "detect") return { ok: true, page };

    if (!isCapturablePage(page.page_type)) {
      return { ok: false, page, error_code: page.page_type === "unsupported_page" || page.page_type === "unknown_page" ? "unsupported_douyin_page" : "capture_not_supported", error: page.page_type };
    }

    const profile = extractProfile(window.location.href);
    const captureId = crypto.randomUUID();
    const capturedAt = new Date().toISOString();
    const captureContext = buildCaptureContext(page, profile, captureId, capturedAt);
    const discoveryDiagnostics = createDiscoveryDiagnostics();
    const videos = extractVideos(captureContext, discoveryDiagnostics).slice(0, MAX_VIDEOS);
    const payload: ExtensionCapturePayload = {
      schema_version: captureSchemaVersion,
      capture_id: captureId,
      captured_at: capturedAt,
      page: { ...page, video_link_count: Math.max(page.video_link_count, videos.length) },
      profile,
      capture_context: captureContext,
      videos,
      diagnostics: {
        extension_version: VERSION,
        extractor: "direct_execute_script_dom_fallback_v1",
        network_metadata_available: false,
        visible_video_count: videos.length,
        page_type: page.page_type,
        thumbnail_candidate_video_count: videos.filter((video) => Boolean(video.thumbnail_url)).length,
        thumbnail_candidate_total_count: videos.reduce((total, video) => total + (video.url_list?.length ?? 0), 0),
        thumbnail_source_types: uniqueStrings(videos.flatMap((video) => video.thumbnail_source_types ?? [])).join(",") || null,
        duration_text_video_count: videos.filter((video) => Boolean(video.duration_text)).length,
        posted_text_video_count: videos.filter((video) => Boolean(video.posted_text)).length,
        view_count_video_count: videos.filter((video) => typeof video.view_count === "number" || Boolean(video.view_count_text)).length,
        like_count_video_count: videos.filter((video) => typeof video.like_count === "number" || Boolean(video.like_count_text)).length,
        comment_count_video_count: videos.filter((video) => typeof video.comment_count === "number" || Boolean(video.comment_count_text)).length,
        discovery_active_grid_root_strategy: discoveryDiagnostics.active_grid_root_strategy,
        discovery_candidate_link_count: discoveryDiagnostics.candidate_link_count,
        discovery_eligible_tile_count: discoveryDiagnostics.eligible_tile_count,
        discovery_deduped_aweme_count: discoveryDiagnostics.deduped_aweme_count,
        discovery_rejected_link_count: discoveryDiagnostics.rejected_link_count,
        discovery_rejected_reason_counts: JSON.stringify(discoveryDiagnostics.rejected_reason_counts)
      }
    };
    return { ok: true, payload };
  } catch (error) {
    return { ok: false, error_code: "direct_execution_failed", error: error instanceof Error ? error.message : "direct execution failed" };
  }

  function detectPage(): PageSnapshot {
    const locationHref = window.location.href;
    const title = document.title || null;
    const bodyText = compactText(document.body?.innerText || "").slice(0, MAX_BODY_SAMPLE_LENGTH);
    const videoLinks = collectVideoLinks(document);
    const pageType = classifyPage(locationHref, title, bodyText, videoLinks.length);
    const profileUrl = profileUrlFromPage(locationHref);
    const profile = extractProfile(locationHref);
    return {
      url: locationHref,
      title,
      body_text_sample: bodyText,
      page_type: pageType,
      profile_url: profileUrl,
      profile_external_id: profile?.sec_uid ?? profile?.id ?? profileExternalIdFromUrl(profileUrl),
      handle: profile?.handle ?? handleFromUrl(locationHref),
      display_name: profile?.display_name ?? null,
      video_link_count: videoLinks.length
    };
  }

  function classifyPage(url: string, title: string | null, bodyText: string | null, videoLinkCount: number): DouyinPageType {
    let parsed: URL;
    try {
      parsed = new URL(url);
    } catch {
      return "unknown_page";
    }
    const host = parsed.hostname.toLowerCase();
    const path = parsed.pathname.replace(/^\/+|\/+$/g, "");
    const lowered = `${title ?? ""} ${bodyText ?? ""} ${url}`.toLowerCase();
    if (!host.includes("douyin.com") && !host.includes("iesdouyin.com")) return "unsupported_page";
    if (containsAny(lowered, ["captcha", "security check", "verify you are human", "验证码", "安全验证"])) return "challenge_page";
    if (containsAny(lowered, ["passport", "login", "登录", "请先登录"])) return "login_page";
    if (/(^|\/)video\/[^/?#]+/.test(path)) return "video_detail_page";
    if (/(^|\/)user\/[^/?#]+/.test(path) || path.startsWith("@")) return videoLinkCount > 0 ? "profile_feed_page" : "profile_page";
    if (["", "discover", "follow", "recommend"].includes(path)) return "home_feed_page";
    return "unknown_page";
  }

  type GridDiscoveryRecord = {
    aweme_id: string;
    source_url: string;
    share_url: string | null;
    visible_order: number;
    link: HTMLAnchorElement;
  };

  type DiscoveryRejectReason =
    | "stray_video_link"
    | "outside_active_grid"
    | "detached_node"
    | "hidden_node"
    | "invalid_visibility"
    | "non_active_profile_tab"
    | "modal_link"
    | "no_tile_media_frame"
    | "duplicate_aweme_in_grid";

  type DiscoveryDiagnostics = {
    active_grid_root_strategy: string;
    candidate_link_count: number;
    eligible_tile_count: number;
    deduped_aweme_count: number;
    rejected_link_count: number;
    rejected_reason_counts: Record<string, number>;
  };

  type DomFallbackMetadata = {
    aweme_id: string;
    title: string | null;
    thumbnail: Partial<VideoPayload>;
    duration: { duration_text: string | null; duration_seconds: number | null };
    posted: { posted_text: string | null; posted_at: string | null };
    metrics: ExtractedMetrics;
    card: HTMLElement | null;
    text: string;
  };

  function extractVideos(captureContext: ExtensionCapturePayload["capture_context"], discoveryDiagnostics: DiscoveryDiagnostics = createDiscoveryDiagnostics()): VideoPayload[] {
    return discoverGridVideos(discoveryDiagnostics).map((discovery) => buildCanonicalVideoPayload(discovery, buildDomFallbackMetadata(discovery), captureContext));
  }

  function buildCaptureContext(page: PageSnapshot, profile: ReturnType<typeof extractProfile>, captureId: string, capturedAt: string) {
    const pageUrl = page.url ?? window.location.href;
    const profileUrl = page.profile_url ?? null;
    const profileExternalId = page.profile_external_id ?? profile?.sec_uid ?? profile?.id ?? profileExternalIdFromUrl(profileUrl) ?? null;
    const pageUrlNormalized = normalizeContextUrl(pageUrl);
    return {
      capture_id: captureId,
      tab_id: null,
      page_url: pageUrl,
      page_url_normalized: pageUrlNormalized,
      profile_url: profileUrl,
      profile_external_id: profileExternalId,
      captured_at: capturedAt,
      cache_scope_key: [pageUrlNormalized, profileUrl, profileExternalId].filter(Boolean).join("|") || null
    };
  }

  function normalizeContextUrl(value: string | null | undefined): string | null {
    if (!value) return null;
    try {
      const parsed = new URL(value, "https://www.douyin.com");
      return `${parsed.origin}${parsed.pathname.replace(/\/+$/, "")}`;
    } catch {
      return null;
    }
  }

  function discoverGridVideos(diagnostics: DiscoveryDiagnostics = createDiscoveryDiagnostics()): GridDiscoveryRecord[] {
    const activeGridRoot = findActiveWorksGridRoot();
    diagnostics.active_grid_root_strategy = activeGridRoot ? "active_grid_root" : "document_fallback";
    const scopedRoot: ParentNode = activeGridRoot ?? document;
    const links = collectVideoLinks(scopedRoot);
    diagnostics.candidate_link_count = links.length;
    const discoveries = new Map<string, GridDiscoveryRecord>();
    let visibleOrder = 0;
    for (const link of links) {
      const awemeId = videoIdFromUrl(link.href);
      const rejectReason = discoveryRejectReason(link, awemeId, activeGridRoot);
      if (rejectReason) {
        diagnostics.rejected_link_count += 1;
        diagnostics.rejected_reason_counts[rejectReason] = (diagnostics.rejected_reason_counts[rejectReason] ?? 0) + 1;
        continue;
      }
      diagnostics.eligible_tile_count += 1;
      if (discoveries.has(awemeId as string)) {
        diagnostics.rejected_link_count += 1;
        diagnostics.rejected_reason_counts.duplicate_aweme_in_grid = (diagnostics.rejected_reason_counts.duplicate_aweme_in_grid ?? 0) + 1;
        continue;
      }
      discoveries.set(awemeId as string, {
        aweme_id: awemeId as string,
        source_url: link.href,
        share_url: safeShareUrlForLink(link, awemeId as string),
        visible_order: visibleOrder,
        link
      });
      visibleOrder += 1;
    }
    diagnostics.deduped_aweme_count = discoveries.size;
    return Array.from(discoveries.values());
  }

  function buildDomFallbackMetadata(discovery: GridDiscoveryRecord): DomFallbackMetadata {
    const card = nearestCard(discovery.link);
    const text = cardText(card, discovery.link);
    const metadata: DomFallbackMetadata = {
      aweme_id: discovery.aweme_id,
      title: titleFromCard(card, discovery.link, text),
      thumbnail: thumbnailFromCard(card, discovery.link),
      duration: extractDuration(text),
      posted: extractPosted(text),
      metrics: extractMetrics(text),
      card,
      text
    };
    if (TARGET_DEBUG_AWEME_IDS.has(discovery.aweme_id)) {
      console.info("[targeted-aweme-checkpoint1-precanonical]", {
        aweme_id: discovery.aweme_id,
        posted_at: metadata.posted.posted_at,
        posted_text: metadata.posted.posted_text,
        duration_seconds: metadata.duration.duration_seconds,
        duration_text: metadata.duration.duration_text,
        view_count: metadata.metrics.view_count,
        like_count: metadata.metrics.like_count,
        comment_count: metadata.metrics.comment_count,
        share_count: metadata.metrics.share_count,
        view_count_text: metadata.metrics.view_count_text,
        like_count_text: metadata.metrics.like_count_text,
        comment_count_text: metadata.metrics.comment_count_text,
        share_count_text: null
      });
    }
    return metadata;
  }

  function buildCanonicalVideoPayload(discovery: GridDiscoveryRecord, dom: DomFallbackMetadata, captureContext: ExtensionCapturePayload["capture_context"]): VideoPayload {
    const thumbnailUrl = dom.thumbnail.thumbnail_url ?? null;
    const thumbnailMissingReason = thumbnailUrl ? null : "dom_cover_missing";
    const durationSeconds = dom.duration.duration_seconds ?? null;
    const durationText = dom.duration.duration_text ?? (typeof durationSeconds === "number" ? formatDurationValue(durationSeconds) : null);
    const durationSource = durationSeconds !== null || durationText !== null ? "dom_text" : "fallback_none";
    const rawDomSnapshot = buildRawDomSnapshot(discovery, dom, dom.thumbnail.url_list ?? []);
    const viewCount = validCount(dom.metrics.view_count);
    const likeCount = validCount(dom.metrics.like_count);
    const commentCount = validCount(dom.metrics.comment_count);
    const shareCount = validCount(dom.metrics.share_count);
    const engagementRate = deriveEngagementRate({
      view_count: viewCount,
      like_count: likeCount,
      comment_count: commentCount,
      share_count: shareCount
    });
    const payload: VideoPayload = {
      id: discovery.aweme_id,
      aweme_id: discovery.aweme_id,
      video_id: discovery.aweme_id,
      source_video_url: discovery.source_url,
      share_url: discovery.share_url ?? discovery.source_url,
      url: discovery.source_url,
      title: dom.title,
      desc: dom.title,
      ...dom.thumbnail,
      duration_text: durationText,
      duration_seconds: durationSeconds,
      duration_source: durationSource,
      ...dom.posted,
      view_count: viewCount,
      view_count_source: viewCount !== null ? "dom_text" : "fallback_none",
      view_count_text: dom.metrics.view_count_text,
      like_count: likeCount,
      like_count_source: likeCount !== null ? "dom_text" : "fallback_none",
      like_count_text: dom.metrics.like_count_text,
      comment_count: commentCount,
      comment_count_source: commentCount !== null
        ? commentCount === 0 && parseCommentZeroSentinel(dom.metrics.comment_count_text ?? "") ? "dom_zero_sentinel" : "dom_text"
        : "fallback_none",
      comment_count_text: dom.metrics.comment_count_text,
      share_count: shareCount,
      share_count_source: shareCount !== null ? "dom_text" : "fallback_none",
      engagement_rate: engagementRate,
      engagement_rate_source: engagementRate !== null ? "derived_from_canonical_counts" : "fallback_none",
      has_speech: null,
      text_density: null,
      has_heavy_watermark: null,
      processing_complexity: null,
      copyright_risk: null,
      poster_aspect_ratio: thumbnailUrl ? 9 / 16 : null,
      capture_context: captureContext,
      context_mismatch_codes: [],
      thumbnail_source: thumbnailUrl ? "dom_fallback" : "missing",
      thumbnail_missing_reason: thumbnailMissingReason,
      posted_source: dom.posted.posted_text ? "dom_text" : "fallback_none",
      preview_status: thumbnailUrl ? "ready" : "missing",
      source_link_status: discovery.source_url ? "captured" : "missing",
      media_asset_status: "not_generated",
      media_status: discovery.source_url ? "source_link_captured" : "missing",
      network_source: null,
      raw: {
        visible_text: dom.text.slice(0, 600),
        network_aweme_id: null,
        detail_aweme_id: null,
        network_source: null,
        detail_source: null,
        thumbnail_missing_reason: thumbnailMissingReason,
        ...(TARGET_DEBUG_AWEME_IDS.has(discovery.aweme_id)
          ? {
              _target_debug_checkpoint1_json: JSON.stringify({
                posted_at: dom.posted.posted_at,
                posted_text: dom.posted.posted_text,
                duration_seconds: dom.duration.duration_seconds,
                duration_text: dom.duration.duration_text,
                view_count: dom.metrics.view_count,
                like_count: dom.metrics.like_count,
                comment_count: dom.metrics.comment_count,
                share_count: dom.metrics.share_count
              }),
              _target_debug_checkpoint2_json: JSON.stringify({
                posted_at: dom.posted.posted_at,
                posted_text: dom.posted.posted_text,
                duration_seconds: durationSeconds,
                duration_text: durationText,
                view_count: viewCount,
                like_count: likeCount,
                comment_count: commentCount,
                share_count: shareCount
              })
            }
          : {})
      },
      raw_network_aweme: null,
      raw_detail_aweme: null,
      raw_dom_snapshot: rawDomSnapshot,
      raw_evidence_summary: {
        has_network_aweme: false,
        has_detail_aweme: false,
        has_dom_snapshot: Boolean(rawDomSnapshot),
        network_keys: [],
        detail_keys: [],
        evidence_sources: rawDomSnapshot ? ["dom_snapshot"] : [],
        evidence_collection_version: "phase2"
      },
      extraction_diagnostics: {
        has_card_root: Boolean(dom.card),
        card_text_length: dom.text.length,
        visible_order: discovery.visible_order,
        thumbnail_candidate_count: dom.thumbnail.url_list?.length ?? 0,
        has_network_metadata: false,
        has_detail_hydrate_metadata: false,
        has_dom_fallback_metadata: true,
        grid_metadata_primary: false,
        has_duration_text: Boolean(durationText),
        has_posted_text: Boolean(dom.posted.posted_text),
        has_view_count: typeof dom.metrics.view_count === "number" || Boolean(dom.metrics.view_count_text),
        has_like_count: typeof dom.metrics.like_count === "number" || Boolean(dom.metrics.like_count_text),
        has_comment_count: typeof dom.metrics.comment_count === "number" || Boolean(dom.metrics.comment_count_text),
        thumbnail_missing_reason: thumbnailMissingReason
      },
      statistics: {
        like_count: likeCount,
        comment_count: commentCount,
        share_count: shareCount,
        favorite_count: validCount(dom.metrics.favorite_count),
        view_count: viewCount,
        engagement_rate: engagementRate
      }
    };
    if (TARGET_DEBUG_AWEME_IDS.has(discovery.aweme_id)) {
      console.info("[targeted-aweme-checkpoint2-canonical]", {
        aweme_id: discovery.aweme_id,
        posted_at: payload.posted_at,
        posted_text: payload.posted_text,
        duration_seconds: payload.duration_seconds,
        duration_text: payload.duration_text,
        view_count: payload.view_count,
        like_count: payload.like_count,
        comment_count: payload.comment_count,
        share_count: payload.share_count
      });
    }
    return payload;
  }

  function buildRawDomSnapshot(discovery: GridDiscoveryRecord, dom: DomFallbackMetadata, imageCandidates: string[]) {
    const card = dom.card ?? discovery.link;
    return {
      aweme_id: discovery.aweme_id,
      visible_text: dom.text.slice(0, 1200) || null,
      href: discovery.link.href || null,
      source_url: discovery.source_url || null,
      image_candidates: imageCandidates.slice(0, 20),
      data_attributes: localDataAttributes(card),
      local_text_snippets: localTextSnippets(dom.text)
    };
  }

  function localDataAttributes(root: HTMLElement): Record<string, string> {
    const output: Record<string, string> = {};
    for (const [key, value] of Object.entries(root.dataset).slice(0, 30)) {
      if (!value || isSecretLikeDomKey(key)) continue;
      output[key] = value.slice(0, 240);
    }
    for (const attribute of Array.from(root.attributes).slice(0, 40)) {
      const key = attribute.name.toLowerCase();
      if ((!key.startsWith("data-") && key !== "aria-label" && key !== "title") || isSecretLikeDomKey(key)) continue;
      output[key] = attribute.value.slice(0, 240);
    }
    return output;
  }

  function localTextSnippets(text: string): string[] {
    return uniqueStrings(text.split(/(?<=[。.!?！？])|\n/g).map((entry) => entry.trim().replace(/\s+/g, " ").slice(0, 240)).filter(Boolean)).slice(0, 8);
  }

  function isSecretLikeDomKey(key: string): boolean {
    return /cookie|authorization|auth|token|secret|credential|password|passwd|session|csrf/i.test(key);
  }

  function collectVideoLinks(root: ParentNode): HTMLAnchorElement[] {
    const links = Array.from(root.querySelectorAll<HTMLAnchorElement>('a[href*="/video/"]'));
    return links.filter((link) => {
      try {
        const url = new URL(link.href);
        return url.hostname.includes("douyin.com") && /\/video\/[^/?#]+/.test(url.pathname);
      } catch {
        return false;
      }
    });
  }

  function createDiscoveryDiagnostics(): DiscoveryDiagnostics {
    return {
      active_grid_root_strategy: "unknown",
      candidate_link_count: 0,
      eligible_tile_count: 0,
      deduped_aweme_count: 0,
      rejected_link_count: 0,
      rejected_reason_counts: {}
    };
  }

  function findActiveWorksGridRoot(): HTMLElement | null {
    const candidates = Array.from(
      document.querySelectorAll<HTMLElement>(
        '[data-e2e*="user-post-list"], [data-e2e*="user-post"], [data-e2e*="user-work"], [data-e2e*="post-list"], [data-e2e*="works"], [data-e2e*="feed"], [class*="user-post"], [class*="works"], [class*="feed"]'
      )
    );
    const visibleCandidates = candidates.filter((node) => isEligibleContainer(node));
    if (!visibleCandidates.length) return null;
    const scored = visibleCandidates
      .map((node, index) => ({ node, index, score: videoLinksWithin(node).length * 10 + (hasValidVisibility(node) ? 3 : 0) }))
      .sort((left, right) => right.score - left.score || left.index - right.index);
    return scored[0]?.node ?? null;
  }

  function discoveryRejectReason(link: HTMLAnchorElement, awemeId: string | null, activeGridRoot: HTMLElement | null): DiscoveryRejectReason | null {
    if (!awemeId) return "stray_video_link";
    if (activeGridRoot && !activeGridRoot.contains(link)) return "outside_active_grid";
    if (!isConnectedNode(link)) return "detached_node";
    if (isNodeHidden(link, activeGridRoot)) return "hidden_node";
    if (!hasValidVisibility(link)) return "invalid_visibility";
    if (isNonActiveSection(link, activeGridRoot)) return "non_active_profile_tab";
    if (isModalLike(link)) return "modal_link";
    const card = nearestCard(link);
    if (!card) return "no_tile_media_frame";
    return null;
  }

  function isConnectedNode(element: HTMLElement): boolean {
    if (typeof element.isConnected === "boolean") return element.isConnected;
    return true;
  }

  function hasValidVisibility(element: HTMLElement): boolean {
    const rect = typeof element.getBoundingClientRect === "function" ? element.getBoundingClientRect() : null;
    if (!rect) return true;
    return rect.width > 1 && rect.height > 1;
  }

  function isNodeHidden(element: HTMLElement, boundary: HTMLElement | null): boolean {
    let current: HTMLElement | null = element;
    while (current) {
      const hasHiddenAttr = typeof (current as unknown as { hasAttribute?: (name: string) => boolean }).hasAttribute === "function"
        ? (current as unknown as { hasAttribute: (name: string) => boolean }).hasAttribute("hidden")
        : false;
      const ariaHidden = typeof current.getAttribute === "function" ? current.getAttribute("aria-hidden") : null;
      if (hasHiddenAttr || ariaHidden === "true") return true;
      const style = typeof window !== "undefined" && typeof window.getComputedStyle === "function" ? window.getComputedStyle(current) : null;
      if (style && (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") === 0)) return true;
      if (boundary && current === boundary) break;
      current = current.parentElement;
    }
    return false;
  }

  function isEligibleContainer(element: HTMLElement): boolean {
    if (!isConnectedNode(element)) return false;
    if (isNodeHidden(element, null)) return false;
    if (!hasValidVisibility(element)) return false;
    if (isModalLike(element)) return false;
    return true;
  }

  function isNonActiveSection(element: HTMLElement, boundary: HTMLElement | null): boolean {
    let current: HTMLElement | null = element;
    while (current) {
      const ariaHidden = typeof current.getAttribute === "function" ? current.getAttribute("aria-hidden") : null;
      const dataState = typeof current.getAttribute === "function" ? current.getAttribute("data-state") : null;
      const className = String((current as unknown as { className?: string }).className ?? "").toLowerCase();
      const hasHiddenAttr = typeof (current as unknown as { hasAttribute?: (name: string) => boolean }).hasAttribute === "function"
        ? (current as unknown as { hasAttribute: (name: string) => boolean }).hasAttribute("hidden")
        : false;
      if (ariaHidden === "true" || dataState === "inactive" || hasHiddenAttr || className.includes("inactive") || className.includes("is-hidden")) {
        return !boundary || current !== boundary;
      }
      if (boundary && current === boundary) break;
      current = current.parentElement;
    }
    return false;
  }

  function isModalLike(element: HTMLElement): boolean {
    let current: HTMLElement | null = element;
    while (current) {
      const role = typeof current.getAttribute === "function" ? current.getAttribute("role") : null;
      const ariaModal = typeof current.getAttribute === "function" ? current.getAttribute("aria-modal") : null;
      const hasDataModal = typeof (current as unknown as { hasAttribute?: (name: string) => boolean }).hasAttribute === "function"
        ? (current as unknown as { hasAttribute: (name: string) => boolean }).hasAttribute("data-modal")
        : false;
      const className = String((current as unknown as { className?: string }).className ?? "").toLowerCase();
      const tag = String(current.tagName || "").toLowerCase();
      if (tag === "dialog" || tag === "template" || role === "dialog" || ariaModal === "true" || hasDataModal || className.includes("modal") || className.includes("overlay") || className.includes("popup")) {
        return true;
      }
      current = current.parentElement;
    }
    return false;
  }

  function extractProfile(locationHref: string) {
    const profileUrl = profileUrlFromPage(locationHref);
    const externalId = profileExternalIdFromUrl(profileUrl);
    const handle = handleFromUrl(locationHref);
    const displayName = displayNameFromDocument();
    if (!externalId && !handle && !displayName) return null;
    return {
      id: externalId ?? (handle ? `handle:${handle}` : null),
      sec_uid: externalId,
      handle,
      display_name: displayName
    };
  }

  function nearestCard(link: HTMLAnchorElement): HTMLElement | null {
    const candidates = ancestors(link, 7).filter((element) => element !== document.body && element !== document.documentElement);
    const localCandidates = candidates.filter((element) => element !== link && isLocalCardForLink(element, link));
    const scored = localCandidates
      .map((element, index) => ({ element, score: cardScore(element, link), index }))
      .filter((entry) => entry.score > 0)
      .sort((left, right) => right.score - left.score || left.index - right.index);
    if (scored[0]) return scored[0].element;
    return isLocalCardForLink(link, link) && cardScore(link, link) > 0 ? link : null;
  }

  function ancestors(element: HTMLElement, limit: number): HTMLElement[] {
    const values: HTMLElement[] = [];
    let current: HTMLElement | null = element;
    while (current && values.length < limit) {
      values.push(current);
      current = current.parentElement;
    }
    return values;
  }

  function cardScore(element: HTMLElement, link: HTMLAnchorElement): number {
    if (!isLocalCardForLink(element, link)) return 0;
    let score = 0;
    if (element.matches("li, article, section, [data-e2e], div")) score += 4;
    if (element.matches("li, article, [data-e2e]")) score += 2;
    if (element.querySelector("img, picture, video[poster], source[srcset]")) score += 5;
    if (imageCandidatesFromAttributes(element).length) score += 2;
    if (imageCandidatesFromBackgrounds(element).length) score += 2;
    const text = compactText(element.textContent || link.textContent || "");
    if (extractDuration(text).duration_text) score += 2;
    if (extractPosted(text).posted_text) score += 1;
    const rect = typeof element.getBoundingClientRect === "function" ? element.getBoundingClientRect() : null;
    if (rect && rect.width > 80 && rect.height > 80) score += 2;
    if (text.length > 4 && text.length < 1200) score += 1;
    if (text.length >= 1200) score -= 4;
    return score;
  }

  function isLocalCardForLink(element: HTMLElement, link: HTMLAnchorElement): boolean {
    const currentId = videoIdFromUrl(link.href);
    if (!currentId) return false;
    const links = videoLinksWithin(element);
    const distinctIds = uniqueStrings(links.map((candidate) => videoIdFromUrl(candidate.href)).filter((id): id is string => Boolean(id)));
    return distinctIds.length === 1 && distinctIds[0] === currentId;
  }

  function videoLinksWithin(element: HTMLElement): HTMLAnchorElement[] {
    const links = Array.from(element.querySelectorAll<HTMLAnchorElement>('a[href*="/video/"]'));
    if (element.tagName.toLowerCase() === "a" && (element as HTMLAnchorElement).href.includes("/video/")) links.unshift(element as HTMLAnchorElement);
    return links;
  }

  function cardText(card: HTMLElement | null, link: HTMLAnchorElement): string {
    const values = [card?.textContent, link.textContent, link.getAttribute("aria-label"), link.title, card?.getAttribute("aria-label"), card?.getAttribute("title")];
    return compactText(values.filter(Boolean).join(" "));
  }

  function titleFromCard(card: HTMLElement | null, link: HTMLAnchorElement, text: string): string | null {
    const aria = link.getAttribute("aria-label") || link.title;
    const candidate = compactText(aria || text || "");
    if (!candidate) return null;
    return candidate.slice(0, 240);
  }

  type ThumbnailCandidate = {
    url: string;
    sourceType: string;
  };

  function thumbnailFromCard(card: HTMLElement | null, link: HTMLAnchorElement): Partial<VideoPayload> {
    const roots = [card ?? link].filter(Boolean) as HTMLElement[];
    const candidates: ThumbnailCandidate[] = [];
    for (const root of roots) {
      candidates.push(...imageCandidatesFromMedia(root));
      candidates.push(...imageCandidatesFromAttributes(root));
      candidates.push(...imageCandidatesFromBackgrounds(root));
    }
    const sortedCandidates = candidates.filter((candidate) => isImageLikeUrl(candidate.url)).sort((left, right) => thumbnailCandidateScore(right) - thumbnailCandidateScore(left));
    const urlList = uniqueStrings(sortedCandidates.map((candidate) => candidate.url));
    const thumbnailUrl = urlList[0] ?? null;
    if (!thumbnailUrl) return {};
    return {
      thumbnail_url: thumbnailUrl,
      poster_url: thumbnailUrl,
      cover_url: thumbnailUrl,
      url_list: urlList,
      thumbnail_source_types: uniqueStrings(candidates.filter((candidate) => urlList.includes(candidate.url)).map((candidate) => candidate.sourceType))
    };
  }

  function imageCandidatesFromMedia(root: HTMLElement): ThumbnailCandidate[] {
    const values: ThumbnailCandidate[] = [];
    for (const image of Array.from(root.querySelectorAll<HTMLImageElement>("img"))) {
      pushCandidate(values, image.currentSrc, "img.currentSrc");
      pushCandidate(values, image.src, "img.src");
      pushCandidate(values, image.getAttribute("src"), "img.getAttribute(src)");
      pushCandidate(values, image.getAttribute("data-src"), "img.getAttribute(data-src)");
      pushSrcsetCandidates(values, image.srcset, "img.srcset");
      pushSrcsetCandidates(values, image.getAttribute("srcset"), "img.getAttribute(srcset)");
    }
    for (const source of Array.from(root.querySelectorAll<HTMLSourceElement>("source[srcset]"))) {
      pushSrcsetCandidates(values, source.srcset, "source.srcset");
      pushSrcsetCandidates(values, source.getAttribute("srcset"), "source.getAttribute(srcset)");
    }
    for (const video of Array.from(root.querySelectorAll<HTMLVideoElement>("video[poster]"))) {
      pushCandidate(values, video.poster, "video.poster");
      pushCandidate(values, video.getAttribute("poster"), "video.getAttribute(poster)");
    }
    return values;
  }

  function imageCandidatesFromAttributes(root: HTMLElement): ThumbnailCandidate[] {
    const values: ThumbnailCandidate[] = [];
    for (const element of [root, ...Array.from(root.querySelectorAll<HTMLElement>("*"))]) {
      for (const [key, value] of Object.entries(element.dataset)) {
        if (isThumbnailKey(key)) pushLooseImageCandidates(values, value, `dataset.${key}`);
      }
      for (const attribute of Array.from(element.attributes)) {
        const key = attribute.name.toLowerCase();
        if (key === "src" || key === "data-src" || key === "poster" || isThumbnailKey(key)) {
          pushLooseImageCandidates(values, attribute.value, `attribute.${key}`);
        }
      }
    }
    return values;
  }

  function imageCandidatesFromBackgrounds(root: HTMLElement): ThumbnailCandidate[] {
    const values: ThumbnailCandidate[] = [];
    for (const element of [root, ...Array.from(root.querySelectorAll<HTMLElement>("*"))]) {
      pushBackgroundCandidates(values, element.style.backgroundImage, "inline.backgroundImage");
      pushBackgroundCandidates(values, window.getComputedStyle(element).backgroundImage, "computed.backgroundImage");
    }
    return values;
  }

  function pushCandidate(values: ThumbnailCandidate[], raw: string | null | undefined, sourceType: string): void {
    const value = raw?.trim();
    if (value) values.push({ url: value, sourceType });
  }

  function pushLooseImageCandidates(values: ThumbnailCandidate[], raw: string | null | undefined, sourceType: string): void {
    const value = raw?.trim();
    if (!value) return;
    pushCandidate(values, value, sourceType);
    for (const candidate of srcsetCandidates(value)) pushCandidate(values, candidate, `${sourceType}.srcset`);
    for (const candidate of backgroundImageCandidates(value)) pushCandidate(values, candidate, `${sourceType}.backgroundImage`);
  }

  function pushSrcsetCandidates(values: ThumbnailCandidate[], srcset: string | null | undefined, sourceType: string): void {
    for (const candidate of srcsetCandidates(srcset ?? "")) pushCandidate(values, candidate, sourceType);
  }

  function pushBackgroundCandidates(values: ThumbnailCandidate[], backgroundImage: string | null | undefined, sourceType: string): void {
    for (const candidate of backgroundImageCandidates(backgroundImage ?? "")) pushCandidate(values, candidate, sourceType);
  }

  function backgroundImageCandidates(value: string): string[] {
    return Array.from(value.matchAll(/url\((['"]?)(.*?)\1\)/g)).map((match) => match[2]?.trim() ?? "").filter(Boolean);
  }

  function isThumbnailKey(key: string): boolean {
    const lowered = key.toLowerCase();
    return lowered.includes("thumb") || lowered.includes("cover") || lowered.includes("poster") || lowered.includes("image") || lowered.includes("img");
  }

  function srcsetCandidates(srcset: string): string[] {
    return srcset.split(",").map((entry) => entry.trim().split(/\s+/, 1)[0] ?? "").filter(Boolean);
  }

  function uniqueStrings(values: string[]): string[] {
    const seen = new Set<string>();
    const unique: string[] = [];
    for (const value of values) {
      const trimmed = value.trim();
      if (!trimmed || seen.has(trimmed)) continue;
      seen.add(trimmed);
      unique.push(trimmed);
    }
    return unique;
  }

  function isImageLikeUrl(value: string): boolean {
    const trimmed = value.trim();
    if (trimmed.startsWith("data:image/")) return true;
    try {
      const url = new URL(trimmed, "https://www.douyin.com");
      const path = url.pathname.toLowerCase();
      return url.protocol === "http:" || url.protocol === "https:" ? /\.(jpe?g|png|webp|gif|avif)$/.test(path) || url.hostname.includes("douyinpic.com") || url.hostname.includes("byteimg.com") || url.hostname.includes("douyinstatic.com") : false;
    } catch {
      return false;
    }
  }

  type ExtractedMetrics = {
    view_count: number | null;
    view_count_text: string | null;
    like_count: number | null;
    like_count_text: string | null;
    comment_count: number | null;
    comment_count_text: string | null;
    share_count: number | null;
    favorite_count: number | null;
  };

  function parseCommentZeroSentinel(text: string): { value: number; raw: string } | null {
    const compact = compactText(text);
    const sentinels = ["抢首评", "快来抢首评", "抢沙发"];
    for (const sentinel of sentinels) {
      if (compact === sentinel || compact.includes(sentinel)) return { value: 0, raw: sentinel };
    }
    return null;
  }

  function metricNearEngagement(text: string, metric: "comment" | "share", markers: string[]): { value: number | null; raw: string | null } {
    const numeric = metricNear(text, markers);
    if (numeric.value !== null) return numeric;
    if (metric === "comment") {
      const zero = parseCommentZeroSentinel(text);
      if (zero) return { value: zero.value, raw: zero.raw };
    }
    return { value: null, raw: null };
  }

  function extractMetrics(text: string): ExtractedMetrics {
    const view = metricNear(text, ["播放", "观看", "浏览", "views", "view", "plays", "play"]);
    const like = metricNear(text, ["赞", "获赞", "喜欢", "likes", "like"]);
    const comment = metricNearEngagement(text, "comment", ["评论", "comments", "comment"]);
    return {
      like_count: like.value,
      like_count_text: like.raw,
      comment_count: comment.value,
      comment_count_text: comment.raw,
      share_count: metricNear(text, ["分享", "shares", "share"]).value,
      favorite_count: metricNear(text, ["收藏", "favorites", "favorite"]).value,
      view_count: view.value,
      view_count_text: view.raw
    };
  }

  function metricNear(text: string, markers: string[]): { value: number | null; raw: string | null } {
    const normalized = text.replace(/,/g, "");
    for (const marker of markers) {
      const after = new RegExp(`${escapeRegex(marker)}\\s*([0-9.]+)\\s*([w万kKmM]?)`, "i").exec(normalized);
      if (after) return { value: parseMetric(after[1], after[2]), raw: [after[1], after[2]].filter(Boolean).join("") || null };
      const before = new RegExp(`([0-9.]+)\\s*([w万kKmM]?)\\s*${escapeRegex(marker)}`, "i").exec(normalized);
      if (before) return { value: parseMetric(before[1], before[2]), raw: [before[1], before[2]].filter(Boolean).join("") || null };
    }
    return { value: null, raw: null };
  }

  function parseMetric(raw: string | undefined, suffix: string | undefined): number | null {
    if (!raw) return null;
    const normalizedRaw = raw.trim();
    if (!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(normalizedRaw)) return null;
    const value = Number(normalizedRaw);
    if (!Number.isFinite(value) || value < 0) return null;
    const lowered = (suffix || "").toLowerCase();
    const multiplier = lowered === "w" || suffix === "万" ? 10_000 : lowered === "k" ? 1_000 : lowered === "m" ? 1_000_000 : 1;
    const normalized = Math.round(value * multiplier);
    if (!Number.isFinite(normalized) || normalized < 0) return null;
    return normalized;
  }

  function validCount(value: number | null | undefined): number | null {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
    return Math.round(value);
  }

  function deriveEngagementRate(values: {
    view_count: number | null;
    like_count: number | null;
    comment_count: number | null;
    share_count: number | null;
  }): number | null {
    const views = values.view_count;
    if (typeof views !== "number" || !Number.isFinite(views) || views <= 0) return null;
    const likes = typeof values.like_count === "number" ? values.like_count : 0;
    const comments = typeof values.comment_count === "number" ? values.comment_count : 0;
    const shares = typeof values.share_count === "number" ? values.share_count : 0;
    const numerator = likes + comments + shares;
    if (!Number.isFinite(numerator) || numerator < 0) return null;
    const rate = numerator / views;
    return Number.isFinite(rate) && rate >= 0 ? rate : null;
  }

  function compactMetricSequence(text: string): Pick<ExtractedMetrics, "view_count" | "view_count_text" | "like_count" | "like_count_text" | "comment_count" | "comment_count_text"> {
    const labeledPattern = /(?:播放|观看|浏览|views?|plays?|赞|获赞|喜欢|likes?|评论|comments?)\s*[0-9.]+\s*[w万kKmM]?|[0-9.]+\s*[w万kKmM]?\s*(?:播放|观看|浏览|views?|plays?|赞|获赞|喜欢|likes?|评论|comments?)/gi;
    const withoutLabeled = text.replace(labeledPattern, " ");
    const matches = Array.from(withoutLabeled.matchAll(/(^|\s)([0-9]+(?:\.[0-9]+)?)\s*([w万kKmM]?)(?=\s|$)/g)).map((match) => ({ raw: `${match[2]}${match[3] ?? ""}`, value: parseMetric(match[2], match[3]) }));
    const [first, second, third] = matches.filter((entry) => typeof entry.value === "number");
    return {
      view_count: first?.value ?? null,
      view_count_text: first?.raw ?? null,
      like_count: second?.value ?? null,
      like_count_text: second?.raw ?? null,
      comment_count: third?.value ?? null,
      comment_count_text: third?.raw ?? null
    };
  }

  function extractDuration(text: string): { duration_text: string | null; duration_seconds: number | null } {
    const match = /(?:^|\s)(\d{1,2}:\d{2}(?::\d{2})?)(?:\s|$)/.exec(text);
    if (!match?.[1]) return { duration_text: null, duration_seconds: null };
    const parts = match[1].split(":").map((part) => Number(part));
    if (parts.some((part) => !Number.isFinite(part))) return { duration_text: match[1], duration_seconds: null };
    if (parts.length === 2) {
      const [minutes, seconds] = parts;
      if ((minutes ?? -1) < 0 || (seconds ?? -1) < 0 || (seconds ?? 99) >= 60) return { duration_text: null, duration_seconds: null };
      return { duration_text: match[1], duration_seconds: (minutes ?? 0) * 60 + (seconds ?? 0) };
    }
    const [hours, minutes, seconds] = parts;
    if ((hours ?? -1) < 0 || (minutes ?? -1) < 0 || (seconds ?? -1) < 0 || (minutes ?? 99) >= 60 || (seconds ?? 99) >= 60) {
      return { duration_text: null, duration_seconds: null };
    }
    return { duration_text: match[1], duration_seconds: (hours ?? 0) * 3600 + (minutes ?? 0) * 60 + (seconds ?? 0) };
  }

  function extractPosted(text: string): { posted_text: string | null; posted_at: string | null } {
    const match = /(\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2})?|\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2})?|\d+\s*(?:分钟前|小时前|天前|周前|月前|年前)|昨天|前天)/.exec(text);
    if (!match?.[1]) return { posted_text: null, posted_at: null };
    return { posted_text: match[1], posted_at: parsePostedText(match[1]) };
  }

  function parsePostedText(value: string): string | null {
    const now = new Date();
    const relative = /^(\d+)\s*(分钟前|小时前|天前|周前|月前|年前)$/.exec(value);
    if (relative) {
      const amount = Number(relative[1]);
      const unit = relative[2];
      const ms = unit === "分钟前" ? amount * 60_000 : unit === "小时前" ? amount * 3_600_000 : unit === "天前" ? amount * 86_400_000 : unit === "周前" ? amount * 7 * 86_400_000 : unit === "月前" ? amount * 30 * 86_400_000 : amount * 365 * 86_400_000;
      return new Date(now.getTime() - ms).toISOString();
    }
    if (value === "昨天" || value === "前天") {
      const days = value === "昨天" ? 1 : 2;
      return new Date(now.getTime() - days * 86_400_000).toISOString();
    }
    const normalized = value.replace(/[.]/g, "-");
    const withYear = /^\d{1,2}-\d{1,2}/.test(normalized) ? `${now.getFullYear()}-${normalized}` : normalized;
    const parsed = new Date(withYear.replace(/-/g, "/"));
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
  }

  function thumbnailCandidateScore(candidate: ThumbnailCandidate): number {
    const source = candidate.sourceType.toLowerCase();
    let score = 0;
    if (source.includes("poster")) score += 40;
    if (source.includes("currentsrc")) score += 35;
    if (source.includes("srcset")) score += 30;
    if (source.includes("data-src")) score += 25;
    if (source.includes("background")) score += 15;
    if (candidate.url.includes("douyinpic.com") || candidate.url.includes("byteimg.com")) score += 20;
    if (candidate.url.startsWith("data:image/")) score -= 20;
    return score;
  }

  function profileUrlFromPage(url: string): string | null {
    try {
      const parsed = new URL(url);
      const userMatch = /\/user\/([^/?#]+)/.exec(parsed.pathname);
      if (userMatch?.[1]) return `https://www.douyin.com/user/${userMatch[1]}`;
      const path = parsed.pathname.replace(/^\//, "");
      if (path.startsWith("@")) return `https://www.douyin.com/${path.split("/")[0]}`;
    } catch {
      return null;
    }
    return null;
  }

  function profileExternalIdFromUrl(url: string | null): string | null {
    if (!url) return null;
    try {
      const parsed = new URL(url);
      const userMatch = /\/user\/([^/?#]+)/.exec(parsed.pathname);
      return userMatch?.[1] ?? null;
    } catch {
      return null;
    }
  }

  function handleFromUrl(url: string): string | null {
    try {
      const parsed = new URL(url);
      const path = parsed.pathname.replace(/^\//, "");
      return path.startsWith("@") ? path.split("/")[0]?.replace(/^@/, "") ?? null : null;
    } catch {
      return null;
    }
  }

  function formatDurationValue(value: number): string {
    const totalSeconds = Math.max(0, Math.round(value));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  }

  function safeShareUrlForLink(link: HTMLAnchorElement, awemeId: string): string | null {
    const id = videoIdFromUrl(link.href);
    return id === awemeId ? link.href : null;
  }

  function videoIdFromUrl(url: string): string | null {
    try {
      const parsed = new URL(url);
      const match = /\/video\/([^/?#]+)/.exec(parsed.pathname);
      return match?.[1] ?? null;
    } catch {
      return null;
    }
  }

  function displayNameFromDocument(): string | null {
    const metaTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"], meta[name="title"]')?.content;
    const h1 = document.querySelector("h1")?.textContent;
    const candidate = compactText(h1 || metaTitle || document.title || "");
    if (!candidate) return null;
    return candidate.replace(/[-_丨|].*Douyin.*/i, "").slice(0, 180).trim() || null;
  }

  function compactText(value: string): string {
    return value.replace(/\s+/g, " ").trim();
  }

  function containsAny(value: string, markers: string[]): boolean {
    return markers.some((marker) => value.includes(marker.toLowerCase()));
  }

  function escapeRegex(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function blockingPageCode(pageType: DouyinPageType): ExtensionDirectExecutionErrorCode | null {
    if (pageType === "login_page") return "login_page";
    if (pageType === "challenge_page") return "challenge_page";
    return null;
  }

  function isCapturablePage(pageType: DouyinPageType): boolean {
    return pageType === "home_feed_page" || pageType === "profile_page" || pageType === "profile_feed_page" || pageType === "video_detail_page";
  }
}
