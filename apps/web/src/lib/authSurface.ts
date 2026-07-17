/** Operator Studio vs Ops Console path classification for auth gates. */

export type AuthSurface = "operator" | "ops";

export const SESSION_SURFACE_COOKIE = "reup_douyin_surface";
export const SESSION_SURFACE_STORAGE_KEY = "reup_douyin_auth_surface";

/**
 * Capture Inbox lives under /ops/extensions/... but belongs to Operator Studio.
 * Legacy Extension Manager URL (/ops/extensions/douyin) redirects to Studio Setup;
 * path classification still treats the bare manager URL as Ops until the redirect runs.
 */
export function isOpsConsolePath(pathname: string): boolean {
  const path = pathname.split("?")[0] || "/";
  if (path === "/ops/extensions/douyin/capture-inbox" || path.startsWith("/ops/extensions/douyin/capture-inbox/")) {
    return false;
  }
  return path === "/ops" || path.startsWith("/ops/");
}

export function surfaceForPath(pathname: string): AuthSurface {
  return isOpsConsolePath(pathname) ? "ops" : "operator";
}

export function loginPathForSurface(surface: AuthSurface): string {
  return surface === "ops" ? "/auth/ops/login" : "/auth/login";
}

export function homePathForSurface(surface: AuthSurface): string {
  return surface === "ops" ? "/ops" : "/";
}

/**
 * When already authenticated, only bounce away from the *same* surface's login.
 * Cross-surface login must stay reachable so owner/admin can switch Studio ↔ Ops tokens.
 */
export function authenticatedLoginBounceTarget(pathname: string, sessionSurface: AuthSurface): string | null {
  const path = pathname.split("?")[0] || "/";
  if (path === "/auth/login" || path === "/auth/register") {
    return sessionSurface === "operator" ? homePathForSurface("operator") : null;
  }
  if (path === "/auth/ops/login") {
    return sessionSurface === "ops" ? homePathForSurface("ops") : null;
  }
  return null;
}
