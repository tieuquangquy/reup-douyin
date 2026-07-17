/** Safe post-login redirect helpers (open-redirect hardening). */

const PUBLIC_AUTH_PREFIX = "/auth";

/** Soft HTML-session marker for Next middleware (not a secret; API still requires Bearer JWT). */
export const SESSION_PRESENCE_COOKIE = "reup_douyin_session";

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
