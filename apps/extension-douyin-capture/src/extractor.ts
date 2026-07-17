import { CAPTURE_CURRENT_PAGE_SCHEMA_VERSION } from "./requestPayloads.js";
import { parseDouyinEngagementCount, parseDouyinEngagementText } from "./douyinEngagementZeroSentinels.js";
import type {
  CaptureContext,
  ContextMismatchCode,
  DouyinPageType,
  DurationSource,
  EngagementRateSource,
  ExtensionCapturePayload,
  MetricSource,
  NetworkVideoMetadata,
  PageSnapshot,
  PostedSource,
  ProfilePayload,
  RawAwemeEvidence,
  RawDomSnapshot,
  RawEvidenceSummary,
  ThumbnailMissingReason,
  ThumbnailSource,
  VideoPayload
} from "./types.js";

const VERSION = "0.1.0";
const MAX_BODY_SAMPLE_LENGTH = 1600;
const MAX_VIDEOS = 120;

export function detectPageFromDocument(document: Document, locationHref: string): PageSnapshot {
  const title = document.title || null;
  const bodyText = compactText(document.body?.innerText || "").slice(0, MAX_BODY_SAMPLE_LENGTH);
  const videoLinks = collectVideoLinks(document);
  const pageType = classifyPage(locationHref, title, bodyText, videoLinks.length);
  const profileUrl = profileUrlFromPage(locationHref);
  const profile = extractProfile(document, locationHref);
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

export function buildCapturePayload(
  document: Document,
  locationHref: string,
  networkItems: NetworkVideoMetadata[] = [],
  context?: CaptureContext,
  detailHydrateItems: NetworkVideoMetadata[] = [],
  diagnosticsOverrides: Record<string, string | number | boolean | null> = {}
): ExtensionCapturePayload {
  const page = detectPageFromDocument(document, locationHref);
  const profile = extractProfile(document, locationHref);
  const captureId = context?.capture_id ?? crypto.randomUUID();
  const capturedAt = context?.captured_at ?? new Date().toISOString();
  const captureContext = buildCaptureContext(page, profile, { ...context, capture_id: captureId, captured_at: capturedAt });
  const scopedNetworkItems = filterNetworkItemsForContext(networkItems, captureContext);
  const scopedDetailHydrateItems = filterNetworkItemsForContext(detailHydrateItems, captureContext);
  const discoveryDiagnostics = createDiscoveryDiagnostics();
  const videos = extractVideos(document, scopedNetworkItems, scopedDetailHydrateItems, captureContext, discoveryDiagnostics).slice(0, MAX_VIDEOS);
  const payload: ExtensionCapturePayload = {
    schema_version: CAPTURE_CURRENT_PAGE_SCHEMA_VERSION,
    capture_id: captureId,
    captured_at: capturedAt,
    page: { ...page, video_link_count: Math.max(page.video_link_count, videos.length) },
    profile,
    capture_context: captureContext,
    videos,
    diagnostics: {
      extension_version: VERSION,
      extractor: "content_script_network_first_v1",
      network_metadata_available: scopedNetworkItems.length > 0,
      network_metadata_input_count: networkItems.length,
      network_metadata_scoped_count: scopedNetworkItems.length,
      detail_hydrate_metadata_available: scopedDetailHydrateItems.length > 0,
      detail_hydrate_metadata_input_count: detailHydrateItems.length,
      detail_hydrate_metadata_scoped_count: scopedDetailHydrateItems.length,
      network_context_mismatch_count: networkItems.length - scopedNetworkItems.length,
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
      source_link_captured_video_count: videos.filter((video) => video.source_link_status === "captured").length,
      media_asset_ready_video_count: videos.filter((video) => video.media_asset_status === "ready").length,
      network_metadata_video_count: videos.filter((video) => Boolean(video.network_source)).length,
      network_identity_mismatch_count: videos.filter((video) => video.extraction_diagnostics?.rejected_network_identity_mismatch === true).length,
      suspicious_duplicate_payload_mapping_count: suspiciousDuplicatePayloadMappingCount(videos),
      discovery_active_grid_root_strategy: discoveryDiagnostics.active_grid_root_strategy,
      discovery_candidate_link_count: discoveryDiagnostics.candidate_link_count,
      discovery_eligible_tile_count: discoveryDiagnostics.eligible_tile_count,
      discovery_deduped_aweme_count: discoveryDiagnostics.deduped_aweme_count,
      discovery_rejected_link_count: discoveryDiagnostics.rejected_link_count,
      discovery_rejected_reason_counts: JSON.stringify(discoveryDiagnostics.rejected_reason_counts),
      ...diagnosticsOverrides
    }
  };
  logSafeExtractionDebug(payload);
  return payload;
}

export function classifyPage(url: string, title: string | null, bodyText: string | null, videoLinkCount: number): DouyinPageType {
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
  | "outside_active_grid"
  | "stray_video_link"
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

type HydratedItem = {
  discovery: GridDiscoveryRecord;
  network?: NetworkVideoMetadata;
  detail?: NetworkVideoMetadata;
  domFallback?: DomFallbackMetadata;
};

type DouyinAwemeCacheWindow = Window & {
  __DOUYIN_AWEME_CACHE__?: Record<string, CachedAwemeMetadata>;
};

type CachedAwemeMetadata = {
  posted_at?: string | null;
  duration_seconds?: number | null;
  view_count?: number | null;
  like_count?: number | null;
  comment_count?: number | null;
  share_count?: number | null;
};

function readCachedAwemeMetadata(awemeId: string): CachedAwemeMetadata | null {
  if (typeof window === "undefined") return null;
  const cache = (window as DouyinAwemeCacheWindow).__DOUYIN_AWEME_CACHE__;
  if (!cache || typeof cache !== "object") return null;
  const cached = cache[awemeId];
  return cached && typeof cached === "object" ? cached : null;
}

export function extractVideos(document: Document, networkItems: NetworkVideoMetadata[] = [], detailHydrateItems: NetworkVideoMetadata[] = [], context?: CaptureContext, discoveryDiagnostics: DiscoveryDiagnostics = createDiscoveryDiagnostics()): VideoPayload[] {
  const discoveries = discoverGridVideos(document, discoveryDiagnostics);
  const networkById = canonicalNetworkMap(filterNetworkItemsForContext(networkItems, context));
  const detailById = canonicalNetworkMap(filterNetworkItemsForContext(detailHydrateItems, context));
  const hydrateItems = discoveries.map((discovery): HydratedItem => ({
    discovery,
    ...(networkById.has(discovery.aweme_id) ? { network: cloneNetworkMetadata(networkById.get(discovery.aweme_id) as NetworkVideoMetadata) } : {}),
    ...(detailById.has(discovery.aweme_id) ? { detail: cloneNetworkMetadata(detailById.get(discovery.aweme_id) as NetworkVideoMetadata) } : {}),
    domFallback: buildDomFallbackMetadata(discovery)
  }));
  return hydrateItems.map((item) => buildCanonicalVideoPayload(item, context));
}

export function discoverGridVideos(document: Document, diagnostics: DiscoveryDiagnostics = createDiscoveryDiagnostics()): GridDiscoveryRecord[] {
  const activeGridRoot = findActiveWorksGridRoot(document);
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
  return {
    aweme_id: discovery.aweme_id,
    title: titleFromCard(card, discovery.link, text),
    thumbnail: thumbnailFromCard(card, discovery.link),
    duration: extractDuration(text),
    posted: extractPosted(text),
    metrics: extractMetrics(text),
    card,
    text
  };
}

export function collectVideoLinks(root: ParentNode): HTMLAnchorElement[] {
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

function findActiveWorksGridRoot(document: Document): HTMLElement | null {
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

export function extractProfile(document: Document, locationHref: string): ProfilePayload | null {
  const profileUrl = profileUrlFromPage(locationHref);
  const externalId = profileExternalIdFromUrl(profileUrl);
  const handle = handleFromUrl(locationHref);
  const displayName = displayNameFromDocument(document);
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
  const values = [
    card?.textContent,
    link.textContent,
    link.getAttribute("aria-label"),
    link.title,
    card?.getAttribute("aria-label"),
    card?.getAttribute("title")
  ];
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
  const sortedCandidates = candidates
    .map((candidate): ThumbnailCandidate | null => {
      const url = normalizeImageUrl(candidate.url);
      return url ? { ...candidate, url } : null;
    })
    .filter((candidate): candidate is ThumbnailCandidate => candidate !== null && isImageLikeUrl(candidate.url))
    .sort((left, right) => thumbnailCandidateScore(right) - thumbnailCandidateScore(left));
  const urlList = uniqueStrings(sortedCandidates.map((candidate) => candidate.url));
  const thumbnailUrl = urlList[0] ?? null;
  if (!thumbnailUrl) return {};
  const winningSourceType = sortedCandidates.find((candidate) => candidate.url === thumbnailUrl)?.sourceType ?? null;
  return {
    thumbnail_url: thumbnailUrl,
    poster_url: thumbnailUrl,
    cover_url: thumbnailUrl,
    url_list: urlList,
    thumbnail_source_type: winningSourceType,
    thumbnail_source_types: uniqueStrings(sortedCandidates.filter((candidate) => urlList.includes(candidate.url)).map((candidate) => candidate.sourceType))
  };
}

function imageCandidatesFromMedia(root: HTMLElement): ThumbnailCandidate[] {
  const values: ThumbnailCandidate[] = [];
  for (const image of Array.from(root.querySelectorAll<HTMLImageElement>("img"))) {
    pushCandidate(values, image.src, "img.src");
    pushCandidate(values, image.getAttribute("src"), "img.getAttribute(src)");
    pushCandidate(values, image.getAttribute("data-src"), "img.getAttribute(data-src)");
    pushCandidate(values, image.currentSrc, "img.currentSrc");
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
    if (typeof window !== "undefined" && typeof window.getComputedStyle === "function") {
      pushBackgroundCandidates(values, window.getComputedStyle(element).backgroundImage, "computed.backgroundImage");
    }
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

function normalizeImageUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("data:image/")) return trimmed;
  try {
    return new URL(trimmed, "https://www.douyin.com").href;
  } catch {
    return null;
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
  share_count_text: string | null;
  favorite_count: number | null;
};

function extractMetrics(text: string): ExtractedMetrics {
  const view = metricNear(text, ["播放", "观看", "浏览", "views", "view", "plays", "play"]);
  const like = metricNear(text, ["赞", "获赞", "喜欢", "likes", "like"]);
  const comment = metricNearEngagement(text, "comment", ["评论", "comments", "comment"]);
  const share = metricNearEngagement(text, "share", ["分享", "shares", "share"]);
  return {
    like_count: like.value,
    like_count_text: like.raw,
    comment_count: comment.value,
    comment_count_text: comment.raw,
    share_count: share.value,
    share_count_text: share.raw,
    favorite_count: metricNear(text, ["收藏", "favorites", "favorite"]).value,
    view_count: view.value,
    view_count_text: view.raw
  };
}

function metricNearEngagement(
  text: string,
  metric: "comment" | "share",
  markers: string[]
): { value: number | null; raw: string | null; zeroSentinel: boolean } {
  const numeric = metricNear(text, markers);
  if (numeric.value !== null) return { ...numeric, zeroSentinel: false };
  const parsed = parseDouyinEngagementText(metric, text, { shareIconContext: metric === "share" });
  if (parsed.kind === "zero_sentinel") {
    return { value: 0, raw: parsed.rawText, zeroSentinel: true };
  }
  return { value: null, raw: null, zeroSentinel: false };
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

function buildCanonicalVideoPayload(item: HydratedItem, context?: CaptureContext): VideoPayload {
  const { discovery } = item;
  const cachedAweme = readCachedAwemeMetadata(discovery.aweme_id);
  const hasCachedAweme = Boolean(cachedAweme);
  const network = exactHydrateForDiscovery(item.network, discovery, "network_aweme_id_mismatch");
  const detail = exactHydrateForDiscovery(item.detail, discovery, "detail_aweme_id_mismatch");
  const dom = item.domFallback?.aweme_id === discovery.aweme_id ? item.domFallback : undefined;
  const rejectedNetworkAwemeId = item.network && item.network.aweme_id !== discovery.aweme_id ? item.network.aweme_id : null;
  const rejectedDetailAwemeId = item.detail && item.detail.aweme_id !== discovery.aweme_id ? item.detail.aweme_id : null;
  const networkThumbnail = thumbnailFromHydrate(network);
  const detailThumbnail = thumbnailFromHydrate(detail);
  const domThumbnail = normalizeImageUrl(dom?.thumbnail.thumbnail_url ?? null);
  const thumbnailUrl = networkThumbnail ?? detailThumbnail ?? domThumbnail ?? null;
  const thumbnailSource: ThumbnailSource = networkThumbnail ? "network_json" : detailThumbnail ? "detail_hydrate" : domThumbnail ? "dom_fallback" : "missing";
  const thumbnailMissingReason = resolveThumbnailMissingReason({ network, networkThumbnail, detail, detailThumbnail, domThumbnail });
  const urlList = uniqueStrings([
    ...(networkThumbnail ? [networkThumbnail] : []),
    ...(network?.url_list ?? []).map((url) => normalizeImageUrl(url)).filter((url): url is string => Boolean(url)),
    ...(detailThumbnail ? [detailThumbnail] : []),
    ...(detail?.url_list ?? []).map((url) => normalizeImageUrl(url)).filter((url): url is string => Boolean(url)),
    ...(dom?.thumbnail.url_list ?? []).map((url) => normalizeImageUrl(url)).filter((url): url is string => Boolean(url))
  ]);
  const title = network?.title ?? network?.desc ?? detail?.title ?? detail?.desc ?? dom?.title ?? null;
  const cachedDurationSeconds = hasCachedAweme ? validDurationSeconds(cachedAweme?.duration_seconds) : null;
  const networkDurationSeconds = validDurationSeconds(network?.duration_seconds);
  const detailDurationSeconds = validDurationSeconds(detail?.duration_seconds);
  const domDurationSeconds = hasCachedAweme ? null : validDurationSeconds(dom?.duration.duration_seconds ?? null);
  const durationSeconds = hasCachedAweme ? cachedDurationSeconds : networkDurationSeconds ?? detailDurationSeconds ?? domDurationSeconds ?? null;
  const networkDurationText = validDurationText(network?.duration_text);
  const detailDurationText = validDurationText(detail?.duration_text);
  const domDurationText = hasCachedAweme ? null : validDurationText(dom?.duration.duration_text ?? null);
  const durationText = hasCachedAweme ? (typeof durationSeconds === "number" ? formatDuration(durationSeconds) : null) : networkDurationText ?? detailDurationText ?? domDurationText ?? (typeof durationSeconds === "number" ? formatDuration(durationSeconds) : null);
  const durationSource: DurationSource = hasCachedAweme
    ? cachedDurationSeconds !== null ? "network_json" : "fallback_none"
    : networkDurationSeconds !== null || networkDurationText !== null
      ? "network_json"
      : detailDurationSeconds !== null || detailDurationText !== null
        ? "detail_hydrate"
        : domDurationSeconds !== null || domDurationText !== null
          ? "dom_text"
          : "fallback_none";
  const cachedPostedAt = hasCachedAweme ? validNetworkPostedAt(cachedAweme?.posted_at) : null;
  const networkPostedAt = validNetworkPostedAt(network?.posted_at);
  const detailPostedAt = validNetworkPostedAt(detail?.posted_at);
  const domPostedAt = hasCachedAweme ? null : validNetworkPostedAt(dom?.posted.posted_at ?? null);
  const postedAt = hasCachedAweme ? cachedPostedAt : networkPostedAt ?? detailPostedAt ?? domPostedAt ?? null;
  const postedSource: PostedSource = hasCachedAweme ? cachedPostedAt ? "network_json" : "fallback_none" : networkPostedAt ? "network_json" : detailPostedAt ? "detail_hydrate" : domPostedAt ? "dom_text" : "fallback_none";
  const cachedViewCount = hasCachedAweme ? validCount(cachedAweme?.view_count) : null;
  const networkViewCount = validCount(network?.view_count);
  const detailViewCount = validCount(detail?.view_count);
  const domViewCount = hasCachedAweme ? null : validCount(dom?.metrics.view_count);
  const viewCount = hasCachedAweme ? cachedViewCount : networkViewCount ?? detailViewCount ?? domViewCount ?? null;
  const viewCountSource: MetricSource = hasCachedAweme ? cachedViewCount !== null ? "network_json" : "fallback_none" : networkViewCount !== null ? "network_json" : detailViewCount !== null ? "detail_hydrate" : domViewCount !== null ? "dom_text" : "fallback_none";
  const cachedLikeCount = hasCachedAweme ? validCount(cachedAweme?.like_count) : null;
  const networkLikeCount = validCount(network?.like_count);
  const detailLikeCount = validCount(detail?.like_count);
  const domLikeCount = hasCachedAweme ? null : validCount(dom?.metrics.like_count);
  const likeCount = hasCachedAweme ? cachedLikeCount : networkLikeCount ?? detailLikeCount ?? domLikeCount ?? null;
  const likeCountSource: MetricSource = hasCachedAweme ? cachedLikeCount !== null ? "network_json" : "fallback_none" : networkLikeCount !== null ? "network_json" : detailLikeCount !== null ? "detail_hydrate" : domLikeCount !== null ? "dom_text" : "fallback_none";
  const cachedCommentCount = hasCachedAweme ? validCount(cachedAweme?.comment_count) : null;
  const networkCommentCount = validCount(network?.comment_count);
  const detailCommentCount = validCount(detail?.comment_count);
  const domCommentCount = hasCachedAweme ? null : validCount(dom?.metrics.comment_count);
  const commentCount = hasCachedAweme ? cachedCommentCount : networkCommentCount ?? detailCommentCount ?? domCommentCount ?? null;
  const commentCountSource: MetricSource = hasCachedAweme
    ? cachedCommentCount !== null ? "network_json" : "fallback_none"
    : networkCommentCount !== null
      ? "network_json"
      : detailCommentCount !== null
        ? "detail_hydrate"
        : domCommentCount !== null
          ? domCommentCount === 0 && parseDouyinEngagementText("comment", dom?.metrics.comment_count_text).kind === "zero_sentinel"
            ? "dom_zero_sentinel"
            : "dom_text"
          : "fallback_none";
  const cachedShareCount = hasCachedAweme ? validCount(cachedAweme?.share_count) : null;
  const networkShareCount = validCount(network?.share_count);
  const detailShareCount = validCount(detail?.share_count);
  const domShareCount = hasCachedAweme ? null : validCount(dom?.metrics.share_count);
  const shareCount = hasCachedAweme ? cachedShareCount : networkShareCount ?? detailShareCount ?? domShareCount ?? null;
  const shareCountSource: MetricSource = hasCachedAweme
    ? cachedShareCount !== null ? "network_json" : "fallback_none"
    : networkShareCount !== null
      ? "network_json"
      : detailShareCount !== null
        ? "detail_hydrate"
        : domShareCount !== null
          ? domShareCount === 0 && parseDouyinEngagementText("share", dom?.metrics.share_count_text, { shareIconContext: true }).kind === "zero_sentinel"
            ? "dom_zero_sentinel"
            : "dom_text"
          : "fallback_none";
  const engagementRate = deriveEngagementRate({
    view_count: viewCount,
    like_count: likeCount,
    comment_count: commentCount,
    share_count: shareCount
  });
  const engagementRateSource: EngagementRateSource = engagementRate !== null ? "derived_from_canonical_counts" : "fallback_none";
  const shareUrl = network?.share_url ?? detail?.share_url ?? discovery.share_url ?? discovery.source_url;
  const rawNetworkAweme = network?.raw_network_aweme ?? null;
  const rawDetailAweme = detail?.raw_detail_aweme ?? detail?.raw_network_aweme ?? null;
  const rawDomSnapshot = buildRawDomSnapshot(discovery, dom, urlList);
  const rawEvidenceSummary = buildRawEvidenceSummary(rawNetworkAweme, rawDetailAweme, rawDomSnapshot);
  return {
    id: discovery.aweme_id,
    aweme_id: discovery.aweme_id,
    video_id: discovery.aweme_id,
    source_video_url: discovery.source_url,
    share_url: shareUrl,
    url: discovery.source_url,
    title,
    desc: network?.desc ?? detail?.desc ?? title,
    thumbnail_url: thumbnailUrl,
    poster_url: thumbnailUrl,
    cover_url: thumbnailUrl,
    origin_cover: network?.origin_cover ?? detail?.origin_cover ?? null,
    dynamic_cover: network?.dynamic_cover ?? detail?.dynamic_cover ?? null,
    url_list: [...urlList],
    poster_aspect_ratio: network?.poster_aspect_ratio ?? detail?.poster_aspect_ratio ?? (thumbnailUrl ? 9 / 16 : null),
    thumbnail_source_type: thumbnailSource ?? dom?.thumbnail.thumbnail_source_type ?? null,
    capture_context: context ?? null,
    context_mismatch_codes: contextMismatchCodes(network, detail),
    thumbnail_source: thumbnailSource,
    thumbnail_missing_reason: thumbnailMissingReason,
    posted_source: postedSource,
    thumbnail_source_types: uniqueStrings([...(networkThumbnail ? ["network_json"] : []), ...(detailThumbnail ? ["detail_hydrate"] : []), ...(dom?.thumbnail.thumbnail_source_types ?? [])]),
    duration_text: durationText,
    duration_seconds: durationSeconds,
    duration_source: durationSource,
    posted_text: hasCachedAweme ? postedAt : networkPostedAt ?? detailPostedAt ?? dom?.posted.posted_text ?? null,
    posted_at: postedAt,
    view_count: viewCount,
    view_count_source: viewCountSource,
    view_count_text: hasCachedAweme ? null : network?.view_count_text ?? detail?.view_count_text ?? dom?.metrics.view_count_text ?? null,
    like_count: likeCount,
    like_count_source: likeCountSource,
    like_count_text: hasCachedAweme ? null : network?.like_count_text ?? detail?.like_count_text ?? dom?.metrics.like_count_text ?? null,
    comment_count: commentCount,
    comment_count_source: commentCountSource,
    comment_count_text: hasCachedAweme ? null : network?.comment_count_text ?? detail?.comment_count_text ?? dom?.metrics.comment_count_text ?? null,
    share_count: shareCount,
    share_count_source: shareCountSource,
    share_count_text: hasCachedAweme ? null : network?.share_count_text ?? detail?.share_count_text ?? dom?.metrics.share_count_text ?? null,
    engagement_rate: engagementRate,
    engagement_rate_source: engagementRateSource,
    has_speech: null,
    text_density: null,
    has_heavy_watermark: null,
    processing_complexity: null,
    copyright_risk: null,
    preview_status: thumbnailUrl ? "ready" : "missing",
    source_link_status: discovery.source_url || shareUrl ? "captured" : "missing",
    media_asset_status: "not_generated",
    media_status: discovery.source_url || shareUrl ? "source_link_captured" : "missing",
    network_source: hasCachedAweme ? "__DOUYIN_AWEME_CACHE__" : network?.raw_source ?? detail?.raw_source ?? null,
    raw: {
      visible_text: (dom?.text ?? "").slice(0, 600),
      network_aweme_id: network?.aweme_id ?? null,
      detail_aweme_id: detail?.aweme_id ?? null,
      rejected_network_aweme_id: rejectedNetworkAwemeId,
      rejected_detail_aweme_id: rejectedDetailAwemeId,
      network_source: network?.raw_source ?? null,
      detail_source: detail?.raw_source ?? null,
      thumbnail_missing_reason: thumbnailMissingReason
    },
    raw_network_aweme: rawNetworkAweme,
    raw_detail_aweme: rawDetailAweme,
    raw_dom_snapshot: rawDomSnapshot,
    raw_evidence_summary: rawEvidenceSummary,
    extraction_diagnostics: {
      has_card_root: Boolean(dom?.card),
      card_text_length: dom?.text.length ?? 0,
      visible_order: discovery.visible_order,
      thumbnail_candidate_count: urlList.length,
      has_network_metadata: Boolean(network),
      has_detail_hydrate_metadata: Boolean(detail),
      has_dom_fallback_metadata: Boolean(dom),
      rejected_network_identity_mismatch: Boolean(rejectedNetworkAwemeId),
      rejected_detail_identity_mismatch: Boolean(rejectedDetailAwemeId),
      has_duration_text: Boolean(durationText),
      has_posted_text: Boolean(dom?.posted.posted_text),
      has_view_count: typeof viewCount === "number" || Boolean(network?.view_count_text ?? detail?.view_count_text ?? dom?.metrics.view_count_text),
      has_like_count: typeof likeCount === "number" || Boolean(network?.like_count_text ?? detail?.like_count_text ?? dom?.metrics.like_count_text),
      has_comment_count: typeof commentCount === "number" || Boolean(network?.comment_count_text ?? detail?.comment_count_text ?? dom?.metrics.comment_count_text),
      thumbnail_missing_reason: thumbnailMissingReason,
      grid_metadata_primary: false
    },
    statistics: {
      like_count: likeCount,
      comment_count: commentCount,
      share_count: shareCount,
      favorite_count: validCount(dom?.metrics.favorite_count),
      view_count: viewCount,
      engagement_rate: engagementRate
    }
  };
}

function buildRawDomSnapshot(discovery: GridDiscoveryRecord, dom: DomFallbackMetadata | undefined, imageCandidates: string[]): RawDomSnapshot | null {
  if (!dom) return null;
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
  return uniqueStrings(text.split(/(?<=[。.!?！？])|\n/g).map((entry) => compactText(entry).slice(0, 240)).filter(Boolean)).slice(0, 8);
}

function buildRawEvidenceSummary(rawNetworkAweme: RawAwemeEvidence | null, rawDetailAweme: RawAwemeEvidence | null, rawDomSnapshot: RawDomSnapshot | null): RawEvidenceSummary {
  const evidenceSources = [rawNetworkAweme ? "network_json" : null, rawDetailAweme ? "detail_hydrate" : null, rawDomSnapshot ? "dom_snapshot" : null].filter((value): value is string => Boolean(value));
  return {
    has_network_aweme: Boolean(rawNetworkAweme),
    has_detail_aweme: Boolean(rawDetailAweme),
    has_dom_snapshot: Boolean(rawDomSnapshot),
    network_keys: rawNetworkAweme ? Object.keys(rawNetworkAweme).slice(0, 40) : [],
    detail_keys: rawDetailAweme ? Object.keys(rawDetailAweme).slice(0, 40) : [],
    evidence_sources: evidenceSources,
    evidence_collection_version: rawDetailAweme ? "phase5c_detail_hydrate" : "phase2"
  };
}

function isSecretLikeDomKey(key: string): boolean {
  return /cookie|authorization|auth|token|secret|credential|password|passwd|session|csrf/i.test(key);
}

function exactHydrateForDiscovery(metadata: NetworkVideoMetadata | undefined, discovery: GridDiscoveryRecord, warningCode: string): NetworkVideoMetadata | undefined {
  if (!metadata) return undefined;
  if (metadata.aweme_id !== discovery.aweme_id) {
    warnIdentityMappingIssue(warningCode, { discovery_aweme_id: discovery.aweme_id, hydrate_aweme_id: metadata.aweme_id });
    return undefined;
  }
  return cloneNetworkMetadata(metadata);
}

function thumbnailFromHydrate(metadata: NetworkVideoMetadata | undefined): string | null {
  const candidates = [
    metadata?.thumbnail_url,
    metadata?.origin_cover,
    metadata?.cover_url,
    metadata?.dynamic_cover,
    ...(metadata?.url_list ?? [])
  ];
  return candidates.map((candidate) => normalizeImageUrl(candidate)).find((candidate): candidate is string => Boolean(candidate)) ?? null;
}

function resolveThumbnailMissingReason({
  network,
  networkThumbnail,
  detail,
  detailThumbnail,
  domThumbnail
}: {
  network: NetworkVideoMetadata | undefined;
  networkThumbnail: string | null;
  detail: NetworkVideoMetadata | undefined;
  detailThumbnail: string | null;
  domThumbnail: string | null;
}): ThumbnailMissingReason | null {
  if (networkThumbnail || detailThumbnail || domThumbnail) return null;
  if (!network) return "network_cover_missing";
  if (!detail) return "detail_hydrate_not_run";
  if (!thumbnailCandidateCount(detail)) return "detail_hydrate_no_cover";
  if (!thumbnailCandidateCount(network)) return "network_cover_missing";
  return "dom_cover_missing";
}

function thumbnailCandidateCount(metadata: NetworkVideoMetadata): number {
  return [metadata.thumbnail_url, metadata.origin_cover, metadata.cover_url, metadata.dynamic_cover, ...(metadata.url_list ?? [])]
    .map((candidate) => normalizeImageUrl(candidate))
    .filter(Boolean).length;
}

function safeShareUrlForLink(link: HTMLAnchorElement, awemeId: string): string | null {
  const id = videoIdFromUrl(link.href);
  return id === awemeId ? link.href : null;
}

export function buildCaptureContext(page: PageSnapshot, profile: ProfilePayload | null, seed: CaptureContext = {}): CaptureContext {
  const pageUrl = seed.page_url ?? page.url ?? null;
  const profileUrl = seed.profile_url ?? page.profile_url ?? null;
  const profileExternalId = seed.profile_external_id ?? page.profile_external_id ?? profile?.sec_uid ?? profile?.id ?? profileExternalIdFromUrl(profileUrl) ?? null;
  const pageUrlNormalized = seed.page_url_normalized ?? normalizeContextUrl(pageUrl);
  const cacheScopeKey = seed.cache_scope_key ?? ([pageUrlNormalized, profileUrl, profileExternalId].filter(Boolean).join("|") || null);
  return {
    capture_id: seed.capture_id ?? null,
    tab_id: seed.tab_id ?? null,
    page_url: pageUrl,
    page_url_normalized: pageUrlNormalized,
    profile_url: profileUrl,
    profile_external_id: profileExternalId,
    captured_at: seed.captured_at ?? null,
    cache_scope_key: cacheScopeKey
  };
}

export function filterNetworkItemsForContext(items: NetworkVideoMetadata[], context?: CaptureContext | null): NetworkVideoMetadata[] {
  if (!context) return items.map(cloneNetworkMetadata);
  return items.filter((item) => contextMismatchCodes(item).length === 0 && contextMatches(item.context, context)).map(cloneNetworkMetadata);
}

function contextMismatchCodes(...items: Array<NetworkVideoMetadata | undefined>): ContextMismatchCode[] {
  const codes = new Set<ContextMismatchCode>();
  for (const item of items) {
    for (const code of item?.context_mismatch_codes ?? []) codes.add(code);
  }
  return Array.from(codes);
}

function contextMatches(itemContext: CaptureContext | null | undefined, activeContext: CaptureContext): boolean {
  if (!itemContext) return true;
  if (itemContext.profile_external_id && activeContext.profile_external_id && itemContext.profile_external_id !== activeContext.profile_external_id) return false;
  if (itemContext.profile_url && activeContext.profile_url && normalizeContextUrl(itemContext.profile_url) !== normalizeContextUrl(activeContext.profile_url)) return false;
  if (itemContext.page_url_normalized && activeContext.page_url_normalized && itemContext.page_url_normalized !== activeContext.page_url_normalized) return false;
  if (itemContext.page_url && activeContext.page_url && normalizeContextUrl(itemContext.page_url) !== normalizeContextUrl(activeContext.page_url)) return false;
  if (itemContext.tab_id && activeContext.tab_id && itemContext.tab_id !== activeContext.tab_id) return false;
  return true;
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

function canonicalNetworkMap(items: NetworkVideoMetadata[]): Map<string, NetworkVideoMetadata> {
  const byId = new Map<string, NetworkVideoMetadata>();
  for (const item of items) {
    const awemeId = item.aweme_id?.trim();
    if (!awemeId) continue;
    const previous = byId.get(awemeId);
    byId.set(awemeId, mergeNetworkMetadata(previous, item));
  }
  return byId;
}

function mergeNetworkMetadata(previous: NetworkVideoMetadata | undefined, next: NetworkVideoMetadata): NetworkVideoMetadata {
  if (!previous) return cloneNetworkMetadata(next);
  return {
    ...previous,
    ...next,
    aweme_id: previous.aweme_id,
    url_list: uniqueStrings([...(next.url_list ?? []), ...(previous.url_list ?? [])]),
    raw_network_aweme: next.raw_network_aweme ?? previous.raw_network_aweme ?? null,
    raw_detail_aweme: next.raw_detail_aweme ?? previous.raw_detail_aweme ?? null
  };
}

function cloneNetworkMetadata(item: NetworkVideoMetadata): NetworkVideoMetadata {
  return {
    ...item,
    url_list: [...(item.url_list ?? [])],
    raw_network_aweme: item.raw_network_aweme ? { ...item.raw_network_aweme } : null,
    raw_detail_aweme: item.raw_detail_aweme ? { ...item.raw_detail_aweme } : null
  };
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

function validDurationSeconds(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const normalized = Math.round(value);
  if (normalized < 0 || normalized > 86_400) return null;
  return normalized;
}

function validDurationText(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  const match = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(trimmed);
  if (!match) return null;
  const left = Number(match[1]);
  const middle = Number(match[2]);
  const right = match[3] === undefined ? null : Number(match[3]);
  if (!Number.isFinite(left) || !Number.isFinite(middle) || (right !== null && !Number.isFinite(right))) return null;
  if (right === null) {
    return left >= 0 && middle >= 0 && middle < 60 ? trimmed : null;
  }
  return left >= 0 && middle >= 0 && right >= 0 && middle < 60 && right < 60 ? trimmed : null;
}

function validNetworkPostedAt(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  if (parsed.getUTCHours() === 0 && parsed.getUTCMinutes() === 0 && parsed.getUTCSeconds() === 0 && parsed.getUTCMilliseconds() === 0) return null;
  return parsed.toISOString();
}

function formatDuration(value: number): string {
  const totalSeconds = Math.max(0, Math.round(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function thumbnailCandidateScore(candidate: ThumbnailCandidate): number {
  const source = candidate.sourceType.toLowerCase();
  let score = 0;
  if (source === "img.src") score += 70;
  if (source.includes("getattribute(src)")) score += 65;
  if (source.includes("data-src")) score += 60;
  if (source.includes("dataset")) score += 55;
  if (source.includes("srcset")) score += 50;
  if (source.includes("inline.background")) score += 45;
  if (source.includes("computed.background")) score += 40;
  if (source.includes("poster")) score += 35;
  if (source.includes("currentsrc")) score += 30;
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

function logSafeExtractionDebug(payload: ExtensionCapturePayload): void {
  if (typeof console === "undefined" || !payload.videos.length) return;
  const first = payload.videos[0];
  const suspiciousDuplicateCount = Number(payload.diagnostics.suspicious_duplicate_payload_mapping_count ?? 0);
  if (suspiciousDuplicateCount > 0) {
    warnIdentityMappingIssue("suspicious_duplicate_payload_mapping", {
      count: suspiciousDuplicateCount,
      visible_video_count: payload.videos.length
    });
  }
  console.debug("[reup-douyin] visible grid capture", {
    page_type: payload.page.page_type,
    extractor: payload.diagnostics.extractor ?? null,
    visible_video_count: payload.videos.length,
    network_metadata_input_count: payload.diagnostics.network_metadata_input_count ?? null,
    thumbnail_ready_count: payload.videos.filter((video) => Boolean(video.thumbnail_url)).length,
    network_metadata_count: payload.videos.filter((video) => Boolean(video.network_source)).length,
    network_identity_mismatch_count: payload.diagnostics.network_identity_mismatch_count ?? 0,
    suspicious_duplicate_payload_mapping_count: payload.diagnostics.suspicious_duplicate_payload_mapping_count ?? 0,
    preview_status_counts: statusCounts(payload.videos.map((video) => video.preview_status ?? "missing")),
    source_link_status_counts: statusCounts(payload.videos.map((video) => video.source_link_status ?? "missing")),
    media_asset_status_counts: statusCounts(payload.videos.map((video) => video.media_asset_status ?? "not_generated")),
    sample: {
      aweme_id: first?.aweme_id ?? null,
      has_thumbnail: Boolean(first?.thumbnail_url),
      poster_aspect_ratio: first?.poster_aspect_ratio ?? null,
      thumbnail_source_type: first?.thumbnail_source_type ?? null,
      preview_status: first?.preview_status ?? null,
      source_link_status: first?.source_link_status ?? null,
      media_asset_status: first?.media_asset_status ?? null,
      has_duration: Boolean(first?.duration_text || first?.duration_seconds),
      has_posted: Boolean(first?.posted_text || first?.posted_at),
      has_metrics: Boolean(first?.view_count ?? first?.view_count_text ?? first?.like_count ?? first?.like_count_text ?? first?.comment_count ?? first?.comment_count_text),
      network_source: first?.network_source ?? null
    }
  });
}

function warnIdentityMappingIssue(code: string, details: Record<string, unknown>): void {
  if (typeof console === "undefined") return;
  console.warn("[reup-douyin] identity mapping safeguard", { code, ...details });
}

function suspiciousDuplicatePayloadMappingCount(videos: VideoPayload[]): number {
  const bySignature = new Map<string, Set<string>>();
  for (const video of videos) {
    if (!video.aweme_id || !video.network_source) continue;
    const signature = [video.thumbnail_url ?? "", video.title ?? video.desc ?? "", video.posted_at ?? "", video.view_count ?? "", video.like_count ?? "", video.comment_count ?? ""].join("|");
    if (!signature.replace(/[|]/g, "")) continue;
    const ids = bySignature.get(signature) ?? new Set<string>();
    ids.add(video.aweme_id);
    bySignature.set(signature, ids);
  }
  return Array.from(bySignature.values()).filter((ids) => ids.size > 1).length;
}

function statusCounts(values: Array<string | null | undefined>): Record<string, number> {
  return values.reduce<Record<string, number>>((counts, value) => {
    const key = value || "unknown";
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
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

function videoIdFromUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    const match = /\/video\/([^/?#]+)/.exec(parsed.pathname);
    return match?.[1] ?? null;
  } catch {
    return null;
  }
}

function displayNameFromDocument(document: Document): string | null {
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
