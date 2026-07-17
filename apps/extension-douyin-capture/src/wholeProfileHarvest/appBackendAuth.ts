export type AppBackendAuthStatus = {
  tokenPresent: boolean;
  authRequired: boolean;
  loggedIn: boolean;
};

export const APP_BACKEND_AUTH_TOKEN_KEY = "apiAuthToken";
export const APP_BACKEND_AUTH_REQUIRED_KEY = "apiAuthRequired";

export function parseAppBackendAuthStatus(stored: Record<string, unknown>): AppBackendAuthStatus {
  const token = stored[APP_BACKEND_AUTH_TOKEN_KEY];
  const tokenPresent = typeof token === "string" && token.trim().length > 0;
  const authRequired = stored[APP_BACKEND_AUTH_REQUIRED_KEY] === true;
  return {
    tokenPresent,
    authRequired,
    loggedIn: tokenPresent && !authRequired
  };
}

export async function readAppBackendAuthFromStorage(
  storage: { get: (key: string) => Promise<Record<string, unknown>> }
): Promise<AppBackendAuthStatus> {
  const [tokenStored, requiredStored] = await Promise.all([
    storage.get(APP_BACKEND_AUTH_TOKEN_KEY),
    storage.get(APP_BACKEND_AUTH_REQUIRED_KEY)
  ]);
  return parseAppBackendAuthStatus({ ...tokenStored, ...requiredStored });
}

export function appBackendHealthLabel(auth: AppBackendAuthStatus): "App OK" | "App login" | "App offline" {
  if (!auth.loggedIn) return auth.tokenPresent && auth.authRequired ? "App login" : "App login";
  return "App OK";
}

export type WebTabAuthReconcileResult = {
  token: string | null;
  source: string;
  clearedStaleExtensionToken: boolean;
};

/** When a Web Dashboard tab is open, its localStorage is the logout authority over extension chrome.storage. */
export function reconcileExtensionAuthWithWebTabToken(
  extensionToken: string | null | undefined,
  webTabOpen: boolean,
  webTabToken: string | null | undefined
): WebTabAuthReconcileResult {
  const normalizedExtension = typeof extensionToken === "string" && extensionToken.trim() ? extensionToken.trim() : null;
  const normalizedWeb = typeof webTabToken === "string" && webTabToken.trim() ? webTabToken.trim() : null;
  if (!webTabOpen) {
    return {
      token: normalizedExtension,
      source: normalizedExtension ? "chrome_storage_local" : "missing",
      clearedStaleExtensionToken: false
    };
  }
  if (!normalizedWeb) {
    return {
      token: null,
      source: normalizedExtension ? "web_tab_logged_out_cleared_stale" : "web_tab_logged_out",
      clearedStaleExtensionToken: Boolean(normalizedExtension)
    };
  }
  if (normalizedExtension === normalizedWeb) {
    return { token: normalizedWeb, source: "chrome_storage_local", clearedStaleExtensionToken: false };
  }
  return { token: normalizedWeb, source: "background_web_local_storage_22C13A", clearedStaleExtensionToken: false };
}

export function douyinScanHealthLabel(state: {
  profile_scan?: { status?: string };
  scan_job?: { total_persisted?: number };
}, scanApiPaginationAttempted: boolean): "Douyin OK" | "Douyin" {
  if (scanApiPaginationAttempted) return "Douyin OK";
  if (state.profile_scan?.status === "success" || (state.scan_job?.total_persisted ?? 0) > 0) return "Douyin OK";
  return "Douyin";
}
