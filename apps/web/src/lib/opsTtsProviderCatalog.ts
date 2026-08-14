/** TTS Ops provider taxonomy + local install recipes (UI authority). */

import type {
  TtsAiCatalog,
  TtsAiCatalogLanguage,
  TtsAiCatalogModel,
  TtsAiCatalogVoice
} from "./api";

export type TtsProviderKind = "local" | "cloud" | "http" | "system";

export type TtsCatalogSelection = {
  languageCode?: string;
  modelId?: string;
  voiceId?: string;
};

function normalizedCatalogValue(value: string | null | undefined): string {
  return (value || "").trim().toLowerCase();
}

function normalizedCatalogId(value: string | null | undefined): string {
  return (value || "").trim();
}

function catalogListIncludes(values: string[] | null | undefined, selected: string): boolean {
  const wanted = normalizedCatalogId(selected);
  if (!wanted || !values?.length) return true;
  return values.some((value) => normalizedCatalogId(value) === wanted);
}

function catalogLanguageMatches(candidate: string, selected: string): boolean {
  const left = normalizedCatalogValue(candidate).replace(/_/g, "-");
  const right = normalizedCatalogValue(selected).replace(/_/g, "-");
  if (!left || !right) return true;
  return left === right || left.startsWith(`${right}-`) || right.startsWith(`${left}-`);
}

function catalogLanguagesInclude(values: string[] | null | undefined, selected: string): boolean {
  const wanted = normalizedCatalogValue(selected);
  if (!wanted || !values?.length) return true;
  return values.some((value) => catalogLanguageMatches(value, wanted));
}

/** Normalize the additive rich model catalog with the legacy `models: string[]` contract. */
export function ttsCatalogModelOptions(catalog: TtsAiCatalog | null | undefined): TtsAiCatalogModel[] {
  if (!catalog) return [];
  const byId = new Map<string, TtsAiCatalogModel>();
  for (const option of catalog.model_options || []) {
    const id = (option.id || "").trim();
    if (!id || byId.has(id)) continue;
    byId.set(id, { ...option, id, label: (option.label || id).trim() || id });
  }
  for (const raw of catalog.models || []) {
    const id = (raw || "").trim();
    if (!id || byId.has(id)) continue;
    byId.set(id, { id, label: id });
  }
  return [...byId.values()];
}

/** Use explicit languages first, then enrich partial catalogs from model/voice metadata. */
export function ttsCatalogLanguageOptions(
  catalog: TtsAiCatalog | null | undefined
): TtsAiCatalogLanguage[] {
  if (!catalog) return [];
  const byCode = new Map<string, TtsAiCatalogLanguage>();
  for (const option of catalog.languages || []) {
    const code = (option.code || "").trim();
    if (!code) continue;
    const key = normalizedCatalogValue(code);
    if (!byCode.has(key)) byCode.set(key, { code, label: (option.label || code).trim() || code });
  }
  const inferred = [
    ...(catalog.voices || []).flatMap((voice) => voice.languages || []),
    ...ttsCatalogModelOptions(catalog).flatMap((model) => model.languages || [])
  ];
  for (const raw of inferred) {
    const code = (raw || "").trim();
    const key = normalizedCatalogValue(code);
    if (code && !byCode.has(key)) byCode.set(key, { code, label: code });
  }
  return [...byCode.values()];
}

export function filterTtsCatalogModels(
  catalog: TtsAiCatalog | null | undefined,
  selection: TtsCatalogSelection
): TtsAiCatalogModel[] {
  const models = ttsCatalogModelOptions(catalog);
  const selectedVoice = (catalog?.voices || []).find(
    (voice) => normalizedCatalogId(voice.id) === normalizedCatalogId(selection.voiceId)
  );
  return models.filter((model) => {
    if (!catalogLanguagesInclude(model.languages, selection.languageCode || "")) return false;
    if (selectedVoice && !catalogListIncludes(model.voices, selectedVoice.id)) return false;
    if (selectedVoice && !catalogListIncludes(selectedVoice.models, model.id)) return false;
    return true;
  });
}

