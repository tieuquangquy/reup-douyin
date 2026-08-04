/** Operator Studio vs Ops Console path classification for auth gates. */

export type AuthSurface = "operator" | "ops";

export const SESSION_SURFACE_COOKIE = "reup_douyin_surface";
export const SESSION_SURFACE_STORAGE_KEY = "reup_douyin_auth_surface";

/**
 * Pipeline Dashboard lives under /ops/... but belongs to Operator Studio.
 * Legacy Capture Inbox URL under /ops/extensions/... still redirects to Studio;
 * keep it classified as operator so the redirect is reachable with Studio session.
 */
export function isOpsConsolePath(pathname: string): boolean {
  const path = pathname.split("?")[0] || "/";
  if (path === "/ops/extensions/douyin/capture-inbox" || path.startsWith("/ops/extensions/douyin/capture-inbox/")) {
    return false;
  }
  if (path === "/ops/pipeline" || path.startsWith("/ops/pipeline/")) {
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
