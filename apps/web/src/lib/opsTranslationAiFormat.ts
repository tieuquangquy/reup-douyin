export type ConnectionTestResult = {
  ok: boolean;
  provider: string;
  detail: string;
};

export type ProviderErrorView = {
  title: string;
  message: string;
  httpStatus: number | null;
  raw: string;
};

/** Drop trivial LLM ping replies so UI does not show "Connected … OK". */
export function formatConnectionTestDetail(detail: string): string | null {
  const text = detail.trim();
  if (!text) return null;
  if (/^ok[.!]?\s*$/i.test(text)) return null;
  return text;
}

export function formatConnectionTestSummary(
  result: ConnectionTestResult,
  labels: { ok: string; fail: string }
): string {
  const provider = result.provider.trim() || "unknown";
  const status = result.ok ? labels.ok : labels.fail;
  const detail = formatConnectionTestDetail(result.detail);
  return detail ? `${status} · ${provider} — ${detail}` : `${status} · ${provider}`;
}

export type LlmProbeSuccessView = {
  title: string;
  message: string;
  provider: string;
};

/**
 * Ops Test success copy for Translation / Caption AI — same banner shape as TTS.
 * Probe passed ≠ setup saved; UI hint covers that separately.
 */
export function formatLlmProbeSuccess(
  result: ConnectionTestResult,
  labels: { passed: string; generic: string }
): LlmProbeSuccessView {
  const provider = result.provider.trim() || "unknown";
  const cleaned = formatConnectionTestDetail(result.detail || "");
  return {
    title: labels.passed,
    message: cleaned || labels.generic,
    provider
  };
}

function redactSecrets(text: string): string {
  return text
    .replace(/\bsk-[A-Za-z0-9_\-*]{8,}\b/g, "sk-••••")
    .replace(/\bAIza[A-Za-z0-9_\-*]{8,}\b/g, "AIza••••");
}

function extractJsonMessage(chunk: string): string | null {
  const start = chunk.indexOf("{");
  if (start < 0) return null;
  const body = chunk.slice(start);
  try {
    const payload = JSON.parse(body) as {
      error?: { message?: string };
      message?: string;
    };
    const nested = payload.error?.message || payload.message;
    if (typeof nested === "string" && nested.trim()) {
      return redactSecrets(nested.trim());
    }
  } catch {
    // Truncated JSON from provider dumps — pull message field if present.
    const loose = body.match(/"message"\s*:\s*"((?:\\.|[^"\\])*)"/);
    if (loose?.[1]) {
      return redactSecrets(loose[1].replace(/\\"/g, '"').trim());
    }
  }
  return null;
}

function looksLikeProviderDump(text: string): boolean {
  const value = text.trim();
  if (!value) return true;
  if (value.startsWith("{") || value.startsWith('"')) return true;
  if (/^\w+_http_\d{3}\s*:/i.test(value)) return true;
  if (/^\w+_http_\d{3}\b/i.test(value) && value.includes("{")) return true;
  return false;
}

function looksLikeConnectionFailure(text: string): boolean {
  return /urlopen|winerror\s*10060|timed?\s*out|connection\s*(attempt\s*)?failed|connection\s*refused|name\s*or\s*service\s*not\s*known|getaddrinfo|network\s*is\s*unreachable/i.test(
    text
  );
}

function polishOperatorMessage(message: string): string {
  let text = message
    .replace(/\s*For more information on this error,?\s*head to:\s*https?:\/\/\S+/gi, "")
    .replace(/\s*https?:\/\/[^\s)"]+/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  if (text.length > 160) {
    text = `${text.slice(0, 157).trimEnd()}…`;
  }
  return text;
}

function titleForHttpStatus(status: number | null, labels: { unauthorized: string; forbidden: string; notFound: string; rateLimited: string; failed: string }): string {
  if (status === 401) return labels.unauthorized;
  if (status === 403) return labels.forbidden;
  if (status === 404) return labels.notFound;
  if (status === 429) return labels.rateLimited;
  return labels.failed;
}

/**
 * Turn provider dump like ``list_models_http_401:{ "error": {...}}`` into operator-facing copy.
 */
export function formatProviderError(
  detail: string,
  labels: {
    unauthorized: string;
    forbidden: string;
    notFound: string;
    rateLimited: string;
    failed: string;
    checkKey: string;
    checkEndpoint: string;
  }
): ProviderErrorView {
  const raw = (detail || "").trim();
  if (looksLikeConnectionFailure(raw)) {
    return {
      title: labels.failed,
      message: polishOperatorMessage(labels.checkEndpoint),
      httpStatus: null,
      raw
    };
  }
  const httpMatch =
    raw.match(/(?:list_models_|openai_compatible_|gemini_|ollama_)http_(\d{3})\s*:?\s*(.*)$/i) ||
    raw.match(/\bhttp_(\d{3})\s*:?\s*(.*)$/i);
  // API client errors look like "Failed to test …: 500" with no provider dump.
  const bareStatusMatch = !httpMatch ? raw.match(/:\s*(\d{3})\s*$/) : null;
  const httpStatus = httpMatch
    ? Number(httpMatch[1])
    : bareStatusMatch
      ? Number(bareStatusMatch[1])
      : null;
  const remainder = httpMatch ? httpMatch[2].trim() : bareStatusMatch ? "" : raw;
  const fromJson = extractJsonMessage(remainder) || extractJsonMessage(raw);
  const title = titleForHttpStatus(httpStatus, labels);

  let message = fromJson;
  if (!message) {
    const cleaned = redactSecrets(remainder).trim();
    // Avoid dumping truncated provider JSON / bare client errors into the UI.
    if (!cleaned || looksLikeProviderDump(cleaned) || looksLikeConnectionFailure(cleaned)) {
      if (httpStatus === 401 || httpStatus === 403) message = labels.checkKey;
      else if (httpStatus === 429) message = labels.rateLimited;
      else message = labels.checkEndpoint;
    } else {
      message = cleaned;
    }
  }

  if (looksLikeProviderDump(message) || looksLikeConnectionFailure(message)) {
    if (httpStatus === 401 || httpStatus === 403) message = labels.checkKey;
    else if (httpStatus === 429) message = labels.rateLimited;
    else message = labels.checkEndpoint;
  }

  return { title, message: polishOperatorMessage(message), httpStatus, raw };
}