export function filterTtsCatalogVoices(
  catalog: TtsAiCatalog | null | undefined,
  selection: TtsCatalogSelection
): TtsAiCatalogVoice[] {
  const voices = catalog?.voices || [];
  const selectedModel = ttsCatalogModelOptions(catalog).find(
    (model) => normalizedCatalogId(model.id) === normalizedCatalogId(selection.modelId)
  );
  return voices.filter((voice) => {
    if (!catalogLanguagesInclude(voice.languages, selection.languageCode || "")) return false;
    if (selectedModel && !catalogListIncludes(voice.models, selectedModel.id)) return false;
    if (selectedModel && !catalogListIncludes(selectedModel.voices, voice.id)) return false;
    return true;
  });
}

export function filterTtsCatalogLanguages(
  catalog: TtsAiCatalog | null | undefined,
  selection: TtsCatalogSelection
): TtsAiCatalogLanguage[] {
  const languages = ttsCatalogLanguageOptions(catalog);
  const selectedVoice = (catalog?.voices || []).find(
    (voice) => normalizedCatalogId(voice.id) === normalizedCatalogId(selection.voiceId)
  );
  const selectedModel = ttsCatalogModelOptions(catalog).find(
    (model) => normalizedCatalogId(model.id) === normalizedCatalogId(selection.modelId)
  );
  return languages.filter((language) => {
    if (
      selectedVoice?.languages?.length &&
      !selectedVoice.languages.some((code) => catalogLanguageMatches(code, language.code))
    ) {
      return false;
    }
    if (
      selectedModel?.languages?.length &&
      !selectedModel.languages.some((code) => catalogLanguageMatches(code, language.code))
    ) {
      return false;
    }
    return true;
  });
}

export const TTS_KIND_ORDER: TtsProviderKind[] = ["local", "cloud", "http", "system"];

export const TTS_PROVIDERS_BY_KIND: Record<TtsProviderKind, readonly string[]> = {
  local: ["edge", "vieneu", "omnivoice", "cli", "custom"],
  cloud: ["google", "google_gemini", "azure", "elevenlabs", "openai"],
  http: ["openai_compatible", "http_custom"],
  system: ["auto", "placeholder"]
};

export const TTS_FALLBACK_PROVIDERS = [
  "none",
  "edge",
  "vieneu",
  "google",
  "google_gemini",
  "azure",
  "elevenlabs",
  "openai",
  "openai_compatible",
  "http_custom",
  "cli",
  "placeholder"
] as const;

/** Which Voice/Connection fields the Ops form should show for a provider. */
export type TtsFieldCapabilities = {
  voice: boolean;
  model: boolean;
  styles: boolean;
  api_key: boolean;
  base_url: boolean;
  local_backend: boolean;
  cli_binary: boolean;
};

export type LocalInstallRecipe = {
  packageName: string;
  installCommand: string;
  extraRequirement: string;
  defaultVoice: string;
  defaultModel: string;
  defaultLanguage?: string;
  /** Preferred provider slug after Install (custom local). */
  providerSlug?: string;
  hintKey: string;
};

