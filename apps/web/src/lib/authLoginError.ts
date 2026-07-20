/**
 * Maps raw login/register API error strings into a short title + helpful body
 * for the auth error banner (avoids dumping bare "Login failed: 500").
 */

export type AuthLoginErrorView = {
  title: string;
  message: string;
};

export type AuthLoginErrorCopy = {
  title: string;
  serverUnavailable: string;
  unauthorized: string;
  forbidden: string;
  network: string;
  generic: string;
};

const STATUS_RE = /:\s*(\d{3})\b/;
const DETAIL_AFTER_STATUS_RE = /:\s*\d{3}\s*[:\-]?\s*(.+)$/s;

function extractStatus(raw: string): number | null {
  const match = STATUS_RE.exec(raw);
  if (!match) return null;
  const code = Number(match[1]);
  return Number.isFinite(code) ? code : null;
}

function extractDetail(raw: string): string | null {
  const match = DETAIL_AFTER_STATUS_RE.exec(raw.trim());
  if (!match) return null;
  const detail = match[1].trim();
  if (!detail || /^\d{3}$/.test(detail)) return null;
  return detail;
}

function looksLikeNetwork(raw: string): boolean {
  return /failed to fetch|networkerror|load failed|econnrefused|network request failed/i.test(raw);
}

export function resolveAuthLoginError(raw: string, copy: AuthLoginErrorCopy): AuthLoginErrorView {
  const text = (raw || "").trim();
  if (!text) {
    return { title: copy.title, message: copy.generic };
  }

  if (looksLikeNetwork(text)) {
    return { title: copy.title, message: copy.network };
  }

  const status = extractStatus(text);
  const detail = extractDetail(text);

  if (status === 401 || status === 400) {
    return {
      title: copy.title,
      message: detail && detail.length < 160 ? detail : copy.unauthorized
    };
  }
  if (status === 403) {
    return {
      title: copy.title,
      message: detail && detail.length < 160 ? detail : copy.forbidden
    };
  }
  if (status !== null && status >= 500) {
    return { title: copy.title, message: copy.serverUnavailable };
  }
  if (status !== null) {
    return {
      title: copy.title,
      message: detail && detail.length < 160 ? detail : copy.generic
    };
  }

  // Already a human message (no status suffix) — keep it under the title.
  if (!/^login failed$/i.test(text) && !/^ops console login failed$/i.test(text)) {
    return { title: copy.title, message: text };
  }

  return { title: copy.title, message: copy.generic };
}
