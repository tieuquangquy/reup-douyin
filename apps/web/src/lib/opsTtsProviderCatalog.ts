/** TTS Ops provider taxonomy + local install recipes (UI authority). */

export type TtsProviderKind = "local" | "cloud" | "http" | "system";

export const TTS_KIND_ORDER: TtsProviderKind[] = ["local", "cloud", "http", "system"];

export const TTS_PROVIDERS_BY_KIND: Record<TtsProviderKind, readonly string[]> = {
  local: ["edge", "vieneu", "cli", "custom"],
  cloud: ["google", "azure", "elevenlabs", "openai"],
  http: ["openai_compatible", "http_custom"],
  system: ["auto", "placeholder"]
};

export const TTS_FALLBACK_PROVIDERS = [
  "none",
  "edge",
  "vieneu",
  "google",
  "azure",
  "elevenlabs",
  "openai",
  "openai_compatible",
  "http_custom",
  "cli",
  "placeholder"
] as const;

export type LocalInstallRecipe = {
  packageName: string;
  installCommand: string;
  extraRequirement: string;
  defaultVoice: string;
  defaultModel: string;
  hintKey: string;
};

const LOCAL_RECIPES: Record<string, LocalInstallRecipe> = {
  edge: {
    packageName: "edge-tts",
    installCommand: "pip install edge-tts",
    extraRequirement: "ffmpeg on PATH",
    defaultVoice: "vi-VN-HoaiMyNeural",
    defaultModel: "",
    hintKey: "opsTtsAi.hintEdge"
  },
  vieneu: {
    packageName: "vieneu",
    installCommand: "pip install vieneu",
    extraRequirement: "First run downloads models from Hugging Face",
    defaultVoice: "Phạm Tuyên",
    defaultModel: "v3turbo",
    hintKey: "opsTtsAi.hintVieneu"
  },
  cli: {
    packageName: "",
    installCommand: "",
    extraRequirement: "Binary must be on PATH or absolute path in CLI binary",
    defaultVoice: "vi-VN-HoaiMyNeural",
    defaultModel: "",
    hintKey: "opsTtsAi.hintCli"
  }
};

export function resolveTtsProviderKind(provider: string): TtsProviderKind {
  const mode = provider.trim().toLowerCase();
  for (const kind of TTS_KIND_ORDER) {
    if (TTS_PROVIDERS_BY_KIND[kind].includes(mode)) return kind;
  }
  // Custom local slug (not in preset list)
  if (/^[a-z][a-z0-9_\-]{0,62}$/.test(mode) && !["auto", "none", "off"].includes(mode)) {
    return "local";
  }
  return "system";
}

export function isPresetLocalProvider(provider: string): boolean {
  const mode = provider.trim().toLowerCase();
  return mode === "edge" || mode === "vieneu" || mode === "cli";
}

export function isCustomLocalProvider(provider: string): boolean {
  const mode = provider.trim().toLowerCase();
  return resolveTtsProviderKind(mode) === "local" && !isPresetLocalProvider(mode) && mode !== "custom";
}

export function getLocalInstallRecipe(provider: string): LocalInstallRecipe | null {
  const mode = provider.trim().toLowerCase();
  return LOCAL_RECIPES[mode] ?? null;
}

export function defaultProviderForKind(kind: TtsProviderKind): string {
  return TTS_PROVIDERS_BY_KIND[kind][0] ?? "auto";
}

export function showsTtsApiKey(provider: string): boolean {
  const mode = provider.trim().toLowerCase();
  return ["google", "azure", "elevenlabs", "openai", "openai_compatible", "http_custom"].includes(mode);
}

/** VieNeu Base URL only when Local backend = remote; cloud/HTTP always when applicable. */
export function showsTtsBaseUrl(provider: string, localBackend = "auto"): boolean {
  const mode = provider.trim().toLowerCase();
  if (mode === "vieneu") return localBackend.trim().toLowerCase() === "remote";
  return ["azure", "openai", "openai_compatible", "http_custom"].includes(mode);
}

export function showsTtsLocalBackend(provider: string): boolean {
  return provider.trim().toLowerCase() === "vieneu";
}

export function showsTtsCliBinary(provider: string): boolean {
  return provider.trim().toLowerCase() === "cli";
}

export const EDGE_FALLBACK_VOICE_OPTIONS = [
  { id: "vi-VN-HoaiMyNeural", label: "vi-VN-HoaiMyNeural (Female)" },
  { id: "vi-VN-NamMinhNeural", label: "vi-VN-NamMinhNeural (Male)" }
] as const;