const LOCAL_RECIPES: Record<string, LocalInstallRecipe> = {
  edge: {
    packageName: "edge-tts",
    installCommand: "pip install edge-tts",
    extraRequirement: "ffmpeg on PATH",
    defaultVoice: "vi-VN-HoaiMyNeural",
    defaultModel: "",
    defaultLanguage: "vi",
    hintKey: "opsTtsAi.hintEdge"
  },
  vieneu: {
    packageName: "vieneu",
    installCommand: "pip install vieneu",
    extraRequirement: "First run downloads models from Hugging Face",
    defaultVoice: "Phạm Tuyên",
    defaultModel: "v3turbo",
    defaultLanguage: "vi",
    hintKey: "opsTtsAi.hintVieneu"
  },
  cli: {
    packageName: "",
    installCommand: "",
    extraRequirement: "Binary must be on PATH or absolute path in CLI binary",
    defaultVoice: "vi-VN-HoaiMyNeural",
    defaultModel: "",
    defaultLanguage: "vi",
    hintKey: "opsTtsAi.hintCli"
  },
  omnivoice: {
    packageName: "OmniVoice-Studio",
    installCommand: "pip install git+https://github.com/debpalash/OmniVoice-Studio.git",
    extraRequirement: "First run may download Hugging Face models; GPU optional",
    defaultVoice: "auto",
    defaultModel: "k2-fsa/OmniVoice",
    defaultLanguage: "vi",
    providerSlug: "omnivoice",
    hintKey: "opsTtsAi.hintOmnivoice"
  }
};

/** Curated OmniVoice-Studio engines + voice presets (UI hydrate when API catalog is thin). */
export const OMNIVOICE_CURATED_MODELS = [
  "omnivoice",
  "k2-fsa/OmniVoice",
  "cosyvoice",
  "gpt-sovits",
  "voxcpm2",
  "moss-tts-nano",
  "kittentts",
  "sherpa-onnx",
  "mlx-audio",
  "indextts2",
  "omnivoice-gguf",
  "supertonic3",
  "moss-tts-v15",
  "dots-tts",
  "confucius4-tts"
] as const;

export const GEMINI_TTS_MODELS = [
  "gemini-2.5-flash-tts",
  "gemini-2.5-pro-tts",
  "gemini-2.5-flash-preview-tts",
  "gemini-2.5-pro-preview-tts"
] as const;

export const GEMINI_TTS_VOICES = [
  ["Zephyr", "Zephyr · bright"], ["Puck", "Puck · upbeat"],
  ["Charon", "Charon · informative"], ["Kore", "Kore · firm"],
  ["Fenrir", "Fenrir · excitable"], ["Leda", "Leda · youthful"],
  ["Orus", "Orus · firm"], ["Aoede", "Aoede · breezy"],
  ["Callirrhoe", "Callirrhoe · easy-going"], ["Autonoe", "Autonoe · bright"],
  ["Enceladus", "Enceladus · breathy"], ["Iapetus", "Iapetus · clear"],
  ["Umbriel", "Umbriel · easy-going"], ["Algieba", "Algieba · smooth"],
  ["Despina", "Despina · smooth"], ["Erinome", "Erinome · clear"],
  ["Algenib", "Algenib · gravelly"], ["Rasalgethi", "Rasalgethi · informative"],
  ["Laomedeia", "Laomedeia · upbeat"], ["Achernar", "Achernar · soft"],
  ["Alnilam", "Alnilam · firm"], ["Schedar", "Schedar · even"],
  ["Gacrux", "Gacrux · mature"], ["Pulcherrima", "Pulcherrima · forward"],
  ["Achird", "Achird · friendly"], ["Zubenelgenubi", "Zubenelgenubi · casual"],
  ["Vindemiatrix", "Vindemiatrix · gentle"], ["Sadachbia", "Sadachbia · lively"],
  ["Sadaltager", "Sadaltager · knowledgeable"], ["Sulafat", "Sulafat · warm"]
] as const;

export function canonicalizeGeminiVoiceId(value: string | null | undefined): string {
  const text = (value || "").trim();
  if (!text) return "";
  const byLower = new Map(GEMINI_TTS_VOICES.map(([id]) => [id.toLowerCase(), id]));
  const direct = byLower.get(text.toLowerCase());
  if (direct) return direct;
  const marker = "-chirp3-hd-";
  const lowered = text.toLowerCase();
  const markerIndex = lowered.lastIndexOf(marker);
  if (markerIndex >= 0) {
    return byLower.get(text.slice(markerIndex + marker.length).trim().toLowerCase()) || "";
  }
  return "";
}

