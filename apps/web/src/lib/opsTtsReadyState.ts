/** TTS Ops readiness chip: session signals + persisted runtime → operator-facing state. */

import type { TtsAiCatalog } from "./api";

export type TtsReadyState = "unchecked" | "not_installed" | "installed" | "ready" | "failed";

export type TtsReadySignal = {
  ok: boolean;
  detail: string;
} | null;

export type TtsPersistedRuntime = {
  last_install?: { ok?: boolean; detail?: string; already_satisfied?: boolean } | null;
  last_probe?: { ok?: boolean; detail?: string; provider?: string; catalog?: unknown } | null;
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

export function catalogFromRuntime(
  runtime: TtsPersistedRuntime,
  expectedProvider = ""
): TtsAiCatalog | null {
  const probe = runtime?.last_probe as { provider?: string; catalog?: unknown } | null | undefined;
  const expected = expectedProvider.trim().toLowerCase();
  const observed = (probe?.provider || "").trim().toLowerCase();
  if (expected && observed !== expected) return null;
  const catalog = probe?.catalog;
  if (!catalog || typeof catalog !== "object") return null;
  const row = catalog as Partial<TtsAiCatalog>;
  const voices = Array.isArray(row.voices) ? row.voices : [];
  const models = Array.isArray(row.models) ? row.models : [];
  const modelOptions = Array.isArray(row.model_options) ? row.model_options : [];
  const languages = Array.isArray(row.languages) ? row.languages : [];
  if (!voices.length && !models.length && !modelOptions.length && !languages.length && !row.discovery) {
    return null;
  }
  return {
    source: row.source || "none",
    voices,
    styles: Array.isArray(row.styles) ? row.styles : [],
    models,
    model_options: modelOptions,
    languages,
    default_voice_id: row.default_voice_id || "",
    default_model_id: row.default_model_id || "",
    default_language_code: row.default_language_code || "",
    discovery: row.discovery || null,
    warning: row.warning || "",
    sample_rate: row.sample_rate ?? null,
    backends: Array.isArray(row.backends) ? row.backends : [],
    capabilities: row.capabilities || null
  };
}
