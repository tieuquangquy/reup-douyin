import { getProfileUrlFromModalUrl } from "../modalStart.js";

export type WholeProfilePageType = "profile" | "modal" | "video" | "unknown";

export type DouyinProfileIdentity = {
  profile_url: string | null;
  canonical_profile_url: string | null;
  sec_uid: string | null;
  user_id: string | null;
  nickname: string | null;
  page_type: WholeProfilePageType;
};

export type ScanProfileResolverSource = "current_profile" | "modal_parent_profile" | "direct_video_author" | "stored_profile" | "none";

export type ScanProfileResolverContext = {
  current_url: string | null;
  page_type: WholeProfilePageType | string | null;
  stored_profile_url?: string | null;
  last_successful_profile_url?: string | null;
  queue_profile_url?: string | null;
  dom_profile_links?: Array<string | null | undefined> | null;
};

export type ScanProfileResolverResult = {
  ok: boolean;
  targetProfileUrl: string | null;
  source: ScanProfileResolverSource;
  needsNavigation: boolean;
  reason: string | null;
};

export type WholeProfileResolveDiagnostics = {
  original_url: string;
  resolved_profile_url: string | null;
  source_modal_aweme_id: string | null;
  modal_id_present_before: boolean;
  modal_id_present_after_expected: boolean;
  page_type: WholeProfilePageType;
};

export type WholeProfileUrlResolution = {
  ok: boolean;
  page_type: WholeProfilePageType;
  profile_url: string | null;
  source_modal_aweme_id: string | null;
  diagnostics: WholeProfileResolveDiagnostics;
};

export type WholeProfileTabContext = WholeProfileUrlResolution & {
  tab_id: number;
  current_url: string;
};

export function resolveWholeProfileContext(tab: { id?: number; url?: string | null }): WholeProfileTabContext | null {
  if (typeof tab.id !== "number" || !tab.url) return null;
  const resolved = resolveWholeProfileFromCurrentUrl(tab.url);
  return {
    ...resolved,
    tab_id: tab.id,
    current_url: tab.url
  };
}

function isDouyinUrl(url: URL): boolean {
  return /douyin\.com$/i.test(url.hostname) || /\.douyin\.com$/i.test(url.hostname);
}