/** Models currently backed by a real reup-douyin synthesize adapter. */
export const OMNIVOICE_SUPPORTED_MODELS = ["k2-fsa/OmniVoice"] as const;

export const OMNIVOICE_CURATED_VOICES = [
  { id: "auto", label: "Auto (model picks voice)" },
  { id: "alloy", label: "alloy (OpenAI-compat)" },
  { id: "echo", label: "echo (OpenAI-compat)" },
  { id: "fable", label: "fable (OpenAI-compat)" },
  { id: "onyx", label: "onyx (OpenAI-compat)" },
  { id: "nova", label: "nova (OpenAI-compat)" },
  { id: "shimmer", label: "shimmer (OpenAI-compat)" },
  { id: "instruct:vi_female_north", label: "VI · nữ miền Bắc (instruct)" },
  { id: "instruct:vi_female_south", label: "VI · nữ miền Nam (instruct)" },
  { id: "instruct:vi_male_north", label: "VI · nam miền Bắc (instruct)" },
  { id: "instruct:vi_male_south", label: "VI · nam miền Nam (instruct)" },
  { id: "instruct:vi_news", label: "VI · đọc tin (instruct)" },
  { id: "instruct:vi_warm", label: "VI · ấm / kể chuyện (instruct)" },
  { id: "instruct:en_female", label: "EN · female (instruct)" },
  { id: "instruct:en_male", label: "EN · male (instruct)" },
  { id: "instruct:en_british", label: "EN · British (instruct)" }
] as const;

export function getOmnivoiceCuratedCatalogCapabilities(): TtsFieldCapabilities {
  return { voice: true, model: true, styles: false, api_key: false, base_url: false, local_backend: false, cli_binary: false };
}

export function isOmnivoiceProvider(provider: string): boolean {
  const mode = provider.trim().toLowerCase();
  return mode === "omnivoice" || mode === "omnivoice-studio" || mode === "omnivoice_studio";
}

/**
 * Hydrate a known provider catalog without re-running Install/Test.
 *
 * Older OmniVoice profiles may have a successful persisted probe without the
 * catalog payload. Voice presets are deterministic, so the editor can safely
 * use the curated fallback. Model choices stay limited to adapters that the
 * worker can actually execute.
 */
export function resolveTtsCatalogForProvider(
  provider: string,
  persistedCatalog: TtsAiCatalog | null | undefined
): TtsAiCatalog | null {
  if (provider.trim().toLowerCase() === "google_gemini") {
    const voiceIds = GEMINI_TTS_VOICES.map(([id]) => id);
    return {
      source: persistedCatalog?.source === "provider" ? "provider" : "curated",
      voices: GEMINI_TTS_VOICES.map(([id, label]) => ({
        id,
        label,
        languages: ["vi-VN"],
        models: [...GEMINI_TTS_MODELS],
        capabilities: ["expressive", "single_speaker"]
      })),
      styles: [],
      models: [...GEMINI_TTS_MODELS],
      model_options: GEMINI_TTS_MODELS.map((id) => ({
        id,
        label: id,
        languages: ["vi-VN"],
        voices: voiceIds,
        capabilities: ["audio", "expressive_tts"]
      })),
      languages: [{ code: "vi-VN", label: "Tiếng Việt (Việt Nam)" }],
      default_voice_id: "Kore",
      default_model_id: "gemini-2.5-flash-tts",
      default_language_code: "vi-VN",
      warning: persistedCatalog?.warning || "",
      discovery: persistedCatalog?.discovery || null,
      sample_rate: persistedCatalog?.sample_rate ?? null,
      backends: [],
      capabilities: persistedCatalog?.capabilities || {
        voice: true,
        model: true,
        api_key: true
      }
    };
  }
  if (!isOmnivoiceProvider(provider)) return persistedCatalog ?? null;

  const persistedVoices = persistedCatalog?.voices?.length ? persistedCatalog.voices : null;
  const supportedModels = (persistedCatalog?.models || []).filter((model) =>
    OMNIVOICE_SUPPORTED_MODELS.includes(model as (typeof OMNIVOICE_SUPPORTED_MODELS)[number])
  );

  return {
    source: persistedCatalog?.source || "curated",
    voices: persistedVoices
      ? [...persistedVoices]
      : OMNIVOICE_CURATED_VOICES.map((voice) => ({ id: voice.id, label: voice.label })),
    styles: [...(persistedCatalog?.styles || [])],
    models: supportedModels.length ? supportedModels : [...OMNIVOICE_SUPPORTED_MODELS],
    default_voice_id: persistedCatalog?.default_voice_id || "auto",
    warning: persistedCatalog?.warning || "",
    sample_rate: persistedCatalog?.sample_rate ?? null,
    backends: [...(persistedCatalog?.backends || [])],
    capabilities: getOmnivoiceCuratedCatalogCapabilities()
  };
}

