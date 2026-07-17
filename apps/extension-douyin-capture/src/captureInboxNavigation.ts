export const CAPTURE_INBOX_WEB_ROUTE = "/ops/extensions/douyin/capture-inbox";
export const DEFAULT_WEB_APP_ORIGIN = "http://localhost:3000";

export function normalizeWebAppOrigin(input: string | null | undefined): string {
  const trimmed = (typeof input === "string" ? input : DEFAULT_WEB_APP_ORIGIN).trim();
  const value = trimmed || DEFAULT_WEB_APP_ORIGIN;
  return value.replace(/\/+$/, "");
}

export function buildCaptureInboxWebUrl(
  webAppOrigin: string | null | undefined,
  profileUrl?: string | null
): string {
  const base = `${normalizeWebAppOrigin(webAppOrigin)}${CAPTURE_INBOX_WEB_ROUTE}`;
  const trimmedProfileUrl = typeof profileUrl === "string" ? profileUrl.trim() : "";
  if (!trimmedProfileUrl) {
    return base;
  }
  const params = new URLSearchParams({ profile_url: trimmedProfileUrl });
  return `${base}?${params.toString()}`;
}

export type OpenCaptureInboxWebTabResult = {
  action: "created" | "focused";
  url: string;
};

export async function openCaptureInboxWebTab(
  webAppOrigin: string | null | undefined,
  profileUrl?: string | null
): Promise<OpenCaptureInboxWebTabResult> {
  const origin = normalizeWebAppOrigin(webAppOrigin);
  const url = buildCaptureInboxWebUrl(origin, profileUrl);
  const existingTabs = await chrome.tabs.query({ url: `${origin}/*` });
  const matchedTab = existingTabs.find((tab) => typeof tab.url === "string" && tab.url.includes(CAPTURE_INBOX_WEB_ROUTE));
  if (matchedTab?.id != null) {
    await chrome.tabs.update(matchedTab.id, { active: true, url });
    if (matchedTab.windowId != null) {
      await chrome.windows.update(matchedTab.windowId, { focused: true });
    }
    return { action: "focused", url };
  }
  await chrome.tabs.create({ url, active: true });
  return { action: "created", url };
}