export function isDouyinProfileModalUrl(value: string | null | undefined): boolean {
  if (!value) return false;
  try {
    const url = new URL(value);
    return isDouyinUrl(url) && /^\/user\/[^/?#]+/.test(url.pathname) && url.searchParams.has("modal_id");
  } catch {
    return false;
  }
}

export function normalizeDouyinProfileUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (!isDouyinUrl(url)) return null;
  const profileMatch = url.pathname.match(/^(\/user\/[^/?#]+)/);
  if (!profileMatch) return null;
  return `${url.origin}${profileMatch[1]}`;
}

function stringFromPageData(pageData: unknown, keys: string[]): string | null {
  if (!pageData || typeof pageData !== "object") return null;
  const record = pageData as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  for (const value of Object.values(record)) {
    if (value && typeof value === "object") {
      const nested = stringFromPageData(value, keys);
      if (nested) return nested;
    }
  }
  return null;
}

export function detectCurrentDouyinProfileIdentity(tabUrl: string | null | undefined, pageData?: unknown): DouyinProfileIdentity {
  const resolved = tabUrl ? resolveWholeProfileFromCurrentUrl(tabUrl) : null;
  const profileUrl = normalizeDouyinProfileUrl(stringFromPageData(pageData, ["profile_url", "profileUrl"]) ?? resolved?.profile_url ?? tabUrl ?? null);
  const canonicalProfileUrl = profileUrl ? normalizeDouyinProfileUrl(profileUrl) : null;
  const secUid = stringFromPageData(pageData, ["sec_uid", "secUid"]) ?? canonicalProfileUrl?.match(/\/user\/([^/?#]+)/i)?.[1] ?? null;
  const pageType = resolved?.page_type === "profile" || resolved?.page_type === "modal" || resolved?.page_type === "video" ? resolved.page_type : "unknown";
  return {
    profile_url: profileUrl,
    canonical_profile_url: canonicalProfileUrl,
    sec_uid: secUid,
    user_id: stringFromPageData(pageData, ["user_id", "userId", "uid", "id"]),
    nickname: stringFromPageData(pageData, ["nickname", "display_name", "displayName", "name"]),
    page_type: pageType
  };
}

export function isDifferentProfile(previous: Pick<DouyinProfileIdentity, "canonical_profile_url" | "sec_uid" | "user_id"> | null | undefined, current: Pick<DouyinProfileIdentity, "canonical_profile_url" | "sec_uid" | "user_id"> | null | undefined): boolean {
  if (!previous || !current) return false;
  if (previous.sec_uid && current.sec_uid) return previous.sec_uid !== current.sec_uid;
  if (previous.user_id && current.user_id) return previous.user_id !== current.user_id;
  if (previous.canonical_profile_url && current.canonical_profile_url) return previous.canonical_profile_url.replace(/\/+$/, "") !== current.canonical_profile_url.replace(/\/+$/, "");
  return false;
}

export function resolveTargetProfileUrlForScan(context: ScanProfileResolverContext): ScanProfileResolverResult {
  const currentUrlProfile = normalizeDouyinProfileUrl(context.current_url);
  const pageType = context.page_type === "profile" || context.page_type === "modal" || context.page_type === "video" ? context.page_type : "unknown";
  if (currentUrlProfile && pageType === "profile") {
    return { ok: true, targetProfileUrl: currentUrlProfile, source: "current_profile", needsNavigation: context.current_url?.replace(/[#?].*$/, "") !== currentUrlProfile, reason: null };
  }
  if (currentUrlProfile && isDouyinProfileModalUrl(context.current_url)) {
    return { ok: true, targetProfileUrl: currentUrlProfile, source: "modal_parent_profile", needsNavigation: true, reason: null };
  }
  if (currentUrlProfile && pageType === "modal") {
    return { ok: true, targetProfileUrl: currentUrlProfile, source: "modal_parent_profile", needsNavigation: true, reason: null };
  }
  if (pageType === "video") {
    for (const link of context.dom_profile_links ?? []) {
      const normalized = normalizeDouyinProfileUrl(link);
      if (normalized) return { ok: true, targetProfileUrl: normalized, source: "direct_video_author", needsNavigation: true, reason: null };
    }
  }
  for (const candidate of [context.queue_profile_url, context.last_successful_profile_url, context.stored_profile_url]) {
    const normalized = normalizeDouyinProfileUrl(candidate);
    if (normalized) return { ok: true, targetProfileUrl: normalized, source: "stored_profile", needsNavigation: true, reason: null };
  }
  return { ok: false, targetProfileUrl: null, source: "none", needsNavigation: false, reason: "profile_url_unresolved" };
}

export function resolveWholeProfileFromCurrentUrl(currentUrl: string): WholeProfileUrlResolution {
  const modalResolution = getProfileUrlFromModalUrl(currentUrl);
  if (modalResolution) {
    return createResolution({
      originalUrl: currentUrl,
      pageType: "modal",
      profileUrl: modalResolution.profile_url_without_modal_id,
      sourceModalAwemeId: modalResolution.current_modal_aweme_id,
      modalIdPresentBefore: true
    });
  }
  let url: URL;
  try {
    url = new URL(currentUrl);
  } catch {
    return createResolution({ originalUrl: currentUrl, pageType: "unknown", profileUrl: null, sourceModalAwemeId: null, modalIdPresentBefore: false });
  }
  const modalIdPresentBefore = url.searchParams.has("modal_id");
  if (!isDouyinUrl(url)) {
    return createResolution({ originalUrl: currentUrl, pageType: "unknown", profileUrl: null, sourceModalAwemeId: null, modalIdPresentBefore });
  }
  if (/^\/user\/[^/?#]+/.test(url.pathname)) {
    const sourceModalAwemeId = url.searchParams.get("modal_id");
    return createResolution({
      originalUrl: currentUrl,
      pageType: sourceModalAwemeId ? "modal" : "profile",
      profileUrl: normalizeDouyinProfileUrl(currentUrl),
      sourceModalAwemeId,
      modalIdPresentBefore
    });
  }
  if (/^\/video\//.test(url.pathname)) {
    return createResolution({ originalUrl: currentUrl, pageType: "video", profileUrl: null, sourceModalAwemeId: null, modalIdPresentBefore });
  }
  return createResolution({ originalUrl: currentUrl, pageType: "unknown", profileUrl: null, sourceModalAwemeId: null, modalIdPresentBefore });
}

export function resolveProfileUrlFromCurrentUrl(currentUrl: string): Omit<WholeProfileTabContext, "tab_id" | "current_url" | "ok" | "diagnostics"> {
  const resolved = resolveWholeProfileFromCurrentUrl(currentUrl);
  return { page_type: resolved.page_type, profile_url: resolved.profile_url, source_modal_aweme_id: resolved.source_modal_aweme_id };
}

export function buildDirectModalUrl(profileUrl: string, awemeId: string): string {
  const url = new URL(profileUrl);
  url.searchParams.set("modal_id", awemeId);
  return url.toString();
}

function createResolution(args: { originalUrl: string; pageType: WholeProfilePageType; profileUrl: string | null; sourceModalAwemeId: string | null; modalIdPresentBefore: boolean }): WholeProfileUrlResolution {
  return {
    ok: Boolean(args.profileUrl && (args.pageType === "profile" || args.pageType === "modal")),
    page_type: args.pageType,
    profile_url: args.profileUrl,
    source_modal_aweme_id: args.sourceModalAwemeId,
    diagnostics: {
      original_url: args.originalUrl,
      resolved_profile_url: args.profileUrl,
      source_modal_aweme_id: args.sourceModalAwemeId,
      modal_id_present_before: args.modalIdPresentBefore,
      modal_id_present_after_expected: false,
      page_type: args.pageType
    }
  };
}