/** Map common package / repo names → recipe key. */
const PACKAGE_RECIPE_ALIASES: Record<string, string> = {
  "omnivoice-studio": "omnivoice",
  omnivoicestudio: "omnivoice",
  omnivoice: "omnivoice",
  "edge-tts": "edge",
  edgetts: "edge",
  vieneu: "vieneu"
};

const EMPTY_CAPS: TtsFieldCapabilities = {
  voice: false,
  model: false,
  styles: false,
  api_key: false,
  base_url: false,
  local_backend: false,
  cli_binary: false
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
  return mode === "edge" || mode === "vieneu" || mode === "omnivoice" || mode === "cli";
}

export function isCustomLocalProvider(provider: string): boolean {
  const mode = provider.trim().toLowerCase();
  return resolveTtsProviderKind(mode) === "local" && !isPresetLocalProvider(mode) && mode !== "custom";
}

export function looksLikeEdgeVoiceId(voiceId: string): boolean {
  const value = voiceId.trim();
  if (!value) return false;
  if (value.includes(" ")) return false;
  return value.includes("Neural") || /^[a-z]{2}-[A-Z]{2}-/.test(value);
}

export function normalizePackageKey(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\.git$/i, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Resolve install recipe from provider slug or package/repo name. */
export function getLocalInstallRecipe(providerOrPackage: string): LocalInstallRecipe | null {
  const mode = providerOrPackage.trim().toLowerCase();
  if (LOCAL_RECIPES[mode]) return LOCAL_RECIPES[mode];
  const key = normalizePackageKey(providerOrPackage);
  const alias = PACKAGE_RECIPE_ALIASES[key] || PACKAGE_RECIPE_ALIASES[key.replace(/-/g, "")];
  if (alias && LOCAL_RECIPES[alias]) return LOCAL_RECIPES[alias];
  return null;
}

/** Prefer recipe slug; else sanitize package name into a custom provider slug. */
export function resolveProviderSlugFromInstall(packageName: string, repoUrl = ""): string | null {
  const recipe =
    getLocalInstallRecipe(packageName) ||
    (repoUrl ? getLocalInstallRecipe(deriveTtsInstallFromRepoUrl(repoUrl)?.packageName || "") : null);
  if (recipe?.providerSlug) return recipe.providerSlug;
  const fromPackage = normalizePackageKey(packageName);
  if (fromPackage && /^[a-z][a-z0-9_\-]{0,62}$/.test(fromPackage.replace(/-/g, "_"))) {
    return fromPackage.replace(/-/g, "_").slice(0, 63);
  }
  if (fromPackage) {
    const slug = fromPackage.replace(/-/g, "_");
    if (/^[a-z][a-z0-9_]{0,62}$/.test(slug)) return slug;
  }
  return null;
}

/** Derive allowlisted pip install from a GitHub/GitLab HTTPS repo URL (no network scan). */
export function deriveTtsInstallFromRepoUrl(raw: string): {
  installCommand: string;
  packageName: string;
} | null {
  const url = raw.trim().replace(/\/+$/, "");
  if (!url) return null;
  const match = url.match(
    /^https:\/\/(github\.com|gitlab\.com)\/[A-Za-z0-9._\-]+\/([A-Za-z0-9._\-]+?)(?:\.git)?(?:@[A-Za-z0-9._/\-]+)?$/i
  );
  if (!match) return null;
  const hostPath = url.replace(/@[^@]+$/, "");
  const withGit = /\.git$/i.test(hostPath) ? hostPath : `${hostPath}.git`;
  const packageName = match[2].replace(/\.git$/i, "");
  return {
    installCommand: `pip install git+${withGit}`,
    packageName
  };
}

export function defaultProviderForKind(kind: TtsProviderKind): string {
  return TTS_PROVIDERS_BY_KIND[kind][0] ?? "auto";
}

/**
 * Capability profile for the adaptive Ops TTS form.
 * Catalog capabilities (when present) override the static profile for show/hide.
 */
export function getTtsFieldCapabilities(
  provider: string,
  localBackend = "auto",
  catalogCaps?: Partial<TtsFieldCapabilities> | null
): TtsFieldCapabilities {
  const mode = provider.trim().toLowerCase();
  let base: TtsFieldCapabilities;

  if (mode === "edge") {
    base = { ...EMPTY_CAPS, voice: true };
  } else if (mode === "vieneu") {
    base = {
      ...EMPTY_CAPS,
      voice: true,
      model: true,
      styles: true,
      local_backend: true,
      base_url: localBackend.trim().toLowerCase() === "remote"
    };
  } else if (mode === "cli") {
    base = { ...EMPTY_CAPS, voice: true, cli_binary: true };
  } else if (["google", "google_gemini", "azure", "elevenlabs", "openai"].includes(mode)) {
    base = {
      ...EMPTY_CAPS,
      voice: true,
      model: true,
      api_key: true,
      base_url: mode === "google_gemini" || mode === "azure" || mode === "openai"
    };
  } else if (mode === "openai_compatible" || mode === "http_custom") {
    base = { ...EMPTY_CAPS, voice: true, model: true, api_key: true, base_url: true };
  } else if (mode === "auto" || mode === "placeholder") {
    base = { ...EMPTY_CAPS, voice: true };
  } else if (isCustomLocalProvider(mode) || mode === "custom" || mode === "omnivoice") {
    // Unknown / custom local (OmniVoice, etc.): voice + model free-text, never Edge-only layout.
    base = { ...EMPTY_CAPS, voice: true, model: true };
  } else {
    base = { ...EMPTY_CAPS, voice: true };
  }

  if (!catalogCaps) return base;
  return {
    voice: catalogCaps.voice ?? base.voice,
    model: catalogCaps.model ?? base.model,
    styles: catalogCaps.styles ?? base.styles,
    api_key: catalogCaps.api_key ?? base.api_key,
    base_url: catalogCaps.base_url ?? base.base_url,
    local_backend: catalogCaps.local_backend ?? base.local_backend,
    cli_binary: catalogCaps.cli_binary ?? base.cli_binary
  };
}

export function showsTtsApiKey(provider: string): boolean {
  return getTtsFieldCapabilities(provider).api_key;
}

/** VieNeu Base URL only when Local backend = remote; cloud/HTTP always when applicable. */
export function showsTtsBaseUrl(provider: string, localBackend = "auto"): boolean {
  return getTtsFieldCapabilities(provider, localBackend).base_url;
}

export function showsTtsLocalBackend(provider: string): boolean {
  return getTtsFieldCapabilities(provider).local_backend;
}

export function showsTtsCliBinary(provider: string): boolean {
  return getTtsFieldCapabilities(provider).cli_binary;
}

export const EDGE_FALLBACK_VOICE_OPTIONS = [
  { id: "vi-VN-HoaiMyNeural", label: "vi-VN-HoaiMyNeural (Female)" },
  { id: "vi-VN-NamMinhNeural", label: "vi-VN-NamMinhNeural (Male)" }
] as const;
