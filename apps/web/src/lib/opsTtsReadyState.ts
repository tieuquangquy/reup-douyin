/** TTS Ops readiness chip: session signals + persisted runtime → operator-facing state. */

export type TtsReadyState = "unchecked" | "not_installed" | "installed" | "ready" | "failed";

export type TtsReadySignal = {
  ok: boolean;
  detail: string;
} | null;

export type TtsPersistedRuntime = {
  last_install?: { ok?: boolean; detail?: string; already_satisfied?: boolean } | null;
  last_probe?: { ok?: boolean; detail?: string; provider?: string } | null;
} | null;

export function detailLooksLikeNotInstalled(detail: string): boolean {
  const text = (detail || "").trim();
  if (!text) return false;
  if (/not installed/i.test(text)) return true;
  if (/Neither .+ is installed/i.test(text)) return true;
  if (/No matching distribution/i.test(text)) return true;
  return false;
}

/**
 * Authority order:
 * 1) Live session Test result
 * 2) Live session Install result
 * 3) Persisted last_probe / last_install (survives F5)
 * 4) live_import_ok from GET (cheap import check)
 */
export function resolveTtsReadyState(input: {
  test: TtsReadySignal;
  install: TtsReadySignal;
  runtime?: TtsPersistedRuntime;
  liveImportOk?: boolean | null;
}): TtsReadyState {
  if (input.test?.ok) return "ready";
  if (input.test && !input.test.ok) {
    return detailLooksLikeNotInstalled(input.test.detail) ? "not_installed" : "failed";
  }
  if (input.install?.ok) return "installed";
  if (input.install && !input.install.ok) return "not_installed";

  const probe = input.runtime?.last_probe;
  if (probe?.ok) {
    if (input.liveImportOk === false) return "not_installed";
    return "ready";
  }
  if (probe && probe.ok === false) {
    return detailLooksLikeNotInstalled(probe.detail || "") ? "not_installed" : "failed";
  }

  const install = input.runtime?.last_install;
  if (install?.ok) {
    if (input.liveImportOk === false) return "not_installed";
    return "installed";
  }
  if (install && install.ok === false) return "not_installed";

  if (input.liveImportOk === true) return "installed";
  if (input.liveImportOk === false) return "not_installed";
  return "unchecked";
}

export function ttsReadyChipClass(state: TtsReadyState): string {
  if (state === "ready") return "is-active";
  if (state === "installed") return "is-ok";
  if (state === "not_installed" || state === "failed") return "is-warn";
  return "is-muted";
}

export function ttsReadyLabelKey(state: TtsReadyState): string {
  if (state === "ready") return "opsTtsAi.readyReady";
  if (state === "installed") return "opsTtsAi.readyInstalled";
  if (state === "not_installed") return "opsTtsAi.readyNotInstalled";
  if (state === "failed") return "opsTtsAi.readyFailed";
  return "opsTtsAi.readyUnchecked";
}

export function catalogFromRuntime(runtime: TtsPersistedRuntime): {
  source: string;
  voices: { id: string; label: string }[];
  styles: string[];
  models: string[];
  default_voice_id: string;
  warning: string;
  sample_rate?: number | null;
  backends?: string[];
} | null {
  const catalog = (runtime?.last_probe as { catalog?: unknown } | null | undefined)?.catalog;
  if (!catalog || typeof catalog !== "object") return null;
  const row = catalog as {
    source?: string;
    voices?: { id: string; label: string }[];
    styles?: string[];
    models?: string[];
    default_voice_id?: string;
    warning?: string;
    sample_rate?: number | null;
    backends?: string[];
  };
  if (!Array.isArray(row.voices) || row.voices.length === 0) return null;
  return {
    source: row.source || "none",
    voices: row.voices,
    styles: Array.isArray(row.styles) ? row.styles : [],
    models: Array.isArray(row.models) ? row.models : [],
    default_voice_id: row.default_voice_id || "",
    warning: row.warning || "",
    sample_rate: row.sample_rate ?? null,
    backends: Array.isArray(row.backends) ? row.backends : []
  };
}
