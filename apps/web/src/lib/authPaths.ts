/** Safe post-login redirect helpers (open-redirect hardening). */

const PUBLIC_AUTH_PREFIX = "/auth";

/** Soft HTML-session marker for Next middleware (not a secret; API still requires Bearer JWT). */
export const SESSION_PRESENCE_COOKIE = "reup_douyin_session";

/**
 * Soft cookie lifetime for middleware gate — aligned with default refresh TTL (14 days).
 * Browser-session cookies (no Max-Age) die on PC/browser restart while JWTs remain in localStorage,
 * which causes a login-page flash before AuthProvider bounces home.
 */
export const SESSION_SOFT_COOKIE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60;

/**
 * Allow only same-app relative paths. Reject protocol-relative, absolute URLs, and escapes.
 */
export function sanitizeNextPath(raw: string | null | undefined, fallback = "/"): string {
  if (!raw) return fallback;
  let decoded = raw;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return fallback;
  }
  const trimmed = decoded.trim();
  if (!trimmed.startsWith("/")) return fallback;
  if (trimmed.startsWith("//")) return fallback;
  if (trimmed.includes("://")) return fallback;
  if (trimmed.includes("\\")) return fallback;
  if (trimmed.startsWith(PUBLIC_AUTH_PREFIX)) return fallback;
  return trimmed;
}

export function isDevAuthPrefillEnabled(): boolean {
  if (typeof process === "undefined") return false;
  return process.env.NODE_ENV === "development";
}
