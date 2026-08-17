"use client";

import { useEffect, useRef, useState } from "react";
import {
  createTtsAiProfile,
  deleteTtsAiProfile,
  fetchTtsAi,
  fetchTtsAiEngines,
  fetchTtsAiEngineInstallStatus,
  fetchTtsAiInstallStatus,
  fetchTtsAiPreviewStatus,
  cancelTtsAiPreview,
  fetchTtsAiProfile,
  installTtsAiPackage,
  installTtsAiEngine,
  previewTtsAiSpeech,
  renameTtsAiProfile,
  reorderTtsAiProfiles,
  saveTtsAiProfile,
  setTtsAiProfileEnabled,
  testTtsAi,
  type TtsAiCatalog,
  type TtsAiEngineInstallJobResponse,
  type TtsAiEngineOption,
  type TtsAiInstallResponse,
  type TtsAiProfileSummary,
  type TtsAiProbeCheck,
  type TtsAiResponse,
  type TtsAiRuntime
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { isSetupTableInteractiveDragTarget, moveItemIndex, profileIdsOf } from "../../lib/opsProfileReorder";
import {
  formatProviderError,
  providerTestErrorHint,
  type ConnectionTestResult
} from "../../lib/opsTranslationAiFormat";
import { formatTtsProbeSuccess } from "../../lib/opsTtsTestFormat";
import {
  catalogFromRuntime,
  resolveTtsReadyState,
  ttsReadyChipClass,
  ttsReadyLabelKey
} from "../../lib/opsTtsReadyState";
import {
  deriveTtsInstallFromRepoUrl,
  canonicalizeGeminiVoiceId,
  defaultProviderForKind,
  filterTtsCatalogLanguages,
  filterTtsCatalogModels,
  filterTtsCatalogVoices,
  getLocalInstallRecipe,
  getTtsFieldCapabilities,
  isCustomLocalProvider,
  isOmnivoiceProvider,
  isPresetLocalProvider,
  looksLikeEdgeVoiceId,
  resolveTtsCatalogForProvider,
  resolveProviderSlugFromInstall,
  resolveTtsProviderKind,
  showsTtsApiKey,
  showsTtsBaseUrl,
  showsTtsCliBinary,
  showsTtsLocalBackend,
  ttsCatalogLanguageOptions,
  ttsCatalogModelOptions,
  TTS_FALLBACK_PROVIDERS,
  TTS_KIND_ORDER,
  TTS_PROVIDERS_BY_KIND,
  EDGE_FALLBACK_VOICE_OPTIONS,
  type TtsProviderKind
} from "../../lib/opsTtsProviderCatalog";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsPanel } from "./OpsShared";
import {
  defaultHttpConnector,
  httpConnectorFromOptions,
  httpConnectorToOptions,
  lucylabJsonRpcPreset,
  parseTtsCurl,
  type HttpConnectorAuthType,
  type HttpConnectorEndpoint,
  type HttpConnectorFormState,
  type HttpConnectorMode,
  type HttpConnectorResponseType
} from "../../lib/ttsHttpConnector";

export {
  showsTtsApiKey,
  showsTtsBaseUrl,
  showsTtsCliBinary,
  showsTtsLocalBackend,
  resolveTtsProviderKind,
  getLocalInstallRecipe,
  getTtsFieldCapabilities
} from "../../lib/opsTtsProviderCatalog";

type FormState = {
  enabled: boolean;
  provider: string;
  providerChoice: string;
  customProviderSlug: string;
  voiceId: string;
  speakingRate: string;
  languageCode: string;
  modelId: string;
  apiKeyInput: string;
  credentialMode: string;
  googleServiceAccountJson: string;
  googleServiceAccountFileName: string;
  clearGoogleServiceAccount: boolean;
  googleCloudRegion: string;
  baseUrl: string;
  timeoutSeconds: string;
  fallbackProvider: string;
  fallbackVoiceId: string;
  localBackend: string;
  device: string;
  cliBinary: string;
  style: string;
  expressiveMode: string;
  synthesisStrategy: string;
  maxWholeVideoSeconds: string;
  maxBlockSeconds: string;
  compactTriggerRatio: string;
  installCommand: string;
  extraRequirement: string;
  packageName: string;
  repoUrl: string;
  /** Preserve unknown provider options while editing a setup. */
  optionsJson: Record<string, unknown>;
  httpConnector: HttpConnectorFormState;
};

function resolveProviderChoice(provider: string): { choice: string; customSlug: string } {
  if (isPresetLocalProvider(provider) || resolveTtsProviderKind(provider) !== "local") {
    return { choice: provider, customSlug: "" };
  }
  return { choice: "custom", customSlug: provider };
}

function toForm(data: TtsAiResponse): FormState {
  const options = data.options_json || {};
  const expressive =
    options.expressive_tts && typeof options.expressive_tts === "object"
      ? (options.expressive_tts as Record<string, unknown>)
      : {};
  const provider = data.provider || "auto";
  const agentOptions =
    options.google_cloud_tts && typeof options.google_cloud_tts === "object"
      ? (options.google_cloud_tts as Record<string, unknown>)
      : {};
  const recipe = getLocalInstallRecipe(provider);
  const choice = resolveProviderChoice(provider);
  return {
    enabled: data.enabled,
    provider,
    providerChoice: choice.choice,
    customProviderSlug: choice.customSlug,
    voiceId:
      isGeminiExpressiveProvider(provider)
        ? canonicalizeGeminiVoiceId(data.voice_id) || (provider === "google_cloud_tts" ? "Achernar" : "Kore")
        : data.voice_id || "",
    speakingRate: String(data.speaking_rate ?? 1),
    languageCode: data.language_code || "vi",
    modelId: data.model_id || "",
    apiKeyInput: "",
    credentialMode: data.credential_mode || (provider === "google" ? "google_service_account" : "api_key"),
    googleServiceAccountJson: "",
    googleServiceAccountFileName: "",
    clearGoogleServiceAccount: false,
    googleCloudRegion: typeof agentOptions.region === "string" ? agentOptions.region : "global",
    baseUrl: data.base_url || (provider === "google" ? "https://texttospeech.googleapis.com/v1" : ""),
    timeoutSeconds: String(data.timeout_seconds ?? 120),
    fallbackProvider: data.fallback_provider || "none",
    fallbackVoiceId: data.fallback_voice_id || "",
    localBackend: data.local_backend || "auto",
    device: data.device || "auto",
    cliBinary: data.cli_binary || "",
    style: typeof options.style === "string" ? options.style : "tu_nhien",
    expressiveMode:
      typeof expressive.mode === "string"
        ? expressive.mode
        : provider === "google"
          ? "required"
          : "best_effort",
    synthesisStrategy:
      typeof expressive.synthesis_strategy === "string"
        ? expressive.synthesis_strategy
        : isGeminiExpressiveProvider(provider)
          ? "whole_video"
          : "segment",
    maxWholeVideoSeconds: String(expressive.max_whole_video_seconds ?? 180),
    maxBlockSeconds: String(expressive.max_block_seconds ?? 45),
    compactTriggerRatio: String(expressive.compact_trigger_ratio ?? 0.88),
    installCommand:
      typeof options.install_command === "string" && options.install_command.trim()
        ? options.install_command
        : recipe?.installCommand || "",
    extraRequirement:
      typeof options.extra_requirement === "string" && options.extra_requirement.trim()
        ? options.extra_requirement
        : recipe?.extraRequirement || "",
    packageName: typeof options.package_name === "string" ? options.package_name : recipe?.packageName || "",
    repoUrl: typeof options.repo_url === "string" ? options.repo_url : "",
    optionsJson: { ...options },
    httpConnector: httpConnectorFromOptions(options)
  };
}

function effectiveProvider(form: FormState): string {
  if (form.providerChoice === "custom") {
    return form.customProviderSlug.trim().toLowerCase() || "custom";
  }
  return form.providerChoice;
}

/** Local/Cloud/HTTP require an explicit provider before Test; System may use auto. */
function nameProviderForTest(form: FormState): string {
  if (form.providerChoice === "custom") {
    return form.customProviderSlug.trim().toLowerCase();
  }
  return (form.providerChoice || form.provider || "").trim().toLowerCase();
}

function providerSelectValue(form: FormState): string {
  if (form.providerChoice === "custom" || isCustomLocalProvider(form.provider)) {
    return "custom";
  }
  return (form.providerChoice || form.provider || "").trim().toLowerCase();
}

function kindRequiresNamedProvider(kind: TtsProviderKind): boolean {
  return kind === "local" || kind === "cloud" || kind === "http";
}

function engineDependencyLabelKey(status: string): string {
  if (status === "ready") return "opsTtsAi.engineStatusReady";
  if (status === "installed") return "opsTtsAi.engineStatusInstalled";
  if (status === "missing") return "opsTtsAi.engineStatusMissing";
  if (status === "external") return "opsTtsAi.engineStatusExternal";
  if (status === "incompatible") return "opsTtsAi.engineStatusIncompatible";
  return "opsTtsAi.engineStatusManual";
}

function engineInstallStepLabelKey(step: string): string {
  if (step === "preflight") return "opsTtsAi.engineStepPreflight";
  if (step === "clone_repo") return "opsTtsAi.engineStepCloneRepo";
  if (step === "create_venv") return "opsTtsAi.engineStepCreateVenv";
  if (step === "install_dependency") return "opsTtsAi.engineStepDependencies";
  if (step === "download_weights") return "opsTtsAi.engineStepWeights";
  if (step === "probe") return "opsTtsAi.engineStepProbe";
  if (step === "complete") return "opsTtsAi.engineStepComplete";
  return "opsTtsAi.engineStepQueued";
}

type EngineCatalogCategory = "ready" | "installable" | "installed" | "setup" | "unavailable";
type CatalogRefreshPhase = "idle" | "preparing" | "loading";

const TTS_CATALOG_MANUAL_VALUE = "__manual__";
const GOOGLE_SERVICE_ACCOUNT_MAX_BYTES = 64 * 1024;
const GOOGLE_CREDENTIAL_MODES = [
  "google_service_account",
  "google_adc",
  "google_oauth_token"
] as const;
const DIRECT_CLOUD_PREVIEW_PROVIDERS = new Set(["google", "google_gemini", "google_cloud_tts"]);
const HTTP_CONNECTOR_MODES: HttpConnectorMode[] = ["auto", "openapi", "custom"];
const HTTP_CATALOG_RESOURCES = ["models", "voices", "languages"] as const;

function supportsDirectCloudPreview(provider: string): boolean {
  return DIRECT_CLOUD_PREVIEW_PROVIDERS.has((provider || "").trim().toLowerCase());
}

function isGeminiExpressiveProvider(provider: string): boolean {
  return ["google_gemini", "google_cloud_tts"].includes((provider || "").trim().toLowerCase());
}

function sameCatalogId(left: string | null | undefined, right: string | null | undefined): boolean {
  return (left || "").trim() === (right || "").trim();
}

function googleServiceAccountMetadata(raw: string): { email: string; projectId: string } | null {
  if (!raw.trim()) return null;
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (value.type !== "service_account") return null;
    const email = typeof value.client_email === "string" ? value.client_email.trim() : "";
    const projectId = typeof value.project_id === "string" ? value.project_id.trim() : "";
    const privateKey = typeof value.private_key === "string" ? value.private_key : "";
    if (!email || !projectId || !privateKey.includes("PRIVATE KEY")) return null;
    return { email, projectId };
  } catch {
    return null;
  }
}

function engineCatalogCategory(engine: TtsAiEngineOption): EngineCatalogCategory {
  if (engine.selectable) return "ready";
  if (engine.installable) return "installable";
  if (engine.dependency_status === "installed") return "installed";
  if (
    engine.dependency_status !== "incompatible" &&
    (engine.install_mode === "manual" || engine.install_mode === "external")
  ) {
    return "setup";
  }
  return "unavailable";
}

type EngineCatalogActionIconKind = "install" | "loading" | "server" | "guide" | "collapse";

function EngineCatalogActionIcon({ kind }: { kind: EngineCatalogActionIconKind }) {
  if (kind === "loading") {
    return (
      <svg className="is-spinning" viewBox="0 0 20 20" aria-hidden="true">
        <circle
          cx="10"
          cy="10"
          r="6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          opacity="0.3"
        />
        <path
          d="M10 4a6 6 0 0 1 5.7 4.1"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "server") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <rect
          x="4"
          y="3.7"
          width="12"
          height="5"
          rx="1.4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <rect
          x="4"
          y="11.3"
          width="12"
          height="5"
          rx="1.4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <circle cx="7" cy="6.2" r="0.8" fill="currentColor" />
        <circle cx="7" cy="13.8" r="0.8" fill="currentColor" />
      </svg>
    );
  }
  if (kind === "guide") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4 4.5c2.1-.6 4-.2 6 1.2v10c-2-1.4-3.9-1.8-6-1.2v-10Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path
          d="M16 4.5c-2.1-.6-4-.2-6 1.2v10c2-1.4 3.9-1.8 6-1.2v-10Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "collapse") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="m5.5 12.2 4.5-4.4 4.5 4.4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M10 3.5v8M6.8 8.5 10 11.7l3.2-3.2M4 14v1.8h12V14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function blankForm(): FormState {
  return {
    enabled: false,
    provider: "auto",
    providerChoice: "auto",
    customProviderSlug: "",
    voiceId: "",
    speakingRate: "",
    languageCode: "",
    modelId: "",
    apiKeyInput: "",
    credentialMode: "api_key",
    googleServiceAccountJson: "",
    googleServiceAccountFileName: "",
    clearGoogleServiceAccount: false,
    googleCloudRegion: "global",
    baseUrl: "",
    timeoutSeconds: "",
    fallbackProvider: "",
    fallbackVoiceId: "",
    localBackend: "",
    device: "",
    cliBinary: "",
    style: "",
    expressiveMode: "best_effort",
    synthesisStrategy: "segment",
    maxWholeVideoSeconds: "180",
    maxBlockSeconds: "45",
    compactTriggerRatio: "0.88",
    installCommand: "",
    extraRequirement: "",
    packageName: "",
    repoUrl: "",
    optionsJson: {},
    httpConnector: defaultHttpConnector()
  };
}

function kindLabelKey(kind: TtsProviderKind): string {
  if (kind === "local") return "opsTtsAi.kindLocal";
  if (kind === "cloud") return "opsTtsAi.kindCloud";
  if (kind === "http") return "opsTtsAi.kindHttp";
  return "opsTtsAi.kindSystem";
}

function kindHintKey(kind: TtsProviderKind): string {
  if (kind === "local") return "opsTtsAi.kindLocalHint";
  if (kind === "cloud") return "opsTtsAi.kindCloudHint";
  if (kind === "http") return "opsTtsAi.kindHttpHint";
  return "opsTtsAi.kindSystemHint";
}

type TtsSetupActionIconKind =
  | "edit"
  | "delete"
  | "add"
  | "back"
  | "test"
  | "save"
  | "copy"
  | "install"
  | "reinstall"
  | "preview"
  | "stop";

function nextBlankSetupName(existing: Array<{ name: string }>): string {
  const used = new Set(existing.map((p) => (p.name || "").trim().toLowerCase()).filter(Boolean));
  let index = existing.length + 1;
  for (;;) {
    const candidate = `Setup ${index}`;
    if (!used.has(candidate.toLowerCase())) return candidate;
    index += 1;
  }
}

function TtsSetupActionIcon({ kind }: { kind: TtsSetupActionIconKind }) {
  if (kind === "add") {
    return (
      <svg className="ops-tts-list-toolbar__plus" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M10 4.5v11M4.5 10h11"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "back") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M11.5 4.5 6 10l5.5 5.5M6 10h8.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "test") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M7.2 12.8 12.8 7.2M8.4 6.4l1.2-1.2a2.1 2.1 0 0 1 3 3L11.4 9.4M11.6 13.6l-1.2 1.2a2.1 2.1 0 0 1-3-3l1.2-1.2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "save") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 4.5h9.2L15.5 6.3V15.5H4.5V4.5z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinejoin="round"
        />
        <path
          d="M7 4.5v3.8h5.2V4.5M7 15.5v-4.2h6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "copy") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <rect x="7" y="7" width="8.5" height="8.5" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.75" />
        <path
          d="M5.5 13H5a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 5 3.5h6.5A1.5 1.5 0 0 1 13 5v.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "install") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M10 3.5v8.2M6.8 8.5 10 11.7l3.2-3.2M4.5 15.5h11"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "reinstall") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 10a5.5 5.5 0 0 1 9.4-3.9M15.5 10a5.5 5.5 0 0 1-9.4 3.9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
        <path
          d="M14.2 3.8v3.2h-3.2M5.8 16.2v-3.2h3.2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "preview") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M7.2 5.2 15 10l-7.8 4.8V5.2z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "stop") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <rect x="5.5" y="5.5" width="9" height="9" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.75" />
      </svg>
    );
  }
  if (kind === "edit") {
    return (
      <svg className="ops-tts-setup-table__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M4 20h4.2L18.8 9.4a1.8 1.8 0 0 0 0-2.5l-1.7-1.7a1.8 1.8 0 0 0-2.5 0L4 15.8V20z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M13.2 6.4 17.6 10.8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg className="ops-tts-setup-table__icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 7h16M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M6.5 7 7.4 19a1.5 1.5 0 0 0 1.5 1.3h6.2a1.5 1.5 0 0 0 1.5-1.3L17.5 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10 11v5.5M14 11v5.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function OpsTtsAiPage() {
  const t = useT();
  const asyncAction = useAsyncAction();
  const { notify } = useNotice();
  const [form, setForm] = useState<FormState | null>(null);
  const [kind, setKind] = useState<TtsProviderKind>("system");
  const [meta, setMeta] = useState<{
    apiKeySet: boolean;
    apiKeyMasked: string;
    source: string;
    googleServiceAccountSet: boolean;
    googleServiceAccountEmail: string;
    googleServiceAccountProjectId: string;
  }>({
    apiKeySet: false,
    apiKeyMasked: "",
    source: "env",
    googleServiceAccountSet: false,
    googleServiceAccountEmail: "",
    googleServiceAccountProjectId: ""
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<(ConnectionTestResult & {
    checks?: TtsAiProbeCheck[];
    config_fingerprint?: string;
  }) | null>(null);
  const [catalog, setCatalog] = useState<TtsAiCatalog | null>(null);
  const [catalogStale, setCatalogStale] = useState(false);
  const [catalogRefreshPhase, setCatalogRefreshPhase] = useState<CatalogRefreshPhase>("idle");
  const [curlImportDraft, setCurlImportDraft] = useState("");
  const [curlImportFeedback, setCurlImportFeedback] = useState<{ ok: boolean; message: string } | null>(null);
  const [engineCatalog, setEngineCatalog] = useState<TtsAiEngineOption[]>([]);
  const [engineCatalogLoading, setEngineCatalogLoading] = useState(false);
  const [engineCatalogError, setEngineCatalogError] = useState<string | null>(null);
  const [engineInstallingId, setEngineInstallingId] = useState<string | null>(null);
  const [engineExpandedId, setEngineExpandedId] = useState<string | null>(null);
  const [engineGroupTab, setEngineGroupTab] = useState<EngineCatalogCategory>("installable");
  const [engineInstallJob, setEngineInstallJob] = useState<TtsAiEngineInstallJobResponse | null>(null);
  const [runtime, setRuntime] = useState<TtsAiRuntime | null>(null);
  const [liveImportOk, setLiveImportOk] = useState<boolean | null>(null);
  const [installResult, setInstallResult] = useState<{
    ok: boolean;
    detail: string;
    command: string;
    log_tail: string;
    already_satisfied?: boolean;
  } | null>(null);
  const [previewText, setPreviewText] = useState("Xin chào, đây là bản xem trước giọng đọc tiếng Việt.");
  const [previewing, setPreviewing] = useState(false);
  const [previewAudioUrl, setPreviewAudioUrl] = useState<string | null>(null);
  const [previewFeedback, setPreviewFeedback] = useState<string | null>(null);
  const [previewMeta, setPreviewMeta] = useState<{
    provider: string;
    duration: number;
    detail: string;
    requestedVoiceId: string;
    resolvedVoiceId: string;
    requestedModelId: string;
    resolvedModelId: string;
  } | null>(null);
  const [profiles, setProfiles] = useState<TtsAiProfileSummary[]>([]);
  const [activeProfileId, setActiveProfileId] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "editor">("list");
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [editingProfileName, setEditingProfileName] = useState("");
  const [renamingProfileId, setRenamingProfileId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [dragFromId, setDragFromId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const renameInputRef = useRef<HTMLInputElement | null>(null);
  const installPollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const installPollCancelledRef = useRef(false);
  const catalogPreloadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewPollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewPollCancelledRef = useRef(false);

  function applyCatalog(nextCatalog: TtsAiCatalog | null, base: FormState) {
    setCatalog(nextCatalog);
    setCatalogStale(false);
    if (!nextCatalog) return base;
    const patch = { ...base };
    const voices = nextCatalog.voices || [];
    if (voices.length > 0) {
      const preserveManual = ["cloud", "http"].includes(resolveTtsProviderKind(base.provider));
      if (!patch.voiceId.trim() || (!preserveManual && !voices.some((v) => sameCatalogId(v.id, patch.voiceId)))) {
        // Remote providers may expose vendor-specific ids that are not in a partial catalog.
        // Keep those manual values instead of silently replacing a saved configuration.
        patch.voiceId = nextCatalog.default_voice_id || voices[0]?.id || patch.voiceId;
      }
    }
    if (nextCatalog.styles?.length > 0 && !nextCatalog.styles.includes(patch.style)) {
      patch.style = nextCatalog.styles[0] || patch.style;
    }
    const models = ttsCatalogModelOptions(nextCatalog);
    if (models.length > 0) {
      const preserveManual = ["cloud", "http"].includes(resolveTtsProviderKind(base.provider));
      if (!patch.modelId.trim() || (!preserveManual && !models.some((model) => sameCatalogId(model.id, patch.modelId)))) {
        patch.modelId = nextCatalog.default_model_id || models[0]?.id || patch.modelId;
      }
    }
    if (!patch.languageCode.trim() && nextCatalog.default_language_code) {
      patch.languageCode = nextCatalog.default_language_code;
    }
    return patch;
  }

  function applyListResponse(data: TtsAiResponse) {
    setProfiles(data.profiles || []);
    setActiveProfileId(data.active_profile_id || "");
  }

  async function loadOmnivoiceEngines() {
    setEngineCatalogLoading(true);
    setEngineCatalogError(null);
    try {
      const response = await fetchTtsAiEngines();
      setEngineCatalog(response.engines || []);
    } catch (err) {
      setEngineCatalogError(err instanceof Error ? err.message : t("opsTtsAi.engineCatalogError"));
    } finally {
      setEngineCatalogLoading(false);
    }
  }

  function applyResponse(data: TtsAiResponse) {
    let next = toForm(data);
    setRuntime(data.runtime || null);
    setLiveImportOk(data.live_import_ok ?? null);
    applyListResponse(data);
    const hydrated = resolveTtsCatalogForProvider(
      next.provider,
      catalogFromRuntime(data.runtime || null, next.provider)
    );
    if (hydrated) {
      next = applyCatalog(hydrated, next);
    } else {
      setCatalog(null);
      setCatalogStale(false);
    }
    // Banners are session action feedback only — durable status stays on runtime chips.
    setTestResult(null);
    setInstallResult(null);
    setPreviewFeedback(null);
    setForm(next);
    setCurlImportDraft("");
    setCurlImportFeedback(null);
    setKind(resolveTtsProviderKind(next.provider));
    setMeta({
      apiKeySet: data.api_key_set,
      apiKeyMasked: data.api_key_masked,
      source: data.source,
      googleServiceAccountSet: data.google_service_account_set,
      googleServiceAccountEmail: data.google_service_account_email,
      googleServiceAccountProjectId: data.google_service_account_project_id
    });
  }

  async function loadList() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTtsAi();
      applyListResponse(data);
      setViewMode("list");
      setEditingProfileId(null);
      setForm(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.loadError"));
    } finally {
      setLoading(false);
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      if (viewMode === "editor" && editingProfileId) {
        const data = await fetchTtsAiProfile(editingProfileId);
        applyResponse(data);
        if (data.profiles) applyListResponse(data);
      } else {
        const data = await fetchTtsAi();
        applyListResponse(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.loadError"));
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadList();
  }, [t]);

  useEffect(() => {
    if (!form || !isOmnivoiceProvider(effectiveProvider(form))) {
      installPollCancelledRef.current = true;
      setEngineCatalog([]);
      setEngineCatalogError(null);
      setEngineInstallJob(null);
      return;
    }
    installPollCancelledRef.current = false;
    void loadOmnivoiceEngines();
    void reattachEngineInstallJob();
  }, [form?.provider, form?.providerChoice, form?.customProviderSlug]);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  useEffect(() => {
    return () => {
      if (previewAudioUrl) URL.revokeObjectURL(previewAudioUrl);
    };
  }, [previewAudioUrl]);

  useEffect(() => {
    return () => {
      installPollCancelledRef.current = true;
      if (installPollTimerRef.current) {
        clearTimeout(installPollTimerRef.current);
        installPollTimerRef.current = null;
      }
      if (catalogPreloadTimerRef.current) {
        clearTimeout(catalogPreloadTimerRef.current);
        catalogPreloadTimerRef.current = null;
      }
      previewPollCancelledRef.current = true;
      if (previewPollTimerRef.current) {
        clearTimeout(previewPollTimerRef.current);
        previewPollTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!renamingProfileId) return;
    const input = renameInputRef.current;
    if (!input) return;
    input.focus();
    input.select();
  }, [renamingProfileId]);

  const activeProvider = form ? effectiveProvider(form) : "auto";
  const recipe = form
    ? getLocalInstallRecipe(activeProvider) || getLocalInstallRecipe(form.packageName)
    : null;
  const providerSelect = form ? providerSelectValue(form) : "";
  const showCustomSlug = Boolean(form && kind === "local" && providerSelect === "custom");

  function buildPayload() {
    if (!form) return null;
    const provider = effectiveProvider(form);
    if (kindRequiresNamedProvider(kind) && !nameProviderForTest(form)) {
      setError(null);
      setTestResult({
        ok: false,
        provider: "",
        detail: t("opsTtsAi.testNeedProvider")
      });
      return null;
    }
    if (form.providerChoice === "custom" && !/^[a-z][a-z0-9_\-]{0,62}$/.test(provider)) {
      setError(null);
      setTestResult({
        ok: false,
        provider: provider || "",
        detail: t("opsTtsAi.customProviderInvalid")
      });
      return null;
    }
    const timeout = Number(form.timeoutSeconds);
    const rate = Number(form.speakingRate);
    // Keep provider-specific options we do not own (for example future
    // adapter flags) while replacing only fields edited by this form.
    const options_json: Record<string, unknown> = { ...form.optionsJson };
    const existingExpressive =
      options_json.expressive_tts && typeof options_json.expressive_tts === "object"
        ? (options_json.expressive_tts as Record<string, unknown>)
        : {};
    options_json.expressive_tts = {
      ...existingExpressive,
      mode: ["off", "best_effort", "required"].includes(form.expressiveMode)
        ? form.expressiveMode
        : "best_effort",
      ...(isGeminiExpressiveProvider(provider)
        ? {
            synthesis_strategy: ["whole_video", "auto_blocks", "segment"].includes(
              form.synthesisStrategy
            )
              ? form.synthesisStrategy
              : "whole_video",
            single_voice_mode:
              form.synthesisStrategy === "segment" ? "off" : "required",
            max_whole_video_seconds: Math.max(
              30,
              Math.min(600, Number(form.maxWholeVideoSeconds) || 180)
            ),
            max_block_seconds: Math.max(
              15,
              Math.min(120, Number(form.maxBlockSeconds) || 45)
            ),
            compact_trigger_ratio: Math.max(
              0.65,
              Math.min(1, Number(form.compactTriggerRatio) || 0.88)
            ),
            max_concurrency: 1,
            regenerate_on_timing_mismatch: false,
            regenerate_on_emotion_mismatch: false
          }
        : {})
    };
    if (provider === "google_cloud_tts") {
      options_json.google_cloud_tts = {
        ...(
          options_json.google_cloud_tts && typeof options_json.google_cloud_tts === "object"
            ? (options_json.google_cloud_tts as Record<string, unknown>)
            : {}
        ),
        region: form.googleCloudRegion || "global"
      };
    }
    if (resolveTtsProviderKind(provider) === "local") {
      delete options_json.install_command;
      delete options_json.extra_requirement;
      delete options_json.package_name;
      delete options_json.repo_url;
      if (form.installCommand.trim()) options_json.install_command = form.installCommand.trim();
      if (form.extraRequirement.trim()) options_json.extra_requirement = form.extraRequirement.trim();
      if (form.packageName.trim()) options_json.package_name = form.packageName.trim();
      if (form.repoUrl.trim()) options_json.repo_url = form.repoUrl.trim();
      if (provider !== "vieneu") delete options_json.style;
      if (provider === "vieneu") options_json.style = form.style || "tu_nhien";
    }
    if (
      ["http", "cloud"].includes(resolveTtsProviderKind(provider)) &&
      provider !== "google" &&
      provider !== "google_cloud_tts"
    ) {
      delete options_json.http_connector;
      Object.assign(options_json, httpConnectorToOptions(form.httpConnector));
    }
    const payload: Parameters<typeof saveTtsAiProfile>[1] = {
      enabled: form.enabled,
      provider,
      voice_id: form.voiceId.trim(),
      speaking_rate: Number.isFinite(rate) && rate >= 0.5 && rate <= 2 ? rate : 1,
      language_code: form.languageCode.trim() || "vi",
      model_id: form.modelId.trim(),
      base_url: form.baseUrl.trim(),
      timeout_seconds: Number.isFinite(timeout) && timeout > 0 ? timeout : 120,
      fallback_provider: form.fallbackProvider.trim() || "none",
      fallback_voice_id: form.fallbackVoiceId.trim(),
      local_backend: form.localBackend.trim() || "auto",
      device: form.device.trim() || "auto",
      cli_binary: form.cliBinary.trim(),
      options_json,
    };
    if (form.apiKeyInput.trim()) {
      payload.api_key = form.apiKeyInput.trim();
    } else {
      payload.api_key = null;
    }
    if (provider === "google" || provider === "google_gemini") {
      payload.credential_mode = form.credentialMode || (provider === "google" ? "google_service_account" : "api_key");
      if (form.googleServiceAccountJson.trim()) {
        payload.google_service_account_json = form.googleServiceAccountJson;
      }
      if (form.clearGoogleServiceAccount) {
        payload.clear_google_service_account = true;
      }
    }
    return payload;
  }

  async function openEditor(profileId: string) {
    setProfileBusy(true);
    setError(null);
    try {
      const data = await fetchTtsAiProfile(profileId);
      applyResponse(data);
      setEditingProfileId(profileId);
      const named = (data.profiles || []).find((p) => p.id === profileId);
      setEditingProfileName(named?.name || "Setup");
      setViewMode("editor");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.loadError"));
    } finally {
      setProfileBusy(false);
    }
  }

  async function onSave() {
    const payload = buildPayload();
    if (!payload) return;
    setSaving(true);
    setError(null);
    try {
      let profileId = editingProfileId;
      const setupName = editingProfileName.trim() || nextBlankSetupName(profiles);
      if (!profileId) {
        const created = await createTtsAiProfile(setupName);
        profileId = created.focus_profile_id || null;
        if (!profileId) throw new Error(t("opsTtsAi.profileError"));
        setEditingProfileId(profileId);
        setEditingProfileName(setupName);
      } else {
        const currentName = profiles.find((p) => p.id === profileId)?.name || "";
        if (setupName && setupName !== currentName) {
          await renameTtsAiProfile(profileId, setupName);
          setEditingProfileName(setupName);
        }
      }
      await saveTtsAiProfile(profileId, payload);
      setForm((current) => current ? {
        ...current,
        googleServiceAccountJson: "",
        googleServiceAccountFileName: ""
      } : current);
      await loadList();
      notify({ id: "tts-settings-saved", message: t("opsTtsAi.saved"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.saveError"));
    } finally {
      setSaving(false);
    }
  }

  function onCreateProfile() {
    const name = nextBlankSetupName(profiles);
    setError(null);
    setEditingProfileId(null);
    setEditingProfileName(name);
    setForm(blankForm());
    setKind("system");
    setCatalog(null);
    setCatalogStale(false);
    setRuntime(null);
    setLiveImportOk(null);
    setTestResult(null);
    setInstallResult(null);
    setPreviewFeedback(null);
    setCurlImportDraft("");
    setCurlImportFeedback(null);
    setMeta({
      apiKeySet: false,
      apiKeyMasked: "",
      source: "env",
      googleServiceAccountSet: false,
      googleServiceAccountEmail: "",
      googleServiceAccountProjectId: ""
    });
    setViewMode("editor");
  }

  function startRenameProfile(profileId: string, currentName: string) {
    setRenamingProfileId(profileId);
    setRenameDraft(currentName);
    setError(null);
  }

  function cancelRenameProfile() {
    setRenamingProfileId(null);
    setRenameDraft("");
  }

  async function commitRenameProfile() {
    const profileId = renamingProfileId;
    if (!profileId) return;
    const name = renameDraft.trim();
    const current = profiles.find((p) => p.id === profileId)?.name || "";
    if (!name || name === current) {
      cancelRenameProfile();
      return;
    }
    setProfileBusy(true);
    setError(null);
    try {
      const data = await renameTtsAiProfile(profileId, name);
      applyListResponse(data);
      cancelRenameProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.profileError"));
    } finally {
      setProfileBusy(false);
    }
  }

  async function onSetActive(profileId: string, nextOn: boolean) {
    if (!profileId) return;
    // The On flag is production authority. Enabling one row atomically disables
    // all others; disabling is allowed for the visibly On row even when an old
    // active pointer is stale.
    setProfileBusy(true);
    setError(null);
    try {
      // Backend switches the active profile and disables every other setup in
      // this one request, so the worker can never observe an in-between state.
      if (!nextOn && !profiles.some((profile) => profile.id === profileId && profile.enabled)) return;
      applyListResponse(await setTtsAiProfileEnabled(profileId, nextOn));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.profileError"));
    } finally {
      setProfileBusy(false);
    }
  }

  async function onReorderProfiles(fromId: string, toId: string) {
    if (!fromId || !toId || fromId === toId || profileBusy) return;
    const from = profiles.findIndex((p) => p.id === fromId);
    const to = profiles.findIndex((p) => p.id === toId);
    if (from < 0 || to < 0) return;
    const next = moveItemIndex(profiles, from, to);
    const previous = profiles;
    setProfiles(next);
    setProfileBusy(true);
    setError(null);
    try {
      applyListResponse(await reorderTtsAiProfiles(profileIdsOf(next)));
    } catch (err) {
      setProfiles(previous);
      setError(err instanceof Error ? err.message : t("opsTtsAi.profileError"));
    } finally {
      setProfileBusy(false);
      setDragFromId(null);
      setDragOverId(null);
    }
  }

  async function onDeleteProfile(profileId: string, name: string) {
    if (profiles.length <= 1) {
      setError(t("opsTtsAi.profileLastError"));
      return;
    }
    if (!window.confirm(`${t("opsTtsAi.profileDeleteConfirm")} (${name})`)) return;
    setProfileBusy(true);
    setError(null);
    try {
      const data = await deleteTtsAiProfile(profileId);
      applyListResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.profileError"));
    } finally {
      setProfileBusy(false);
    }
  }

  async function onTest(probeMode: "connection" | "catalog" = "connection") {
    if (!form) return;
    if (kindRequiresNamedProvider(kind)) {
      const named = nameProviderForTest(form);
      if (!named || named === "custom") {
        setError(null);
        setTestResult({
          ok: false,
          provider: "",
          detail: t("opsTtsAi.testNeedProvider")
        });
        return;
      }
      const universalConnectorEnabled = Boolean(
        httpConnectorToOptions(form.httpConnector).http_connector
      );
      if (named === "google") {
        const mode = form.credentialMode || "google_service_account";
        const serviceAccountReady = Boolean(form.googleServiceAccountJson.trim()) ||
          (meta.googleServiceAccountSet && !form.clearGoogleServiceAccount);
        const oauthTokenReady = Boolean(form.apiKeyInput.trim()) || meta.apiKeySet;
        if (mode === "google_service_account" && !serviceAccountReady) {
          setError(null);
          setTestResult({ ok: false, provider: named, detail: t("opsTtsAi.googleServiceAccountRequired") });
          return;
        }
        if (mode === "google_oauth_token" && !oauthTokenReady) {
          setError(null);
          setTestResult({ ok: false, provider: named, detail: t("opsTtsAi.googleOauthTokenRequired") });
          return;
        }
      } else if (
        (kind === "cloud" && !universalConnectorEnabled) ||
        (universalConnectorEnabled && form.httpConnector.authType !== "none")
      ) {
        const hasKey = Boolean(form.apiKeyInput.trim()) || meta.apiKeySet;
        if (!hasKey) {
          setError(null);
          setTestResult({
            ok: false,
            provider: named,
            detail: t("opsTtsAi.testNeedApiKey")
          });
          return;
        }
      }
      if (named !== "google" && (kind === "http" || (kind === "cloud" && universalConnectorEnabled))) {
        if (!form.baseUrl.trim()) {
          setError(null);
          setTestResult({
            ok: false,
            provider: named,
            detail: t("opsTtsAi.testNeedBaseUrl")
          });
          return;
        }
      }
    }
    const payload = buildPayload();
    if (!payload) return;
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const result = await testTtsAi({
        ...payload,
        profile_id: editingProfileId || undefined,
        probe_mode: probeMode
      });
      setTestResult({
        ok: result.ok,
        provider: result.provider,
        detail: result.detail,
        checks: result.checks,
        config_fingerprint: result.config_fingerprint
      });
      if (result.ok) {
        notify({
          id: "tts-settings-test",
          message: t("opsTtsAi.testOk"),
          tone: "success"
        });
      }
      if (result.runtime) setRuntime(result.runtime);
      const nextCatalog = result.ok
        ? resolveTtsCatalogForProvider(result.provider || effectiveProvider(form), result.catalog || null)
        : catalog;
      if (form && result.ok) {
        setForm(applyCatalog(nextCatalog, form));
      } else if (!result.ok) {
        // Keep the last known catalog visible as stale context after a transient
        // probe failure; the operator can correct credentials and refresh again.
        setCatalogStale(Boolean(catalog));
      } else {
        setCatalog(nextCatalog);
        setCatalogStale(false);
      }
    } catch (err) {
      setTestResult({
        ok: false,
        provider: activeProvider,
        detail: err instanceof Error ? err.message : t("opsTtsAi.testError")
      });
    } finally {
      setTesting(false);
    }
  }

  function onKindChange(nextKind: TtsProviderKind) {
    if (!form) return;
    if (nextKind === kind) return;
    const list = TTS_PROVIDERS_BY_KIND[nextKind];
    const currentChoice = form.providerChoice === "custom" ? "custom" : form.provider;
    const staysInKind =
      (nextKind === "local" && (form.providerChoice === "custom" || isCustomLocalProvider(form.provider))) ||
      list.includes(currentChoice as (typeof list)[number]);
    setKind(nextKind);
    setTestResult(null);
    setCatalog(null);
    setCatalogStale(false);
    setInstallResult(null);
    setPreviewFeedback(null);
    if (!editingProfileId && nextKind === "local") {
      setForm({
        ...form,
        provider: "",
        providerChoice: "",
        customProviderSlug: ""
      });
      return;
    }
    if (staysInKind) return;
    applyProvider(defaultProviderForKind(nextKind), form);
  }

  function applyProvider(next: string, base: FormState) {
    const isCustom = next === "custom" || isCustomLocalProvider(next);
    const patch: FormState = {
      ...base,
      provider: isCustom ? base.customProviderSlug || next : next,
      providerChoice: isCustom ? "custom" : next,
      customProviderSlug: isCustom ? (next === "custom" ? base.customProviderSlug : next) : ""
    };
    const recipeKey = isCustom
      ? patch.customProviderSlug || patch.packageName || next
      : next;
    const nextRecipe = getLocalInstallRecipe(recipeKey);
    // Identity only: never copy recipe install/voice/package defaults into the draft form.
    if (nextRecipe?.providerSlug && isCustom) {
      patch.customProviderSlug = nextRecipe.providerSlug;
      patch.provider = nextRecipe.providerSlug;
    } else if (isCustom) {
      if (looksLikeEdgeVoiceId(patch.voiceId) && !isPresetLocalProvider(effectiveProvider(patch))) {
        patch.voiceId = "";
      }
    }
    if (next === "google") {
      patch.credentialMode = GOOGLE_CREDENTIAL_MODES.includes(
        patch.credentialMode as (typeof GOOGLE_CREDENTIAL_MODES)[number]
      )
        ? patch.credentialMode
        : "google_service_account";
      if (!patch.baseUrl.trim()) patch.baseUrl = "https://texttospeech.googleapis.com/v1";
    } else if (next === "google_gemini") {
      patch.credentialMode = "api_key";
      if (!patch.baseUrl.trim()) patch.baseUrl = "https://generativelanguage.googleapis.com/v1beta";
      if (!patch.modelId.trim()) patch.modelId = "gemini-2.5-flash-preview-tts";
      patch.voiceId = canonicalizeGeminiVoiceId(patch.voiceId) || "Kore";
      patch.expressiveMode = "required";
      patch.synthesisStrategy = "whole_video";
      patch.maxWholeVideoSeconds = "180";
      patch.maxBlockSeconds = "45";
      patch.compactTriggerRatio = "0.88";
    } else if (next === "google_cloud_tts") {
      patch.credentialMode = "api_key";
      patch.baseUrl = "";
      patch.modelId = "gemini-2.5-flash-tts";
      patch.voiceId = canonicalizeGeminiVoiceId(patch.voiceId) || "Achernar";
      patch.languageCode = "vi-VN";
      patch.googleCloudRegion = "global";
      patch.expressiveMode = "required";
      patch.synthesisStrategy = "whole_video";
      patch.maxWholeVideoSeconds = "180";
      patch.maxBlockSeconds = "45";
      patch.compactTriggerRatio = "0.88";
    } else if (base.provider === "google" || base.provider === "google_gemini") {
      patch.googleServiceAccountJson = "";
      patch.googleServiceAccountFileName = "";
      patch.clearGoogleServiceAccount = false;
    }
    patch.provider = effectiveProvider(patch);
    setForm(patch);
    setKind(isCustom || patch.providerChoice === "custom" ? "local" : resolveTtsProviderKind(patch.provider));
    setTestResult(null);
    setCatalog(null);
    setCatalogStale(false);
    setInstallResult(null);
    setPreviewFeedback(null);
  }

  function onProviderSelect(next: string) {
    if (!form) return;
    if (next === "custom") {
      setForm({
        ...form,
        providerChoice: "custom",
        customProviderSlug: form.customProviderSlug,
        provider: form.customProviderSlug.trim().toLowerCase()
      });
      setKind("local");
      setTestResult(null);
      setCatalog(null);
      setCatalogStale(false);
      setInstallResult(null);
      setPreviewFeedback(null);
      return;
    }
    applyProvider(next, form);
  }

  function onCustomSlugInput(raw: string) {
    if (!form) return;
    const normalized = raw.trim().toLowerCase();
    setForm({
      ...form,
      providerChoice: "custom",
      customProviderSlug: normalized,
      provider: normalized
    });
    setTestResult(null);
    setCatalog(null);
    setCatalogStale(false);
    setInstallResult(null);
    setPreviewFeedback(null);
  }

  function onRemoteCredentialChange(field: "baseUrl" | "apiKeyInput", value: string) {
    if (!form) return;
    setForm({ ...form, [field]: value });
    // A catalog is tied to the exact endpoint/key pair. Keep it visible as context,
    // but mark it stale until the operator refreshes with the new credentials.
    if (isCloud || isHttp) {
      setCatalogStale(Boolean(catalog || runtime?.last_probe));
      setTestResult(null);
      setPreviewAudioUrl(null);
      setPreviewMeta(null);
      setPreviewFeedback(null);
    }
  }

  async function onGoogleServiceAccountFile(file: File | undefined) {
    if (!file || !form) return;
    setError(null);
    if (file.size > GOOGLE_SERVICE_ACCOUNT_MAX_BYTES) {
      setError(t("opsTtsAi.googleServiceAccountTooLarge"));
      return;
    }
    try {
      const raw = await file.text();
      if (new TextEncoder().encode(raw).byteLength > GOOGLE_SERVICE_ACCOUNT_MAX_BYTES) {
        setError(t("opsTtsAi.googleServiceAccountTooLarge"));
        return;
      }
      if (!googleServiceAccountMetadata(raw)) {
        setError(t("opsTtsAi.googleServiceAccountInvalid"));
        return;
      }
      setForm({
        ...form,
        googleServiceAccountJson: raw,
        googleServiceAccountFileName: file.name,
        clearGoogleServiceAccount: false
      });
      setCatalogStale(Boolean(catalog || runtime?.last_probe));
      setTestResult(null);
    } catch {
      setError(t("opsTtsAi.googleServiceAccountReadError"));
    }
  }

  function onGoogleCredentialModeChange(credentialMode: string) {
    if (!form) return;
    setForm({ ...form, credentialMode, apiKeyInput: credentialMode === "google_oauth_token" ? form.apiKeyInput : "" });
    setCatalogStale(Boolean(catalog || runtime?.last_probe));
    setTestResult(null);
    setPreviewAudioUrl(null);
    setPreviewMeta(null);
    setPreviewFeedback(null);
  }

  function clearGoogleServiceAccount() {
    if (!form) return;
    setForm({
      ...form,
      googleServiceAccountJson: "",
      googleServiceAccountFileName: "",
      clearGoogleServiceAccount: true
    });
    setCatalogStale(Boolean(catalog || runtime?.last_probe));
    setTestResult(null);
  }

  function updateHttpConnector(patch: Partial<HttpConnectorFormState>) {
    if (!form) return;
    setForm({ ...form, httpConnector: { ...form.httpConnector, ...patch } });
    if (isHttp || isCloud) {
      setCatalogStale(Boolean(catalog || runtime?.last_probe));
      setTestResult(null);
      setPreviewAudioUrl(null);
      setPreviewMeta(null);
      setPreviewFeedback(null);
    }
  }

  function updateHttpAuth(patch: Partial<Pick<
    HttpConnectorFormState,
    "authType" | "authHeader" | "authPrefix" | "authQueryName" | "authTestPath" | "authTestMethod"
  >>) {
    updateHttpConnector(patch);
  }

  function updateHttpCatalogEndpoint(
    key: "models" | "voices" | "languages",
    patch: Partial<HttpConnectorEndpoint>
  ) {
    if (!form) return;
    updateHttpConnector({
      catalog: {
        ...form.httpConnector.catalog,
        [key]: { ...form.httpConnector.catalog[key], ...patch }
      }
    });
  }

  function importHttpCurl() {
    const imported = parseTtsCurl(curlImportDraft);
    if (!imported) {
      setCurlImportFeedback({ ok: false, message: t("opsTtsAi.httpCurlInvalid") });
      return;
    }
    if (!form) return;
    setForm({
      ...form,
      baseUrl: imported.baseUrl,
      httpConnector: {
        ...form.httpConnector,
        mode: "custom",
        authType: imported.authType,
        authHeader: imported.authHeader,
        authPrefix: imported.authPrefix,
        authQueryName: imported.authQueryName,
        synthesisPath: imported.synthesisPath,
        synthesisMethod: imported.method,
        synthesisContentType: imported.contentType,
        synthesisBody: imported.body || form.httpConnector.synthesisBody
      }
    });
    setCurlImportFeedback({
      ok: true,
      message: imported.keyDetected
        ? t("opsTtsAi.httpCurlCredentialsRemoved")
        : t("opsTtsAi.httpCurlImported")
    });
    setCurlImportDraft("");
    setCatalogStale(Boolean(catalog || runtime?.last_probe));
    setTestResult(null);
    setPreviewAudioUrl(null);
    setPreviewMeta(null);
    setPreviewFeedback(null);
  }

  function applyLucylabPreset() {
    if (!form) return;
    setForm({
      ...form,
      baseUrl: "https://api.lucylab.io",
      provider: "http_custom",
      providerChoice: "http_custom",
      customProviderSlug: "",
      httpConnector: {
        ...form.httpConnector,
        ...lucylabJsonRpcPreset()
      }
    });
    setCatalogStale(Boolean(catalog || runtime?.last_probe));
    setTestResult(null);
    setPreviewAudioUrl(null);
    setPreviewMeta(null);
    setPreviewFeedback(null);
  }

  async function copyInstallCommand() {
    if (!form?.installCommand.trim()) return;
    try {
      await navigator.clipboard.writeText(form.installCommand.trim());
      setCopied(true);
    } catch {
      setError(t("opsTtsAi.copyFailed"));
    }
  }

  function applyRepoUrl(nextRepo: string) {
    if (!form) return;
    const derived = deriveTtsInstallFromRepoUrl(nextRepo);
    if (!derived) {
      setForm({ ...form, repoUrl: nextRepo });
      return;
    }
    const recipe = getLocalInstallRecipe(derived.packageName);
    const slug = resolveProviderSlugFromInstall(derived.packageName, nextRepo);
    const next: FormState = {
      ...form,
      repoUrl: nextRepo,
      installCommand: derived.installCommand,
      packageName: derived.packageName
    };
    if (slug) {
      const isPreset = isPresetLocalProvider(slug);
      next.providerChoice = isPreset ? slug : "custom";
      next.customProviderSlug = isPreset ? "" : slug;
      next.provider = slug;
      setKind("local");
    }
    if (recipe) {
      if (recipe.defaultLanguage) next.languageCode = recipe.defaultLanguage;
      if (recipe.defaultModel) next.modelId = recipe.defaultModel;
      next.voiceId = recipe.defaultVoice;
      if (recipe.extraRequirement) next.extraRequirement = recipe.extraRequirement;
    } else if (looksLikeEdgeVoiceId(next.voiceId)) {
      next.voiceId = "";
    }
    setForm(next);
  }

  function applyInstallFinished(result: TtsAiInstallResponse, workingForm: FormState) {
    setInstallResult({
      ok: result.ok,
      detail: result.detail,
      command: result.command,
      log_tail: result.log_tail,
      already_satisfied: Boolean(result.already_satisfied)
    });
    if (result.runtime) setRuntime(result.runtime);
    if (result.ok) {
      notify({
        id: "tts-install-finished",
        message: result.already_satisfied ? t("opsTtsAi.installAlready") : t("opsTtsAi.installOk"),
        tone: "success"
      });
      if (typeof result.probe_ok === "boolean") {
        setTestResult({
          ok: result.probe_ok,
          provider: result.provider || effectiveProvider(workingForm),
          detail: result.probe_detail || ""
        });
        setLiveImportOk(result.probe_ok);
      }
      let nextForm = { ...workingForm };
      if (result.command) {
        nextForm.installCommand = result.command;
      }
      const packageName =
        workingForm.packageName.trim() ||
        result.runtime?.last_install?.package ||
        deriveTtsInstallFromRepoUrl(workingForm.repoUrl)?.packageName ||
        "";
      const slug = resolveProviderSlugFromInstall(packageName, workingForm.repoUrl);
      const recipe = getLocalInstallRecipe(slug || packageName);
      if (slug) {
        const isPreset = isPresetLocalProvider(slug);
        nextForm.providerChoice = isPreset ? slug : "custom";
        nextForm.customProviderSlug = isPreset ? "" : slug;
        nextForm.provider = slug;
        setKind("local");
      }
      if (recipe) {
        if (recipe.defaultLanguage) nextForm.languageCode = recipe.defaultLanguage;
        if (recipe.defaultModel) nextForm.modelId = recipe.defaultModel;
        nextForm.voiceId = recipe.defaultVoice;
        if (recipe.packageName && !nextForm.packageName.trim()) {
          nextForm.packageName = recipe.packageName;
        }
      } else if (slug && looksLikeEdgeVoiceId(nextForm.voiceId)) {
        nextForm.voiceId = "";
      }
      const apiCatalog = result.catalog;
      const apiCatalogHasChoices = Boolean(apiCatalog?.voices?.length || apiCatalog?.models?.length);
      const isOmnivoice = slug === "omnivoice" || packageName.toLowerCase().includes("omnivoice");
      const nextCatalog =
        apiCatalogHasChoices || isOmnivoice
          ? apiCatalog ?? null
          : slug
            ? ({
                source: "curated",
                voices: [],
                styles: [],
                models: recipe?.defaultModel ? [recipe.defaultModel] : [],
                default_voice_id: "",
                warning: "",
                capabilities: getTtsFieldCapabilities(slug || "custom")
              } satisfies TtsAiCatalog)
            : null;
      const resolvedCatalog = resolveTtsCatalogForProvider(effectiveProvider(nextForm), nextCatalog ?? null);
      setForm(applyCatalog(resolvedCatalog, nextForm));
    }
  }

  async function onRefreshCatalog() {
    if (catalogRefreshPhase !== "idle") return;
    setCatalogRefreshPhase("preparing");
    await new Promise<void>((resolve) => {
      catalogPreloadTimerRef.current = setTimeout(() => {
        catalogPreloadTimerRef.current = null;
        resolve();
      }, 250);
    });
    setCatalogRefreshPhase("loading");
    try {
      await onTest("catalog");
    } finally {
      setCatalogRefreshPhase("idle");
    }
  }

  async function waitInstallPollDelay(ms: number) {
    await new Promise<void>((resolve) => {
      installPollTimerRef.current = setTimeout(() => {
        installPollTimerRef.current = null;
        resolve();
      }, ms);
    });
  }

  async function pollInstallUntilDone(workingForm: FormState): Promise<TtsAiInstallResponse | null> {
    const maxAttempts = 180;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      if (installPollCancelledRef.current) return null;
      await waitInstallPollDelay(2000);
      if (installPollCancelledRef.current) return null;
      const status = await fetchTtsAiInstallStatus();
      if (status.status === "running") {
        setInstallResult({
          ok: false,
          detail: status.detail || t("opsTtsAi.installing"),
          command: status.command || "",
          log_tail: status.log_tail || "",
          already_satisfied: false
        });
        continue;
      }
      applyInstallFinished(status, workingForm);
      return status;
    }
    setInstallResult({
      ok: false,
      detail: t("opsTtsAi.installPollTimeout"),
      command: workingForm.installCommand,
      log_tail: "",
      already_satisfied: false
    });
    return null;
  }

  async function onInstall(options?: { forceReinstall?: boolean }) {
    if (!form) return;
    const forceReinstall = Boolean(options?.forceReinstall);
    installPollCancelledRef.current = false;
    setInstalling(true);
    setError(null);
    setInstallResult(null);
    let plannedCommand = "";
    try {
      const repo = form.repoUrl.trim();
      const derived = repo ? deriveTtsInstallFromRepoUrl(repo) : null;
      const rawCmd = form.installCommand.trim();
      const cmdIsGit = /^pip\s+install\s+git\+/i.test(rawCmd);
      // Prefer repo-derived git+ command when a repo URL is present so stale PyPI
      // commands like ``pip install OmniVoice-Studio`` / edge-tts do not win.
      const installCommand = derived
        ? cmdIsGit
          ? rawCmd
          : derived.installCommand
        : rawCmd || null;
      plannedCommand = installCommand || "";
      let workingForm = form;
      if (derived) {
        workingForm = {
          ...form,
          installCommand: installCommand || derived.installCommand,
          packageName: derived.packageName
        };
        setForm(workingForm);
      }
      const result = await installTtsAiPackage({
        install_command: installCommand,
        package: workingForm.packageName.trim() || null,
        repo_url: repo || null,
        timeout_seconds: 900,
        provider: effectiveProvider(workingForm),
        profile_id: editingProfileId || undefined,
        force_reinstall: forceReinstall
      });
      if (result.status === "running") {
        setInstallResult({
          ok: false,
          detail: result.detail || t("opsTtsAi.installing"),
          command: result.command || plannedCommand,
          log_tail: "",
          already_satisfied: false
        });
        await pollInstallUntilDone(workingForm);
      } else {
        applyInstallFinished(result, workingForm);
      }
    } catch (err) {
      setInstallResult({
        ok: false,
        detail: err instanceof Error ? err.message : t("opsTtsAi.installError"),
        command: plannedCommand,
        log_tail: "",
        already_satisfied: false
      });
    } finally {
      setInstalling(false);
    }
  }

  function applyEngineInstallJob(result: TtsAiEngineInstallJobResponse) {
    setEngineInstallJob(result);
    const succeeded = result.status === "succeeded" || result.status === "already_installed";
    setInstallResult({
      ok: succeeded,
      detail: result.detail,
      command: "",
      log_tail: result.log_tail,
      already_satisfied: result.status === "already_installed"
    });
    if (succeeded) {
      notify({
        id: "tts-engine-install-finished",
        message:
          result.status === "already_installed"
            ? t("opsTtsAi.engineAlreadyInstalled")
            : t("opsTtsAi.engineInstallOk"),
        tone: "success"
      });
    }
  }

  async function pollEngineInstallUntilDone(): Promise<void> {
    const maxAttempts = 3600;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      if (installPollCancelledRef.current) return;
      await waitInstallPollDelay(2000);
      if (installPollCancelledRef.current) return;
      const status = await fetchTtsAiEngineInstallStatus();
      applyEngineInstallJob(status);
      if (status.status === "running") {
        continue;
      }
      return;
    }
    setInstallResult({
      ok: false,
      detail: t("opsTtsAi.installPollTimeout"),
      command: "",
      log_tail: "",
      already_satisfied: false
    });
  }

  async function reattachEngineInstallJob(): Promise<void> {
    try {
      const status = await fetchTtsAiEngineInstallStatus();
      setEngineInstallJob(status);
      if (status.status !== "running") return;
      setEngineInstallingId(status.engine_id);
      setInstalling(true);
      await pollEngineInstallUntilDone();
      await loadOmnivoiceEngines();
    } catch {
      // A missing status is expected before the first engine install.
    } finally {
      setEngineInstallingId(null);
      setInstalling(false);
    }
  }

  async function onInstallEngine(engine: TtsAiEngineOption) {
    if (!form || !engine.installable) return;
    installPollCancelledRef.current = false;
    setEngineInstallingId(engine.id);
    setInstalling(true);
    setInstallResult(null);
    setEngineInstallJob(null);
    setError(null);
    try {
      const result = await installTtsAiEngine(engine.id, {
        profile_id: editingProfileId || undefined
      });
      applyEngineInstallJob(result);
      if (result.status === "running" || result.status === "already_running") {
        await pollEngineInstallUntilDone();
      }
      await loadOmnivoiceEngines();
    } catch (err) {
      setInstallResult({
        ok: false,
        detail: err instanceof Error ? err.message : t("opsTtsAi.engineInstallError"),
        command: engine.install_command || "",
        log_tail: "",
        already_satisfied: false
      });
    } finally {
      setEngineInstallingId(null);
      setInstalling(false);
    }
  }

  function friendlyPreviewFailure(raw: string): string {
    const message = (raw || "").trim();
    if (isLucylabJsonRpc && /missing_job_id/i.test(message)) {
      return t("opsTtsAi.httpLucylabPreviewMissingJob");
    }
    if (/cloud TTS adapter is not enabled|settings are saved, but the cloud TTS adapter/i.test(message)) {
      return t("opsTtsAi.previewCloudUnavailable");
    }
    if (/google_cloud_http_404[\s\S]*publisher model|publisher model[\s\S]*not found/i.test(message)) {
      return t("opsTtsAi.previewGoogleModelUnavailable");
    }
    if (/requires an API key|api[_ -]?key/i.test(message)) {
      return t("opsTtsAi.previewNeedApiKey");
    }
    if (/base URL/i.test(message)) {
      return t("opsTtsAi.previewNeedBaseUrl");
    }
    if (/adapter.+not enabled|known adapter|synthesis adapter/i.test(message)) {
      return t("opsTtsAi.previewAdapterUnavailable");
    }
    return message || t("opsTtsAi.previewError");
  }

  function showPreviewFailure(message: string) {
    setError(null);
    setPreviewMeta(null);
    setPreviewFeedback(friendlyPreviewFailure(message));
  }

  function previewValidationMessage(sample: string): string {
    if (!sample) return t("opsTtsAi.previewEmpty");
    if (!form) return t("opsTtsAi.previewConfigurationIncomplete");
    const provider = nameProviderForTest(form);
    if (kindRequiresNamedProvider(kind) && !provider) return t("opsTtsAi.previewNeedProvider");
    if (form.providerChoice === "custom" && !/^[a-z][a-z0-9_\-]{0,62}$/.test(provider)) {
      return t("opsTtsAi.customProviderInvalid");
    }
    const genericSynthesisConfigured =
      form.httpConnector.mode !== "auto" && Boolean(form.httpConnector.synthesisPath.trim());
    const googleCredentialMode =
      form.credentialMode || (provider === "google" ? "google_service_account" : "api_key");
    const usesGoogleCloudCredentials =
      provider === "google" || (provider === "google_gemini" && googleCredentialMode !== "api_key");
    if (usesGoogleCloudCredentials) {
      const mode = googleCredentialMode;
      if (
        mode === "google_service_account" &&
        !form.googleServiceAccountJson.trim() &&
        (!meta.googleServiceAccountSet || form.clearGoogleServiceAccount)
      ) {
        return t("opsTtsAi.googleServiceAccountRequired");
      }
      if (mode === "google_oauth_token" && !form.apiKeyInput.trim() && !meta.apiKeySet) {
        return t("opsTtsAi.googleOauthTokenRequired");
      }
    }
    if (
      provider === "google_gemini" &&
      googleCredentialMode === "api_key" &&
      !form.apiKeyInput.trim() &&
      !meta.apiKeySet
    ) {
      return t("opsTtsAi.previewNeedApiKey");
    }
    if (
      !usesGoogleCloudCredentials &&
      genericSynthesisConfigured &&
      form.httpConnector.authType !== "none" &&
      !form.apiKeyInput.trim() &&
      !meta.apiKeySet
    ) {
      return t("opsTtsAi.previewNeedApiKey");
    }
    if (
      kind === "cloud" &&
      !supportsDirectCloudPreview(provider) &&
      !genericSynthesisConfigured &&
      !["edge", "vieneu"].includes(form.fallbackProvider || "")
    ) {
      return t("opsTtsAi.previewCloudUnavailable");
    }
    if (provider !== "google" && (kind === "http" || genericSynthesisConfigured) && !form.baseUrl.trim()) {
      return t("opsTtsAi.previewNeedBaseUrl");
    }
    return "";
  }

  async function onPreview() {
    const sample = previewText.trim();
    const validationMessage = previewValidationMessage(sample);
    if (validationMessage) {
      showPreviewFailure(validationMessage);
      return;
    }
    const payload = buildPayload();
    if (!payload) {
      showPreviewFailure(t("opsTtsAi.previewConfigurationIncomplete"));
      return;
    }
    previewPollCancelledRef.current = false;
    setPreviewing(true);
    setError(null);
    setPreviewFeedback(null);
    setPreviewMeta(null);
    setPreviewAudioUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    try {
      const started = await previewTtsAiSpeech({
        ...payload,
        text: sample,
        max_chars: 280,
        profile_id: editingProfileId || undefined
      });
      if (started.status === "running") {
        setPreviewMeta({
          provider: started.provider || payload.provider || "tts",
          duration: 0,
          detail: t("opsTtsAi.previewing"),
          requestedVoiceId: started.requested_voice_id || payload.voice_id || "",
          resolvedVoiceId: started.resolved_voice_id || "",
          requestedModelId: started.requested_model_id || payload.model_id || "",
          resolvedModelId: started.resolved_model_id || ""
        });
        const maxAttempts = 300;
        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
          if (previewPollCancelledRef.current) return;
          await new Promise<void>((resolve) => {
            previewPollTimerRef.current = setTimeout(() => {
              previewPollTimerRef.current = null;
              resolve();
            }, 2000);
          });
          if (previewPollCancelledRef.current) return;
          const status = await fetchTtsAiPreviewStatus();
          if (status.status === "running") {
            setPreviewMeta({
              provider: status.provider || payload.provider || "tts",
              duration: 0,
              detail: t("opsTtsAi.previewing"),
              requestedVoiceId: status.requested_voice_id || payload.voice_id || "",
              resolvedVoiceId: status.resolved_voice_id || "",
              requestedModelId: status.requested_model_id || payload.model_id || "",
              resolvedModelId: status.resolved_model_id || ""
            });
            continue;
          }
          if (!status.ok || status.status === "failed" || status.status === "cancelled") {
            if (status.status === "cancelled") {
              setPreviewMeta(null);
              setPreviewFeedback(null);
              setError(null);
              return;
            }
            showPreviewFailure(status.detail || t("opsTtsAi.previewError"));
            return;
          }
          if (!status.audio_base64) {
            showPreviewFailure(t("opsTtsAi.previewError"));
            return;
          }
          const binary = Uint8Array.from(atob(status.audio_base64), (c) => c.charCodeAt(0));
          const blob = new Blob([binary], { type: status.mime_type || "audio/wav" });
          const url = URL.createObjectURL(blob);
          setPreviewAudioUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return url;
          });
          setPreviewMeta({
            provider: status.provider,
            duration: status.duration_seconds,
            detail: status.detail,
            requestedVoiceId: status.requested_voice_id || payload.voice_id || "",
            resolvedVoiceId: status.resolved_voice_id || "",
            requestedModelId: status.requested_model_id || payload.model_id || "",
            resolvedModelId: status.resolved_model_id || ""
          });
          notify({ id: "tts-preview-finished", message: status.detail || t("opsTtsAi.preview"), tone: "success" });
          return;
        }
        showPreviewFailure(t("opsTtsAi.previewPollTimeout"));
        try {
          await cancelTtsAiPreview();
        } catch {
          // Best-effort unlock so the next Preview is not blocked.
        }
        return;
      }
      if (!started.ok || !started.audio_base64) {
        showPreviewFailure(started.detail || t("opsTtsAi.previewError"));
        return;
      }
      const binary = Uint8Array.from(atob(started.audio_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([binary], { type: started.mime_type || "audio/wav" });
      const url = URL.createObjectURL(blob);
      setPreviewAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setPreviewMeta({
        provider: started.provider,
        duration: started.duration_seconds,
        detail: started.detail,
        requestedVoiceId: started.requested_voice_id || payload.voice_id || "",
        resolvedVoiceId: started.resolved_voice_id || "",
        requestedModelId: started.requested_model_id || payload.model_id || "",
        resolvedModelId: started.resolved_model_id || ""
      });
      notify({ id: "tts-preview-finished", message: started.detail || t("opsTtsAi.preview"), tone: "success" });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("opsTtsAi.previewError");
      // Older API builds returned 409 for a stuck lock — cancel once so the next click works.
      if (/already running/i.test(message)) {
        try {
          await cancelTtsAiPreview();
          showPreviewFailure(t("opsTtsAi.previewUnlockedRetry"));
        } catch {
          showPreviewFailure(message);
        }
        return;
      }
      showPreviewFailure(message);
    } finally {
      setPreviewing(false);
    }
  }

  async function onCancelPreview() {
    previewPollCancelledRef.current = true;
    if (previewPollTimerRef.current) {
      clearTimeout(previewPollTimerRef.current);
      previewPollTimerRef.current = null;
    }
    try {
      await cancelTtsAiPreview();
      setError(null);
      setPreviewFeedback(null);
      setPreviewMeta(null);
      notify({ id: "tts-preview-cancelled", message: t("opsTtsAi.previewCancel"), tone: "info" });
    } catch (err) {
      showPreviewFailure(err instanceof Error ? err.message : t("opsTtsAi.previewCancelError"));
    } finally {
      setPreviewing(false);
    }
  }

  if (loading && profiles.length === 0 && viewMode === "list") {
    return (
      <OpsConsoleShell
        actions={
          <TopbarRefreshButton busy={refreshing} disabled={refreshing} onClick={() => void onRefresh()} />
        }
        description={t("nav.ttsSettingsDesc")}
        title={t("nav.ttsSettings")}
      >
        <AsyncContentBoundary status="loading" skeletonVariant="list" loadingLabel={t("opsTtsAi.loadingDetail")}>
          {null}
        </AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  const refreshAction = (
    <TopbarRefreshButton
      busy={refreshing}
      disabled={refreshing || profileBusy || saving || testing || installing || previewing}
      onClick={() => void onRefresh()}
    />
  );

  if (viewMode === "list") {
    const activeOnProfile = profiles.find((profile) => Boolean(profile.enabled));
    return (
      <OpsConsoleShell
        actions={refreshAction}
        description={t("nav.ttsSettingsDesc")}
        title={t("nav.ttsSettings")}
      >
      <main className="ops-page ops-page--settings ops-tts-page ops-ai-page is-compact ops-ai-control-center is-tts">
        {error ? <div className="inline-error">{error}</div> : null}
        <div className="ops-tts-list-header">
          <div className="ops-ai-registry-leading">
            <span aria-hidden="true" className="ops-ai-registry-icon">
              <svg fill="none" viewBox="0 0 24 24"><path d="M8 5v8a4 4 0 0 0 8 0V5" /><path d="M5 12v1a7 7 0 0 0 14 0v-1M12 20v2" /></svg>
            </span>
            <span><strong>{t("opsTtsAi.sectionProfiles")}</strong><small>{t("nav.ttsSettingsDesc")}</small></span>
          </div>
          <div className="ops-tts-list-toolbar">
            <div className="ops-tts-list-toolbar__cluster" aria-label={t("opsTtsAi.sectionProfiles")}>
              {activeOnProfile ? (
                <>
                  <span className="ops-tts-list-toolbar__active" title={t("opsTtsAi.profileActiveHint")}>
                    <span className="ops-tts-list-toolbar__dot" aria-hidden="true" />
                    <span className="ops-tts-list-toolbar__active-label">{t("opsTtsAi.profileActive")}</span>
                    <strong>{activeOnProfile.name}</strong>
                  </span>
                  <span className="ops-tts-list-toolbar__divider" aria-hidden="true" />
                </>
              ) : null}
              <span className="ops-tts-list-toolbar__count">
                <strong>{profiles.length}</strong>
                <span>{t("opsTtsAi.profileSetupsCount")}</span>
              </span>
              <button
                type="button"
                className="ops-tts-list-toolbar__new"
                onClick={() => onCreateProfile()}
                disabled={profileBusy}
                aria-label={t("opsTtsAi.profileNew")}
                title={t("opsTtsAi.profileNew")}
              >
                <TtsSetupActionIcon kind="add" />
                <span>{t("opsTtsAi.profileNew")}</span>
              </button>
            </div>
          </div>
        </div>
        {profiles.length === 0 ? (
          <p className="ops-tts-empty">{t("opsTtsAi.profileEmpty")}</p>
        ) : (
          <div className="ops-tts-setup-table-wrap">
            <table className="ops-tts-setup-table ops-ai-registry-table is-tts">
              <colgroup>
                <col className="ops-ai-col-drag" />
                <col className="ops-ai-col-setup" />
                <col className="ops-ai-col-voice" />
                <col className="ops-ai-col-speech" />
                <col className="ops-ai-col-status" />
                <col className="ops-ai-col-actions" />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className="ops-tts-setup-table__drag-col">
                    <span className="visually-hidden">{t("common.dragToReorder")}</span>
                  </th>
                  <th scope="col">{t("opsTtsAi.profileNameCol")}</th>
                  <th scope="col">{t("opsTtsAi.voiceRuntimeCol")}</th>
                  <th scope="col">{t("opsTtsAi.speechRuntimeCol")}</th>
                  <th scope="col">{t("opsTtsAi.statusControlCol")}</th>
                  <th scope="col">{t("opsTtsAi.profileActionsCol")}</th>
                </tr>
              </thead>
              <tbody>
                  {profiles.map((profile) => {
                  const isOn = Boolean(profile.enabled);
                  const hasFallback = Boolean(
                    profile.fallback_provider?.trim() && profile.fallback_provider.trim().toLowerCase() !== "none"
                  );
                  const profileCredentialReady = profile.provider === "google"
                    ? profile.credential_mode === "google_adc" ||
                      (profile.credential_mode === "google_service_account" && profile.google_service_account_set) ||
                      (profile.credential_mode === "google_oauth_token" && profile.api_key_set)
                    : profile.api_key_set;
                  const rowReady = resolveTtsReadyState({
                    test: profile.runtime?.last_probe
                      ? {
                          ok: Boolean(profile.runtime.last_probe.ok),
                          detail: profile.runtime.last_probe.detail || ""
                        }
                      : null,
                    install: profile.runtime?.last_install
                      ? {
                          ok: Boolean(profile.runtime.last_install.ok),
                          detail: profile.runtime.last_install.detail || ""
                        }
                      : null,
                    runtime: profile.runtime || null,
                    liveImportOk: null
                  });
                  const canDrag = !profileBusy && renamingProfileId !== profile.id;
                  const rowClass = [
                    isOn ? "is-active" : "",
                    canDrag ? "is-draggable" : "",
                    dragFromId === profile.id ? "is-dragging" : "",
                    dragOverId === profile.id && dragFromId !== profile.id ? "is-drag-over" : ""
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <tr
                      key={profile.id}
                      className={rowClass || undefined}
                      draggable={canDrag}
                      title={canDrag ? t("common.dragToReorder") : undefined}
                      onDragStart={(event) => {
                        if (!canDrag || isSetupTableInteractiveDragTarget(event.target)) {
                          event.preventDefault();
                          return;
                        }
                        setDragFromId(profile.id);
                        setDragOverId(profile.id);
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/plain", profile.id);
                      }}
                      onDragEnd={() => {
                        setDragFromId(null);
                        setDragOverId(null);
                      }}
                      onDragOver={(event) => {
                        if (!dragFromId || profileBusy) return;
                        event.preventDefault();
                        if (dragOverId !== profile.id) setDragOverId(profile.id);
                      }}
                      onDrop={(event) => {
                        event.preventDefault();
                        const fromId = dragFromId || event.dataTransfer.getData("text/plain");
                        void onReorderProfiles(fromId, profile.id);
                      }}
                    >
                      <td className="ops-tts-setup-table__drag">
                        <span className="ops-tts-setup-table__drag-handle" aria-hidden="true">
                          ⋮⋮
                        </span>
                      </td>
                      <td className="ops-tts-setup-table__name">
                        <div className="ops-ai-setup-identity">
                          {renamingProfileId === profile.id ? (
                            <input
                              ref={renameInputRef}
                              className="ops-tts-setup-table__rename-input"
                              type="text"
                              value={renameDraft}
                              maxLength={80}
                              disabled={profileBusy}
                              aria-label={t("opsTtsAi.profileRename")}
                              onChange={(e) => setRenameDraft(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  void commitRenameProfile();
                                } else if (e.key === "Escape") {
                                  e.preventDefault();
                                  cancelRenameProfile();
                                }
                              }}
                              onBlur={() => {
                                if (!profileBusy) void commitRenameProfile();
                              }}
                            />
                          ) : (
                            <button
                              type="button"
                              className="ops-tts-setup-table__name-btn"
                              disabled={profileBusy}
                              title={t("opsTtsAi.profileRenameHint")}
                              onClick={() => startRenameProfile(profile.id, profile.name)}
                            >
                              {profile.name}
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="ops-ai-voice-runtime-cell">
                        <div
                          className="ops-ai-inline-config"
                          title={[
                            profile.provider || "auto",
                            profile.voice_id?.trim(),
                            profile.model_id?.trim(),
                            hasFallback ? `FB: ${profile.fallback_provider}${profile.fallback_voice_id?.trim() ? ` / ${profile.fallback_voice_id}` : ""}` : ""
                          ].filter(Boolean).join(" · ")}
                        >
                          <strong>
                            {profile.provider === "google_cloud_tts"
                              ? t("opsTtsAi.providerGoogleCloudTts")
                              : profile.provider || "auto"}
                          </strong>
                          <span aria-hidden="true">·</span>
                          <span>{profile.voice_id?.trim() || "—"}</span>
                          {profile.model_id?.trim() ? <><span aria-hidden="true">·</span><span>{profile.model_id}</span></> : null}
                          {showsTtsApiKey(profile.provider) ? <span className={profileCredentialReady ? "is-key-set" : "is-key-missing"}>· {profileCredentialReady ? t("opsTtsAi.profileKeySet") : t("opsTtsAi.profileKeyUnset")}</span> : null}
                          {hasFallback ? <span className="is-muted">· FB: {profile.fallback_provider}{profile.fallback_voice_id?.trim() ? ` / ${profile.fallback_voice_id}` : ""}</span> : null}
                        </div>
                      </td>
                      <td>
                        <div className="ops-ai-inline-config is-secondary" title={`${profile.language_code || "vi"} · ×${profile.speaking_rate ?? 1} · ${profile.local_backend || "auto"}${profile.device ? `/${profile.device}` : ""}`}>
                          <strong>{(profile.language_code || "vi").toUpperCase()}</strong>
                          <span aria-hidden="true">·</span>
                          <span>×{profile.speaking_rate ?? 1}</span>
                          <span aria-hidden="true">·</span>
                          <span>{profile.local_backend || "auto"}{profile.device ? `/${profile.device}` : ""}</span>
                        </div>
                      </td>
                      <td>
                        <div className="ops-ai-inline-status is-tts">
                          <span className={`ops-ai-chip ops-tts-chip ${ttsReadyChipClass(rowReady)}`}>
                            {t(ttsReadyLabelKey(rowReady))}
                          </span>
                          <label className="ops-tts-setup-switch" title={t("opsTtsAi.profileActiveHint")}>
                            <input
                              type="checkbox"
                              checked={isOn}
                              disabled={profileBusy}
                              aria-label={isOn ? t("opsTtsAi.profileOn") : t("opsTtsAi.profileOff")}
                              onChange={(e) => void onSetActive(profile.id, e.target.checked)}
                            />
                            <span className="ops-tts-setup-switch__track" aria-hidden="true" />
                          </label>
                        </div>
                      </td>
                      <td className="ops-tts-setup-table__actions">
                        <div className="ops-ai-row-actions">
                          <button
                            type="button"
                            className="ops-tts-setup-table__icon-btn"
                            disabled={profileBusy}
                            aria-label={t("opsTtsAi.profileEdit")}
                            title={t("opsTtsAi.profileEdit")}
                            onClick={() => void openEditor(profile.id)}
                          >
                            <TtsSetupActionIcon kind="edit" />
                          </button>
                          <button
                            type="button"
                            className="ops-tts-setup-table__icon-btn ops-tts-setup-table__icon-btn--danger"
                            disabled={profileBusy || profiles.length <= 1}
                            aria-label={t("opsTtsAi.profileDelete")}
                            title={t("opsTtsAi.profileDelete")}
                            onClick={() => void onDeleteProfile(profile.id, profile.name)}
                          >
                            <TtsSetupActionIcon kind="delete" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>
      </OpsConsoleShell>
    );
  }

  if (!form) {
    return (
      <OpsConsoleShell
        actions={refreshAction}
        description={t("nav.ttsSettingsDesc")}
        title={t("nav.ttsSettings")}
      >
        <AsyncContentBoundary status="loading" skeletonVariant="form" loadingLabel={t("opsTtsAi.loadingDetail")}>
          {null}
        </AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  const testFailure =
    testResult && !testResult.ok
      ? formatProviderError(testResult.detail || t("opsTtsAi.testFail"), {
          unauthorized: t("opsTtsAi.errorUnauthorized"),
          forbidden: t("opsTtsAi.errorForbidden"),
          notFound: t("opsTtsAi.errorNotFound"),
          rateLimited: t("opsTtsAi.errorRateLimited"),
          failed: t("opsTtsAi.errorFailed"),
          checkKey: t("opsTtsAi.errorCheckKey"),
          checkForbidden: t("opsTtsAi.errorCheckForbidden"),
          checkEndpoint: t("opsTtsAi.errorCheckEndpoint")
        })
      : null;
  const testSuccess =
    testResult && testResult.ok
      ? formatTtsProbeSuccess(testResult, {
          passed: t("opsTtsAi.testOk"),
          autoVieneu: t("opsTtsAi.testProbeAutoVieneu"),
          autoEdge: t("opsTtsAi.testProbeAutoEdge"),
          generic: t("opsTtsAi.testOkGeneric")
        })
      : null;

  const isLocal = kind === "local";
  const isCloud = kind === "cloud";
  const isHttp = kind === "http";
  // Gemini can use either an AI Studio API key or billed Vertex OAuth.  Only
  // the latter needs the Google Cloud credential editor/locked endpoint.
  const isGoogle = activeProvider === "google" || (
    activeProvider === "google_gemini" && form.credentialMode !== "api_key"
  );
  const isGoogleAgentTts = activeProvider === "google_cloud_tts";
  const googleDraftMetadata = googleServiceAccountMetadata(form.googleServiceAccountJson);
  const googleServiceAccountReady = Boolean(googleDraftMetadata) ||
    (meta.googleServiceAccountSet && !form.clearGoogleServiceAccount);
  const isLucylabJsonRpc = Boolean(
    isHttp &&
    /^https:\/\/api\.lucylab\.io\/?$/i.test(form.baseUrl.trim()) &&
    form.httpConnector.synthesisPath.trim() === "/json-rpc"
  );
  const catalogRefreshBusy = catalogRefreshPhase !== "idle";
  const localDraftProvider = nameProviderForTest(form);
  const localDraftNeedsProvider = Boolean(
    isLocal &&
    !editingProfileId &&
    (!localDraftProvider ||
      (form.providerChoice === "custom" && !/^[a-z][a-z0-9_\-]{0,62}$/.test(localDraftProvider)))
  );
  const fieldCaps = getTtsFieldCapabilities(
    activeProvider,
    form?.localBackend || "auto",
    catalog?.capabilities || null
  );
  const isSystem = kind === "system";
  const readyState = resolveTtsReadyState({
    test: testResult ? { ok: testResult.ok, detail: testResult.detail } : null,
    install: installResult ? { ok: installResult.ok, detail: installResult.detail } : null,
    runtime,
    liveImportOk
  });
  const readyChipLabel =
    !editingProfileId && readyState === "ready"
      ? t("opsTtsAi.readyProbed")
      : t(ttsReadyLabelKey(readyState));
  const readyChipClass =
    !editingProfileId && readyState === "ready" ? "is-ok" : ttsReadyChipClass(readyState);
  const hadInstall = Boolean(runtime?.last_install?.ok || installResult?.ok);
  const isRemoteCatalogProvider = isCloud || isHttp;
  const allCatalogVoices = catalog?.voices || [];
  const allCatalogModels = ttsCatalogModelOptions(catalog);
  const allCatalogLanguages = ttsCatalogLanguageOptions(catalog);
  const remoteCatalogVoices = filterTtsCatalogVoices(catalog, {
    languageCode: form.languageCode,
    modelId: form.modelId
  });
  const remoteCatalogModels = filterTtsCatalogModels(catalog, {
    languageCode: form.languageCode,
    voiceId: form.voiceId
  });
  const remoteCatalogLanguages = filterTtsCatalogLanguages(catalog, {
    modelId: form.modelId,
    voiceId: form.voiceId
  });
  const catalogVoices = (isRemoteCatalogProvider ? remoteCatalogVoices : allCatalogVoices).length
    ? isRemoteCatalogProvider
      ? remoteCatalogVoices
      : allCatalogVoices
    : null;
  const catalogStyles = catalog?.styles?.length ? catalog.styles : null;
  const catalogModels = catalog?.models?.length ? catalog.models : null;
  const selectedCatalogModel = allCatalogModels.find((model) => sameCatalogId(model.id, form.modelId));
  const selectedCatalogVoice = allCatalogVoices.find((voice) => sameCatalogId(voice.id, form.voiceId));
  const selectedCatalogVoiceCompatible =
    !selectedCatalogVoice || remoteCatalogVoices.some((voice) => sameCatalogId(voice.id, selectedCatalogVoice.id));
  const selectedCatalogModelCompatible =
    !selectedCatalogModel || remoteCatalogModels.some((model) => sameCatalogId(model.id, selectedCatalogModel.id));
  const remoteCatalogSelectionMismatch =
    isRemoteCatalogProvider && (!selectedCatalogVoiceCompatible || !selectedCatalogModelCompatible);
  const catalogDiscoveryStatus = (catalog?.discovery?.status || "").trim().toLowerCase();
  const catalogWarnings = [catalog?.warning || "", ...(catalog?.discovery?.warnings || [])]
    .map((warning) => warning.trim())
    .filter((warning, index, rows) => Boolean(warning) && rows.indexOf(warning) === index);
  if (isLucylabJsonRpc && catalogWarnings.some((warning) => /no mapped catalog items|empty catalog|endpoint could not be read/i.test(warning))) {
    catalogWarnings.splice(0, catalogWarnings.length, t("opsTtsAi.httpLucylabNoVoices"));
  }
  const remoteVoiceSelectValue = allCatalogVoices.some((voice) => sameCatalogId(voice.id, form.voiceId))
    ? form.voiceId
    : TTS_CATALOG_MANUAL_VALUE;
  const remoteModelSelectValue = allCatalogModels.some((model) => sameCatalogId(model.id, form.modelId))
    ? form.modelId
    : TTS_CATALOG_MANUAL_VALUE;
  const remoteLanguageSelectValue = remoteCatalogLanguages.some((language) =>
    sameCatalogId(language.code, form.languageCode)
  )
    ? form.languageCode
    : TTS_CATALOG_MANUAL_VALUE;
  const discoveryLabelKey =
    catalogDiscoveryStatus === "complete"
      ? "opsTtsAi.catalogDiscoveryComplete"
      : catalogDiscoveryStatus === "partial"
        ? "opsTtsAi.catalogDiscoveryPartial"
        : "opsTtsAi.catalogDiscoveryUnavailable";
  const isOmniEngine = isOmnivoiceProvider(activeProvider);
  const engineModelOptions = isOmniEngine && engineCatalog.length ? engineCatalog : null;
  const engineGroups: Array<{
    id: EngineCatalogCategory;
    label: string;
    engines: TtsAiEngineOption[];
  }> = (
    [
      ["ready", t("opsTtsAi.engineGroupReady")],
      ["installable", t("opsTtsAi.engineGroupInstallable")],
      ["installed", t("opsTtsAi.engineGroupInstalled")],
      ["setup", t("opsTtsAi.engineGroupSetup")],
      ["unavailable", t("opsTtsAi.engineGroupUnavailable")]
    ] as Array<[EngineCatalogCategory, string]>
  )
    .map(([id, label]) => ({
      id,
      label,
      engines: engineCatalog.filter((engine) => engineCatalogCategory(engine) === id)
    }));
  const activeEngineGroup =
    engineGroups.find((group) => group.id === engineGroupTab) || engineGroups[0];
  const persistedProbeMatchesProvider =
    Boolean(runtime?.last_probe?.provider) &&
    runtime?.last_probe?.provider?.trim().toLowerCase() === activeProvider.trim().toLowerCase();
  const httpProbeChecks =
    (testResult?.checks?.length ? testResult.checks : undefined) ||
    (!catalogStale && persistedProbeMatchesProvider && runtime?.last_probe?.checks?.length
      ? runtime.last_probe.checks
      : undefined) ||
    (!catalogStale && catalog?.discovery?.checks?.length ? catalog.discovery.checks : undefined) ||
    [];
  const httpCheckFor = (...stages: string[]) => {
    for (const stage of stages) {
      const check = httpProbeChecks.find((candidate) => candidate.stage === stage);
      if (check) return check;
    }
    return undefined;
  };
  const httpAuthCheck = httpCheckFor("authentication", "auth");
  const httpCatalogCheck = httpCheckFor(
    "aggregate catalog",
    "catalog",
    "catalog_models",
    "catalog_voices",
    "catalog_languages"
  );
  const httpSynthesisCheck = httpCheckFor("synthesis", "preview");
  const httpCredentialConfigured =
    form.httpConnector.authType === "none" || Boolean(form.apiKeyInput.trim()) || meta.apiKeySet;
  const httpAuthRejected = Boolean(
    testResult &&
      !testResult.ok &&
      /401|403|unauthori[sz]ed|forbidden|api key|token/i.test(testResult.detail || "")
  );
  const httpSynthesisConfigured =
    form.httpConnector.mode !== "auto" && Boolean(form.httpConnector.synthesisPath.trim());
  const httpConnectorSteps = [
    {
      id: "auth",
      label: t("opsTtsAi.httpStepAuthentication"),
      state: httpAuthCheck
        ? httpAuthCheck.status === "failed"
          ? "error"
          : httpAuthCheck.status === "passed"
            ? "ok"
            : "warn"
        : httpAuthRejected
          ? "error"
          : testResult?.ok
            ? "ok"
            : httpCredentialConfigured
              ? "warn"
              : "muted",
      detail: httpAuthCheck?.detail || (httpAuthRejected
        ? t("opsTtsAi.httpStatusRejected")
        : testResult?.ok
          ? t("opsTtsAi.httpStatusPassed")
          : httpCredentialConfigured
            ? t("opsTtsAi.httpStatusConfigured")
            : t("opsTtsAi.httpStatusNeedsSetup"))
    },
    {
      id: "catalog",
      label: t("opsTtsAi.httpStepCatalog"),
      state: catalogStale
        ? "warn"
        : httpCatalogCheck?.status === "failed"
        ? "error"
        : catalog
        ? catalogDiscoveryStatus === "complete"
          ? "ok"
          : "warn"
        : testResult?.ok
          ? "warn"
          : "muted",
      detail: catalogStale
        ? t("opsTtsAi.catalogStale")
        : httpCatalogCheck?.detail || (catalog
        ? catalogDiscoveryStatus === "complete"
          ? t("opsTtsAi.httpStatusPassed")
          : t("opsTtsAi.httpStatusManual")
        : testResult?.ok
          ? t("opsTtsAi.httpStatusManual")
          : t("opsTtsAi.httpStatusNeedsSetup"))
    },
    {
      id: "synthesis",
      label: t("opsTtsAi.httpStepSynthesis"),
      state: httpSynthesisCheck?.status === "failed" || previewFeedback ? "error" : httpSynthesisCheck?.status === "passed" || previewAudioUrl ? "ok" : httpSynthesisConfigured ? "warn" : "muted",
      detail: httpSynthesisCheck?.detail || (previewAudioUrl
        ? t("opsTtsAi.httpStatusPassed")
        : previewFeedback
          ? t("opsTtsAi.httpStatusRejected")
          : httpSynthesisConfigured
            ? t("opsTtsAi.httpStatusConfigured")
            : t("opsTtsAi.httpStatusNeedsSetup"))
    }
  ] as Array<{ id: string; label: string; state: string; detail: string }>;

  return (
    <OpsConsoleShell
      actions={refreshAction}
      description={t("nav.ttsSettingsDesc")}
      title={t("nav.ttsSettings")}
    >
    <main className="ops-page ops-page--settings ops-tts-page ops-ai-page is-compact">
      {error ? <div className="inline-error">{error}</div> : null}

      <OpsPanel
        title={`${t("opsTtsAi.panelTitle")} · ${editingProfileName || t("opsTtsAi.profileNew")}`}
        actions={
          <div className="ops-header-actions ops-ai-toolbar" role="group" aria-label={t("opsTtsAi.panelTitle")}>
            <div className="ops-ai-toolbar__group">
              <button
                type="button"
                onClick={() => void loadList()}
                disabled={saving || testing || installing || previewing || profileBusy}
                aria-label={t("opsTtsAi.profileBack")}
                title={t("opsTtsAi.profileBack")}
              >
                <TtsSetupActionIcon kind="back" />
                <span className="ops-tts-editor-actions__label">{t("opsTtsAi.actionBack")}</span>
              </button>
              <AsyncButton
                pending={asyncAction.isPending("test")}
                pendingLabel={t("opsTtsAi.testing")}
                leadingIcon={<TtsSetupActionIcon kind="test" />}
                onClick={() => void asyncAction.run("test", onTest)}
                disabled={
                  saving || installing || previewing || profileBusy || localDraftNeedsProvider || catalogRefreshBusy
                }
                aria-label={t("opsTtsAi.test")}
                title={t("opsTtsAi.test")}
              >
                <span className="ops-tts-editor-actions__label">{t("opsTtsAi.actionTest")}</span>
              </AsyncButton>
              <AsyncButton
                className="primary"
                pending={asyncAction.isPending("save")}
                pendingLabel={t("opsTtsAi.saving")}
                leadingIcon={<TtsSetupActionIcon kind="save" />}
                onClick={() => void asyncAction.run("save", onSave)}
                disabled={
                  testing || installing || previewing || profileBusy || localDraftNeedsProvider || catalogRefreshBusy
                }
                aria-label={t("opsTtsAi.save")}
                title={t("opsTtsAi.save")}
              >
                <span className="ops-tts-editor-actions__label">{t("opsTtsAi.actionSave")}</span>
              </AsyncButton>
            </div>
          </div>
        }
        meta={
          <div className="ops-ai-meta">
            <div className="ops-ai-status" aria-label={t("opsTtsAi.statusLabel")}>
              <span className={`ops-ai-chip ${meta.source === "workspace_db" ? "is-active" : "is-muted"}`}>
                {meta.source === "workspace_db" ? t("opsTtsAi.sourceDbShort") : t("opsTtsAi.sourceEnvShort")}
              </span>
              <span className={`ops-ai-chip ${meta.apiKeySet ? "is-ok" : "is-muted"}`}>
                {meta.apiKeySet ? `${t("opsTtsAi.keySet")}: ${meta.apiKeyMasked}` : t("opsTtsAi.keyUnset")}
              </span>
              <span className="ops-ai-chip is-muted">
                {activeProvider.trim() ? activeProvider : t("opsTtsAi.providerUnset")}
              </span>
              <span className="ops-ai-chip is-muted">{t(kindLabelKey(kind))}</span>
              <span className={`ops-ai-chip ${readyChipClass}`} title={t("opsTtsAi.readyHint")} data-ready-state={readyState}>
                {readyChipLabel}
              </span>
            </div>
          </div>
        }
      >
        <div className="ops-tts-editor is-dense">
        {testResult ? (
          testResult.ok && testSuccess ? (
            <div className="ops-tts-test-banner is-ok" role="status">
              <span className="ops-tts-test-banner__icon" aria-hidden="true">
                <svg viewBox="0 0 20 20">
                  <path
                    d="M5 10.2 8.2 13.5 15 6.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.9"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <div className="ops-tts-test-banner__body">
                <div className="ops-tts-test-banner__title-row">
                  <strong>{testSuccess.title}</strong>
                  {testSuccess.provider ? (
                    <span className="ops-tts-test-banner__chip">{testSuccess.provider}</span>
                  ) : null}
                </div>
                <span className="ops-tts-test-banner__message">{testSuccess.message}</span>
                <span className="ops-tts-test-banner__hint">
                  {editingProfileId ? t("opsTtsAi.testOkHint") : t("opsTtsAi.testOkDraftHint")}
                </span>
              </div>
              <button
                type="button"
                className="ops-tts-test-banner__dismiss"
                aria-label={t("common.close")}
                title={t("common.close")}
                onClick={() => setTestResult(null)}
              >
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path
                    d="M6.5 6.5 13.5 13.5M13.5 6.5 6.5 13.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>
          ) : (
            <div
              className="ops-tts-test-banner is-error"
              role="alert"
              title={testResult.detail || undefined}
            >
              <span className="ops-tts-test-banner__icon" aria-hidden="true">
                <svg viewBox="0 0 20 20">
                  <circle cx="10" cy="10" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.75" />
                  <path
                    d="M10 7.2v3.6M10 13.2h.01"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
              <div className="ops-tts-test-banner__body">
                <div className="ops-tts-test-banner__title-row">
                  <strong>
                    {testFailure?.title || t("opsTtsAi.testFail")}
                    {testFailure?.httpStatus ? ` · HTTP ${testFailure.httpStatus}` : ""}
                  </strong>
                  {testResult.provider ? (
                    <span className="ops-tts-test-banner__meta">{testResult.provider}</span>
                  ) : null}
                </div>
                <span className="ops-tts-test-banner__message">
                  {testFailure?.message || testResult.detail}
                </span>
                <span className="ops-tts-test-banner__hint">
                  {testResult.detail === t("opsTtsAi.testNeedProvider")
                    ? t("opsTtsAi.testNeedProviderHint")
                    : testResult.detail === t("opsTtsAi.testNeedApiKey")
                      ? t("opsTtsAi.testNeedApiKeyHint")
                      : testResult.detail === t("opsTtsAi.testNeedBaseUrl")
                        ? t("opsTtsAi.testNeedBaseUrlHint")
                        : testResult.detail === t("opsTtsAi.customProviderInvalid")
                          ? t("opsTtsAi.customProviderInvalidHint")
                          : providerTestErrorHint(testFailure?.httpStatus, {
                              key: t("opsTtsAi.testErrorHintKey"),
                              forbidden: t("opsTtsAi.testErrorHintForbidden"),
                              quota: t("opsTtsAi.testErrorHintQuota"),
                              generic: t("opsTtsAi.testErrorHint")
                            })}
                </span>
              </div>
              <button
                type="button"
                className="ops-tts-test-banner__dismiss"
                aria-label={t("common.close")}
                title={t("common.close")}
                onClick={() => setTestResult(null)}
              >
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path
                    d="M6.5 6.5 13.5 13.5M13.5 6.5 6.5 13.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>
          )
        ) : null}

        <section className="ops-tts-section">
          <header className="ops-tts-section__head">
            <h3>{t("opsTtsAi.sectionKind")}</h3>
            <p>{t(kindHintKey(kind))}</p>
          </header>
          <div className="ops-tts-grid" style={{ marginBottom: "0.85rem" }}>
            <div className="ops-form-field ops-tts-setup-name ops-tts-span-2">
              <label htmlFor="tts-ai-setup-name">{t("opsTtsAi.setupName")}</label>
              <input
                id="tts-ai-setup-name"
                value={editingProfileName}
                onChange={(e) => setEditingProfileName(e.target.value)}
                placeholder={t("opsTtsAi.setupNamePlaceholder")}
                title={t("opsTtsAi.setupNameHint")}
                spellCheck={false}
                autoComplete="off"
              />
              <p className="ops-tts-field-hint">{t("opsTtsAi.setupNameHint")}</p>
            </div>
          </div>
          <div className="ops-tts-kind-tabs ops-tts-kind-tabs--segmented" role="tablist" aria-label={t("opsTtsAi.sectionKind")}>

              {TTS_KIND_ORDER.map((item) => (
                <button
                  key={item}
                  type="button"
                  role="tab"
                  aria-selected={kind === item}
                  className={`ops-tts-kind-tab${kind === item ? " is-active" : ""}`}
                  onClick={() => onKindChange(item)}
                  disabled={catalogRefreshBusy}
                  title={t(kindHintKey(item))}
                >
                  {t(kindLabelKey(item))}
                </button>
              ))}
            </div>
          <div className="ops-tts-grid" style={{ marginTop: "0.85rem" }}>
          <div className="ops-form-field ops-tts-provider-name ops-tts-span-2">
            <label htmlFor="tts-ai-provider">{t("opsTtsAi.provider")}</label>
            <select
              id="tts-ai-provider"
              value={
                providerSelect && TTS_PROVIDERS_BY_KIND[kind].includes(providerSelect)
                  ? providerSelect
                  : providerSelect === "custom" && kind === "local"
                    ? "custom"
                    : isLocal && !editingProfileId
                      ? ""
                      : defaultProviderForKind(kind)
              }
              onChange={(e) => onProviderSelect(e.target.value)}
              disabled={catalogRefreshBusy}
              title={t("opsTtsAi.providerHint")}
            >
              {isLocal && !editingProfileId ? (
                <option value="" disabled>
                  {t("opsTtsAi.providerSelectPlaceholder")}
                </option>
              ) : null}
              {TTS_PROVIDERS_BY_KIND[kind].map((slug) => (
                <option key={slug} value={slug}>
                  {slug === "custom"
                    ? t("opsTtsAi.providerCustom")
                    : slug === "google_cloud_tts"
                      ? t("opsTtsAi.providerGoogleCloudTts")
                      : slug}
                </option>
              ))}
            </select>
            <p className="ops-tts-field-hint">{t("opsTtsAi.providerHint")}</p>
          </div>
          <div className="ops-form-field ops-tts-span-2">
            <label htmlFor="tts-ai-expressive-mode">{t("opsTtsAi.expressiveMode")}</label>
            <select
              id="tts-ai-expressive-mode"
              value={form?.expressiveMode || "best_effort"}
              onChange={(event) =>
                setForm((current) =>
                  current ? { ...current, expressiveMode: event.target.value } : current
                )
              }
              disabled={catalogRefreshBusy}
            >
              <option value="off">{t("opsTtsAi.expressiveOff")}</option>
              <option value="best_effort">{t("opsTtsAi.expressiveBestEffort")}</option>
              <option value="required">{t("opsTtsAi.expressiveRequired")}</option>
            </select>
            <p className="ops-tts-field-hint">{t("opsTtsAi.expressiveModeHint")}</p>
          </div>
          {isGeminiExpressiveProvider(activeProvider) ? (
            <>
              <div className="ops-form-field ops-tts-span-2">
                <label htmlFor="tts-ai-synthesis-strategy">
                  {t("opsTtsAi.synthesisStrategy")}
                </label>
                <select
                  id="tts-ai-synthesis-strategy"
                  value={form.synthesisStrategy}
                  onChange={(event) =>
                    setForm((current) =>
                      current
                        ? { ...current, synthesisStrategy: event.target.value }
                        : current
                    )
                  }
                  disabled={catalogRefreshBusy}
                >
                  <option value="whole_video">{t("opsTtsAi.synthesisWholeVideo")}</option>
                  <option value="auto_blocks">{t("opsTtsAi.synthesisAutoBlocks")}</option>
                  <option value="segment">{t("opsTtsAi.synthesisLegacySegments")}</option>
                </select>
                <p className="ops-tts-field-hint">
                  {t("opsTtsAi.synthesisStrategyHint")}
                </p>
              </div>
              {form.synthesisStrategy !== "segment" ? (
                <>
                  <div className="ops-form-field">
                    <label htmlFor="tts-ai-whole-max-seconds">
                      {t("opsTtsAi.maxWholeVideoSeconds")}
                    </label>
                    <input
                      id="tts-ai-whole-max-seconds"
                      type="number"
                      min="30"
                      max="600"
                      step="10"
                      value={form.maxWholeVideoSeconds}
                      onChange={(event) =>
                        setForm((current) =>
                          current
                            ? { ...current, maxWholeVideoSeconds: event.target.value }
                            : current
                        )
                      }
                      disabled={catalogRefreshBusy}
                    />
                  </div>
                  <div className="ops-form-field">
                    <label htmlFor="tts-ai-block-max-seconds">
                      {t("opsTtsAi.maxBlockSeconds")}
                    </label>
                    <input
                      id="tts-ai-block-max-seconds"
                      type="number"
                      min="15"
                      max="120"
                      step="5"
                      value={form.maxBlockSeconds}
                      onChange={(event) =>
                        setForm((current) =>
                          current
                            ? { ...current, maxBlockSeconds: event.target.value }
                            : current
                        )
                      }
                      disabled={catalogRefreshBusy}
                    />
                  </div>
                  <div className="ops-form-field ops-tts-span-2">
                    <label htmlFor="tts-ai-compact-trigger">
                      {t("opsTtsAi.compactTriggerRatio")}
                    </label>
                    <input
                      id="tts-ai-compact-trigger"
                      type="number"
                      min="0.65"
                      max="1"
                      step="0.01"
                      value={form.compactTriggerRatio}
                      onChange={(event) =>
                        setForm((current) =>
                          current
                            ? { ...current, compactTriggerRatio: event.target.value }
                            : current
                        )
                      }
                      disabled={catalogRefreshBusy}
                    />
                    <p className="ops-tts-field-hint">
                      {t("opsTtsAi.compactTriggerRatioHint")}
                    </p>
                  </div>
                  <div className="ops-tts-provider-gate ops-tts-span-2" role="status">
                    <div>
                      <strong>{t("opsTtsAi.wholeVideoActiveTitle")}</strong>
                      <p>{t("opsTtsAi.wholeVideoActiveHint")}</p>
                    </div>
                  </div>
                </>
              ) : null}
            </>
          ) : null}
          {showCustomSlug ? (
            <div className="ops-form-field ops-tts-span-2">
              <label htmlFor="tts-ai-custom-slug">{t("opsTtsAi.customProviderSlug")}</label>
              <input
                id="tts-ai-custom-slug"
                value={form?.customProviderSlug || ""}
                onChange={(e) => onCustomSlugInput(e.target.value)}
                disabled={catalogRefreshBusy}
                placeholder={t("opsTtsAi.customProviderSlugPlaceholder")}
                title={t("opsTtsAi.customProviderHint")}
                spellCheck={false}
                autoComplete="off"
              />
              <p className="ops-tts-field-hint">{t("opsTtsAi.customProviderHint")}</p>
            </div>
          ) : null}
          {localDraftNeedsProvider ? (
            <div className="ops-tts-provider-gate ops-tts-span-2" role="status">
              <span className="ops-tts-provider-gate__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path
                    d="M7 7.5h10M7 12h10M7 16.5h6"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                  />
                  <rect x="3.5" y="3.5" width="17" height="17" rx="4" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </span>
              <div>
                <strong>{t("opsTtsAi.providerRequiredTitle")}</strong>
                <p>{t("opsTtsAi.providerRequiredHint")}</p>
              </div>
            </div>
          ) : null}
          </div>
        </section>

        {(isCloud || isHttp) ? (
          <section className="ops-tts-section">
            <header className="ops-tts-section__head">
              <h3>{t("opsTtsAi.sectionCredentials")}</h3>
              <p>{t(isHttp ? "opsTtsAi.sectionHttpHint" : "opsTtsAi.sectionCredentialsHint")}</p>
            </header>
            <div className="ops-tts-grid">
              {(isHttp || isCloud || fieldCaps.base_url) && activeProvider !== "google_cloud_tts" ? (
                <div className="ops-form-field ops-tts-span-2">
                  <label htmlFor="tts-ai-base-url">{t("opsTtsAi.baseUrl")}</label>
                  <input
                    id="tts-ai-base-url"
                    value={form.baseUrl}
                    onChange={(e) => onRemoteCredentialChange("baseUrl", e.target.value)}
                    placeholder={t("opsTtsAi.baseUrlPlaceholder")}
                    title={t("opsTtsAi.baseUrlHint")}
                    spellCheck={false}
                    autoComplete="off"
                    disabled={isGoogle || testing || catalogRefreshBusy}
                  />
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.baseUrlHint")}</p>
                </div>
              ) : null}
              {isGoogle ? (
                <div className="ops-tts-google-credential ops-tts-span-2">
                  <div className="ops-form-field">
                    <label htmlFor="tts-google-credential-mode">{t("opsTtsAi.googleCredentialMode")}</label>
                    <select
                      id="tts-google-credential-mode"
                      value={form.credentialMode}
                      onChange={(event) => onGoogleCredentialModeChange(event.target.value)}
                      disabled={testing || catalogRefreshBusy}
                    >
                      <option value="google_service_account">{t("opsTtsAi.googleServiceAccount")}</option>
                      <option value="google_adc">{t("opsTtsAi.googleAdc")}</option>
                      <option value="google_oauth_token">{t("opsTtsAi.googleOauthToken")}</option>
                    </select>
                    <p className="ops-tts-field-hint ops-tts-field-hint--quiet">
                      {t(`opsTtsAi.${form.credentialMode === "google_adc" ? "googleAdcHint" : form.credentialMode === "google_oauth_token" ? "googleOauthTokenHint" : "googleServiceAccountHint"}`)}
                    </p>
                  </div>

                  {form.credentialMode === "google_service_account" ? (
                    <div className="ops-tts-google-upload">
                      <div className="ops-tts-google-upload__status" data-ready={googleServiceAccountReady}>
                        <strong>
                          {form.clearGoogleServiceAccount
                            ? t("opsTtsAi.googleServiceAccountWillRemove")
                            : googleServiceAccountReady
                              ? t("opsTtsAi.googleServiceAccountReady")
                              : t("opsTtsAi.googleServiceAccountMissing")}
                        </strong>
                        {googleDraftMetadata || (meta.googleServiceAccountSet && !form.clearGoogleServiceAccount) ? (
                          <small>
                            {(googleDraftMetadata?.email || meta.googleServiceAccountEmail)} · {t("opsTtsAi.googleProject")} {googleDraftMetadata?.projectId || meta.googleServiceAccountProjectId}
                          </small>
                        ) : (
                          <small>{t("opsTtsAi.googleServiceAccountPrivateHint")}</small>
                        )}
                        {form.googleServiceAccountFileName ? <small>{form.googleServiceAccountFileName}</small> : null}
                      </div>
                      <div className="ops-tts-google-upload__actions">
                        <label className="ops-tts-action-btn" htmlFor="tts-google-service-account-file">
                          {t(googleServiceAccountReady ? "opsTtsAi.googleServiceAccountReplace" : "opsTtsAi.googleServiceAccountUpload")}
                        </label>
                        <input
                          id="tts-google-service-account-file"
                          className="ops-tts-google-upload__input"
                          type="file"
                          accept=".json,application/json"
                          disabled={testing || catalogRefreshBusy}
                          onChange={(event) => {
                            const file = event.currentTarget.files?.[0];
                            event.currentTarget.value = "";
                            void onGoogleServiceAccountFile(file);
                          }}
                        />
                        {googleServiceAccountReady ? (
                          <button
                            type="button"
                            className="ops-tts-action-btn"
                            onClick={clearGoogleServiceAccount}
                            disabled={testing || catalogRefreshBusy}
                          >
                            {t("opsTtsAi.googleServiceAccountRemove")}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {form.credentialMode === "google_adc" ? (
                    <div className="ops-tts-google-info" role="status">
                      <strong>{t("opsTtsAi.googleAdcTitle")}</strong>
                      <p>{t("opsTtsAi.googleAdcDescription")}</p>
                    </div>
                  ) : null}

                  {form.credentialMode === "google_oauth_token" ? (
                    <div className="ops-form-field">
                      <label htmlFor="tts-ai-google-oauth-token">{t("opsTtsAi.googleOauthToken")}</label>
                      <input
                        id="tts-ai-google-oauth-token"
                        type="password"
                        autoComplete="off"
                        placeholder={meta.apiKeySet ? t("opsTtsAi.apiKeyKeep") : t("opsTtsAi.googleOauthTokenPlaceholder")}
                        value={form.apiKeyInput}
                        onChange={(event) => onRemoteCredentialChange("apiKeyInput", event.target.value)}
                        disabled={testing || catalogRefreshBusy}
                      />
                    </div>
                  ) : null}
                </div>
              ) : (isCloud || isHttp || fieldCaps.api_key) ? (
                <>
                  <div className="ops-form-field ops-tts-span-2">
                    <label htmlFor="tts-ai-api-key">{t("opsTtsAi.apiKey")}</label>
                    <input
                      id="tts-ai-api-key"
                      type="password"
                      autoComplete="off"
                      placeholder={meta.apiKeySet ? t("opsTtsAi.apiKeyKeep") : t("opsTtsAi.apiKeyPlaceholder")}
                      title={t("opsTtsAi.apiKeyHint")}
                      value={form.apiKeyInput}
                      onChange={(e) => onRemoteCredentialChange("apiKeyInput", e.target.value)}
                      disabled={testing || catalogRefreshBusy}
                    />
                    <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.apiKeyHint")}</p>
                    {isHttp || (isCloud && form.httpConnector.mode !== "auto") ? (
                      <p className="ops-tts-field-hint ops-tts-http-key-hint">
                        {t("opsTtsAi.httpRawKeyHint").replace("{prefix}", form.httpConnector.authPrefix || t("opsTtsAi.httpNoKeyPrefix"))}
                      </p>
                    ) : null}
                  </div>
                </>
              ) : null}
              {activeProvider === "google_cloud_tts" ? (
                <div className="ops-form-field ops-tts-span-2">
                  <label htmlFor="tts-ai-google-cloud-region">{t("opsTtsAi.googleCloudRegion")}</label>
                  <select
                    id="tts-ai-google-cloud-region"
                    value={form.googleCloudRegion || "global"}
                    onChange={(event) =>
                      setForm((current) =>
                        current ? { ...current, googleCloudRegion: event.target.value } : current
                      )
                    }
                    disabled={testing || catalogRefreshBusy}
                  >
                    <option value="global">global</option>
                  </select>
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">
                    {t("opsTtsAi.googleCloudRegionHint")}
                  </p>
                </div>
              ) : null}
            </div>
            {(isCloud || isHttp) && !isGoogle && !isGoogleAgentTts ? (
              <div className="ops-tts-http-connector" aria-label={t("opsTtsAi.httpConnectorTitle")}>
                <div className="ops-tts-http-connector__intro">
                  <div>
                    <strong>{t("opsTtsAi.httpConnectorTitle")}</strong>
                    <p>{t("opsTtsAi.httpConnectorHint")}</p>
                  </div>
                  <div className="ops-tts-http-connector__intro-actions">
                    <button
                      type="button"
                      className="ops-tts-action-btn"
                      onClick={applyLucylabPreset}
                      disabled={testing || catalogRefreshBusy}
                      title={t("opsTtsAi.httpLucylabPresetHint")}
                    >
                      {t("opsTtsAi.httpLucylabPreset")}
                    </button>
                    <span className="ops-tts-http-connector__version">v1</span>
                  </div>
                </div>

                <div className="ops-tts-http-connector__steps" role="list" aria-label={t("opsTtsAi.httpStepsLabel")}>
                  {httpConnectorSteps.map((step, index) => (
                    <div className={`ops-tts-http-step is-${step.state}`} role="listitem" key={step.id}>
                      <span className="ops-tts-http-step__number" aria-hidden="true">{index + 1}</span>
                      <span className="ops-tts-http-step__copy">
                        <strong>{step.label}</strong>
                        <small>{step.detail}</small>
                      </span>
                    </div>
                  ))}
                </div>

                <div className="ops-tts-http-mode-tabs" role="tablist" aria-label={t("opsTtsAi.httpModeLabel")}>
                  {HTTP_CONNECTOR_MODES.map((mode) => (
                    <button
                      type="button"
                      role="tab"
                      key={mode}
                      aria-selected={form.httpConnector.mode === mode}
                      className={form.httpConnector.mode === mode ? "is-active" : ""}
                      onClick={() => updateHttpConnector({ mode })}
                      disabled={testing || catalogRefreshBusy}
                    >
                      {t(`opsTtsAi.httpMode${mode[0].toUpperCase()}${mode.slice(1)}`)}
                    </button>
                  ))}
                </div>
                <p className="ops-tts-field-hint ops-tts-field-hint--quiet ops-tts-http-connector__mode-hint">
                  {form.httpConnector.mode === "auto"
                    ? t("opsTtsAi.httpModeAutoHint")
                    : form.httpConnector.mode === "openapi"
                      ? t("opsTtsAi.httpModeOpenapiHint")
                      : t("opsTtsAi.httpModeCustomHint")}
                </p>

                {form.httpConnector.mode === "openapi" ? (
                  <div className="ops-tts-grid ops-tts-http-openapi">
                    <div className="ops-form-field ops-tts-span-2">
                      <label htmlFor="tts-http-openapi-url">{t("opsTtsAi.httpOpenapiUrl")}</label>
                      <input
                        id="tts-http-openapi-url"
                        value={form.httpConnector.openapiUrl}
                        onChange={(event) => updateHttpConnector({ openapiUrl: event.target.value })}
                        placeholder={t("opsTtsAi.httpOpenapiUrlPlaceholder")}
                        title={t("opsTtsAi.httpOpenapiUrlHint")}
                        spellCheck={false}
                        autoComplete="off"
                      />
                      <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.httpOpenapiUrlHint")}</p>
                    </div>
                  </div>
                ) : null}

                <details className="ops-tts-http-mapping">
                  <summary>
                    <span>{t("opsTtsAi.httpAuthenticationTitle")}</span>
                    <small>{t("opsTtsAi.httpAuthenticationHint")}</small>
                  </summary>
                  <div className="ops-tts-grid ops-tts-http-mapping__body">
                    <div className="ops-form-field">
                      <label htmlFor="tts-http-auth-type">{t("opsTtsAi.httpAuthType")}</label>
                      <select
                        id="tts-http-auth-type"
                        value={form.httpConnector.authType}
                        onChange={(event) => {
                          const next = event.target.value as HttpConnectorAuthType;
                          updateHttpAuth({
                            authType: next,
                            authHeader:
                              next === "bearer"
                                ? "Authorization"
                                : next === "header"
                                  ? "X-API-Key"
                                  : form.httpConnector.authHeader,
                            authPrefix: next === "bearer" ? "Bearer " : "",
                            authQueryName:
                              next === "query"
                                ? form.httpConnector.authQueryName || "api_key"
                                : form.httpConnector.authQueryName
                          });
                        }}
                      >
                        <option value="bearer">{t("opsTtsAi.httpAuthBearer")}</option>
                        <option value="header">{t("opsTtsAi.httpAuthHeader")}</option>
                        <option value="query">{t("opsTtsAi.httpAuthQuery")}</option>
                        <option value="none">{t("opsTtsAi.httpAuthNone")}</option>
                      </select>
                    </div>
                    {form.httpConnector.authType !== "none" ? (
                      <div className="ops-form-field">
                        <label htmlFor="tts-http-auth-header">
                          {form.httpConnector.authType === "query" ? t("opsTtsAi.httpAuthQueryName") : t("opsTtsAi.httpAuthHeaderName")}
                        </label>
                        <input
                          id="tts-http-auth-header"
                          value={form.httpConnector.authType === "query" ? form.httpConnector.authQueryName : form.httpConnector.authHeader}
                          onChange={(event) =>
                            updateHttpAuth(
                              form.httpConnector.authType === "query"
                                ? { authQueryName: event.target.value }
                                : { authHeader: event.target.value }
                            )
                          }
                          placeholder={form.httpConnector.authType === "query" ? "api_key" : "Authorization"}
                          spellCheck={false}
                          autoComplete="off"
                        />
                        {form.httpConnector.authType === "query" ? (
                          <p className="ops-tts-field-hint is-warn">{t("opsTtsAi.httpAuthQueryRisk")}</p>
                        ) : null}
                      </div>
                    ) : null}
                    {form.httpConnector.authType !== "none" && form.httpConnector.authType !== "query" ? (
                      <div className="ops-form-field">
                        <label htmlFor="tts-http-auth-prefix">{t("opsTtsAi.httpAuthPrefix")}</label>
                        <input
                          id="tts-http-auth-prefix"
                          value={form.httpConnector.authPrefix}
                          onChange={(event) => updateHttpAuth({ authPrefix: event.target.value })}
                          placeholder="Bearer "
                          spellCheck={false}
                          autoComplete="off"
                        />
                      </div>
                    ) : null}
                    <div className="ops-form-field">
                      <label htmlFor="tts-http-auth-test-method">{t("opsTtsAi.httpAuthTestMethod")}</label>
                      <select
                        id="tts-http-auth-test-method"
                        value={form.httpConnector.authTestMethod}
                        onChange={(event) => updateHttpAuth({ authTestMethod: event.target.value })}
                      >
                        <option value="GET">GET</option>
                        <option value="HEAD">HEAD</option>
                      </select>
                    </div>
                    <div className="ops-form-field ops-tts-span-2">
                      <label htmlFor="tts-http-auth-test-path">{t("opsTtsAi.httpAuthTestPath")}</label>
                      <input
                        id="tts-http-auth-test-path"
                        value={form.httpConnector.authTestPath}
                        onChange={(event) => updateHttpAuth({ authTestPath: event.target.value })}
                        placeholder={t("opsTtsAi.httpAuthTestPathPlaceholder")}
                        spellCheck={false}
                      />
                      <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.httpAuthTestPathHint")}</p>
                    </div>
                  </div>
                </details>

                {form.httpConnector.mode !== "auto" ? (
                  <>
                    <details className="ops-tts-http-mapping">
                      <summary>
                        <span>{t("opsTtsAi.httpCatalogMappingTitle")}</span>
                        <small>{t("opsTtsAi.httpCatalogMappingHint")}</small>
                      </summary>
                      <div className="ops-tts-http-mapping__body">
                        {HTTP_CATALOG_RESOURCES.map((resource) => {
                          const endpoint = form.httpConnector.catalog[resource];
                          return (
                            <fieldset className="ops-tts-http-endpoint" key={resource}>
                              <legend>{t(`opsTtsAi.httpCatalog${resource[0].toUpperCase()}${resource.slice(1)}`)}</legend>
                              <div className="ops-tts-grid">
                                <div className="ops-form-field ops-tts-span-2">
                                  <label htmlFor={`tts-http-${resource}-path`}>{t("opsTtsAi.httpPath")}</label>
                                  <input
                                    id={`tts-http-${resource}-path`}
                                    value={endpoint.path}
                                    onChange={(event) => updateHttpCatalogEndpoint(resource, { path: event.target.value })}
                                    placeholder={resource === "models" ? "/models" : `/${resource}`}
                                    spellCheck={false}
                                  />
                                </div>
                                <div className="ops-form-field">
                                  <label htmlFor={`tts-http-${resource}-method`}>{t("opsTtsAi.httpCatalogMethod")}</label>
                                  <select
                                    id={`tts-http-${resource}-method`}
                                    value={endpoint.method}
                                    onChange={(event) => updateHttpCatalogEndpoint(resource, { method: event.target.value })}
                                  >
                                    <option value="GET">GET</option>
                                    <option value="POST">POST</option>
                                    <option value="PUT">PUT</option>
                                  </select>
                                </div>
                                <div className="ops-form-field">
                                  <label htmlFor={`tts-http-${resource}-content-type`}>{t("opsTtsAi.httpCatalogContentType")}</label>
                                  <select
                                    id={`tts-http-${resource}-content-type`}
                                    value={endpoint.content_type}
                                    onChange={(event) => updateHttpCatalogEndpoint(resource, { content_type: event.target.value })}
                                  >
                                    <option value="application/json">application/json</option>
                                    <option value="application/x-www-form-urlencoded">application/x-www-form-urlencoded</option>
                                  </select>
                                </div>
                                {endpoint.method !== "GET" ? (
                                  <div className="ops-form-field ops-tts-span-2">
                                    <label htmlFor={`tts-http-${resource}-body`}>{t("opsTtsAi.httpCatalogBody")}</label>
                                    <textarea
                                      id={`tts-http-${resource}-body`}
                                      rows={4}
                                      value={endpoint.body}
                                      onChange={(event) => updateHttpCatalogEndpoint(resource, { body: event.target.value })}
                                      spellCheck={false}
                                    />
                                    <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.httpCatalogBodyHint")}</p>
                                  </div>
                                ) : null}
                                <div className="ops-form-field">
                                  <label htmlFor={`tts-http-${resource}-items`}>{t("opsTtsAi.httpItemsPath")}</label>
                                  <input
                                    id={`tts-http-${resource}-items`}
                                    value={endpoint.items_path}
                                    onChange={(event) => updateHttpCatalogEndpoint(resource, { items_path: event.target.value })}
                                    placeholder="data.items"
                                    spellCheck={false}
                                  />
                                </div>
                                <div className="ops-form-field">
                                  <label htmlFor={`tts-http-${resource}-id`}>{resource === "languages" ? t("opsTtsAi.httpCodePath") : t("opsTtsAi.httpIdPath")}</label>
                                  <input
                                    id={`tts-http-${resource}-id`}
                                    value={endpoint.id_path}
                                    onChange={(event) => updateHttpCatalogEndpoint(resource, { id_path: event.target.value })}
                                    placeholder={resource === "languages" ? "code" : "id"}
                                    spellCheck={false}
                                  />
                                </div>
                                <div className="ops-form-field">
                                  <label htmlFor={`tts-http-${resource}-label`}>{t("opsTtsAi.httpLabelPath")}</label>
                                  <input
                                    id={`tts-http-${resource}-label`}
                                    value={endpoint.label_path}
                                    onChange={(event) => updateHttpCatalogEndpoint(resource, { label_path: event.target.value })}
                                    placeholder="name"
                                    spellCheck={false}
                                  />
                                </div>
                              </div>
                              <details className="ops-tts-http-endpoint__optional">
                                <summary>{t("opsTtsAi.httpOptionalMetadata")}</summary>
                                <div className="ops-tts-grid">
                                  {(["languages_path", "models_path", "voices_path", "gender_path", "description_path", "capabilities_path"] as const).map((field) => (
                                    <div className="ops-form-field" key={field}>
                                      <label htmlFor={`tts-http-${resource}-${field}`}>{t(`opsTtsAi.http${field.replace(/_path$/, "").replace(/(^|_)(.)/g, (_match, _prefix, letter) => String(letter).toUpperCase())}Path`)}</label>
                                      <input
                                        id={`tts-http-${resource}-${field}`}
                                        value={endpoint[field]}
                                        onChange={(event) => updateHttpCatalogEndpoint(resource, { [field]: event.target.value })}
                                        placeholder={`data.${field.replace("_path", "")}`}
                                        spellCheck={false}
                                      />
                                    </div>
                                  ))}
                                </div>
                              </details>
                            </fieldset>
                          );
                        })}
                      </div>
                    </details>

                    <details className="ops-tts-http-mapping">
                      <summary>
                        <span>{t("opsTtsAi.httpSynthesisMappingTitle")}</span>
                        <small>{t("opsTtsAi.httpSynthesisMappingHint")}</small>
                      </summary>
                      <div className="ops-tts-grid ops-tts-http-mapping__body">
                        <div className="ops-form-field ops-tts-span-2">
                          <label htmlFor="tts-http-synthesis-path">{t("opsTtsAi.httpSynthesisPath")}</label>
                          <input
                            id="tts-http-synthesis-path"
                            value={form.httpConnector.synthesisPath}
                            onChange={(event) => updateHttpConnector({ synthesisPath: event.target.value })}
                            placeholder="/audio/speech"
                            spellCheck={false}
                          />
                        </div>
                        <div className="ops-form-field">
                          <label htmlFor="tts-http-synthesis-method">{t("opsTtsAi.httpSynthesisMethod")}</label>
                          <select
                            id="tts-http-synthesis-method"
                            value={form.httpConnector.synthesisMethod}
                            onChange={(event) => updateHttpConnector({ synthesisMethod: event.target.value })}
                          >
                            <option value="POST">POST</option>
                            <option value="PUT">PUT</option>
                          </select>
                        </div>
                        <div className="ops-form-field">
                          <label htmlFor="tts-http-content-type">{t("opsTtsAi.httpContentType")}</label>
                          <select
                            id="tts-http-content-type"
                            value={form.httpConnector.synthesisContentType}
                            onChange={(event) => updateHttpConnector({ synthesisContentType: event.target.value })}
                          >
                            <option value="application/json">application/json</option>
                            <option value="application/x-www-form-urlencoded">application/x-www-form-urlencoded</option>
                          </select>
                        </div>
                        <div className="ops-form-field ops-tts-span-2">
                          <label htmlFor="tts-http-body">{t("opsTtsAi.httpRequestBody")}</label>
                          <textarea
                            id="tts-http-body"
                            rows={6}
                            value={form.httpConnector.synthesisBody}
                            onChange={(event) => updateHttpConnector({ synthesisBody: event.target.value })}
                            spellCheck={false}
                          />
                          <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.httpRequestBodyHint")}</p>
                        </div>
                        <div className="ops-form-field">
                          <label htmlFor="tts-http-response-type">{t("opsTtsAi.httpResponseType")}</label>
                          <select
                            id="tts-http-response-type"
                            value={form.httpConnector.synthesisResponseType}
                            onChange={(event) => updateHttpConnector({ synthesisResponseType: event.target.value as HttpConnectorResponseType })}
                          >
                            <option value="binary">{t("opsTtsAi.httpResponseBinary")}</option>
                            <option value="json_base64">{t("opsTtsAi.httpResponseBase64")}</option>
                            <option value="json_url">{t("opsTtsAi.httpResponseUrl")}</option>
                            <option value="async_json">{t("opsTtsAi.httpResponseAsync")}</option>
                          </select>
                        </div>
                        <div className="ops-form-field">
                          <label htmlFor="tts-http-audio-path">{t("opsTtsAi.httpAudioPath")}</label>
                          <input
                            id="tts-http-audio-path"
                            value={form.httpConnector.synthesisAudioPath}
                            onChange={(event) => updateHttpConnector({ synthesisAudioPath: event.target.value })}
                            placeholder={form.httpConnector.synthesisResponseType === "binary" ? "(response body)" : "data.audio"}
                            spellCheck={false}
                          />
                        </div>
                        <div className="ops-form-field">
                          <label htmlFor="tts-http-mime-type">{t("opsTtsAi.httpMimeType")}</label>
                          <input
                            id="tts-http-mime-type"
                            value={form.httpConnector.synthesisMimeType}
                            onChange={(event) => updateHttpConnector({ synthesisMimeType: event.target.value })}
                            placeholder="audio/mpeg"
                            spellCheck={false}
                          />
                        </div>
                        {form.httpConnector.synthesisResponseType !== "binary" ? (
                          <>
                            <div className="ops-form-field">
                              <label htmlFor="tts-http-mime-path">{t("opsTtsAi.httpMimePath")}</label>
                              <input
                                id="tts-http-mime-path"
                                value={form.httpConnector.synthesisMimeTypePath}
                                onChange={(event) => updateHttpConnector({ synthesisMimeTypePath: event.target.value })}
                                placeholder="data.mime_type"
                                spellCheck={false}
                              />
                            </div>
                            <div className="ops-form-field">
                              <label htmlFor="tts-http-duration-path">{t("opsTtsAi.httpDurationPath")}</label>
                              <input
                                id="tts-http-duration-path"
                                value={form.httpConnector.synthesisDurationPath}
                                onChange={(event) => updateHttpConnector({ synthesisDurationPath: event.target.value })}
                                placeholder="data.duration"
                                spellCheck={false}
                              />
                            </div>
                            <div className="ops-form-field">
                              <label htmlFor="tts-http-file-extension">{t("opsTtsAi.httpFileExtension")}</label>
                              <input
                                id="tts-http-file-extension"
                                value={form.httpConnector.synthesisFileExtension}
                                onChange={(event) => updateHttpConnector({ synthesisFileExtension: event.target.value })}
                                placeholder="mp3"
                                spellCheck={false}
                              />
                            </div>
                          </>
                        ) : null}
                        {form.httpConnector.synthesisResponseType === "async_json" ? (
                          <div className="ops-tts-http-polling ops-tts-span-2">
                            <strong>{t("opsTtsAi.httpPollingTitle")}</strong>
                            <div className="ops-tts-grid">
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-job-id-path">{t("opsTtsAi.httpJobIdPath")}</label>
                                <input id="tts-http-job-id-path" value={form.httpConnector.pollingJobIdPath} onChange={(event) => updateHttpConnector({ pollingJobIdPath: event.target.value })} placeholder="job_id" spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-path">{t("opsTtsAi.httpPollPath")}</label>
                                <input id="tts-http-poll-path" value={form.httpConnector.pollingPath} onChange={(event) => updateHttpConnector({ pollingPath: event.target.value })} placeholder="/jobs/{{job_id}}" spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-method">{t("opsTtsAi.httpPollMethod")}</label>
                                <select
                                  id="tts-http-poll-method"
                                  value={form.httpConnector.pollingMethod}
                                  onChange={(event) => updateHttpConnector({ pollingMethod: event.target.value })}
                                >
                                  <option value="GET">GET</option>
                                  <option value="POST">POST</option>
                                  <option value="PUT">PUT</option>
                                </select>
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-content-type">{t("opsTtsAi.httpPollContentType")}</label>
                                <select
                                  id="tts-http-poll-content-type"
                                  value={form.httpConnector.pollingContentType}
                                  onChange={(event) => updateHttpConnector({ pollingContentType: event.target.value })}
                                >
                                  <option value="application/json">application/json</option>
                                  <option value="application/x-www-form-urlencoded">application/x-www-form-urlencoded</option>
                                </select>
                              </div>
                              {form.httpConnector.pollingMethod !== "GET" ? (
                                <div className="ops-form-field ops-tts-span-2">
                                  <label htmlFor="tts-http-poll-body">{t("opsTtsAi.httpPollBody")}</label>
                                  <textarea
                                    id="tts-http-poll-body"
                                    rows={5}
                                    value={form.httpConnector.pollingBody}
                                    onChange={(event) => updateHttpConnector({ pollingBody: event.target.value })}
                                    placeholder={'{ "method": "getExportStatus", "input": { "projectExportId": "{{job_id}}" } }'}
                                    spellCheck={false}
                                  />
                                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.httpPollBodyHint")}</p>
                                </div>
                              ) : null}
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-status-path">{t("opsTtsAi.httpStatusPath")}</label>
                                <input id="tts-http-status-path" value={form.httpConnector.pollingStatusPath} onChange={(event) => updateHttpConnector({ pollingStatusPath: event.target.value })} placeholder="status" spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-success-values">{t("opsTtsAi.httpSuccessValues")}</label>
                                <input id="tts-http-success-values" value={form.httpConnector.pollingSuccessValues} onChange={(event) => updateHttpConnector({ pollingSuccessValues: event.target.value })} spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-failure-values">{t("opsTtsAi.httpFailureValues")}</label>
                                <input id="tts-http-failure-values" value={form.httpConnector.pollingFailureValues} onChange={(event) => updateHttpConnector({ pollingFailureValues: event.target.value })} spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-interval">{t("opsTtsAi.httpPollInterval")}</label>
                                <input id="tts-http-poll-interval" inputMode="decimal" value={form.httpConnector.pollingIntervalSeconds} onChange={(event) => updateHttpConnector({ pollingIntervalSeconds: event.target.value })} placeholder="2" spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-attempts">{t("opsTtsAi.httpPollAttempts")}</label>
                                <input id="tts-http-poll-attempts" inputMode="numeric" value={form.httpConnector.pollingMaxAttempts} onChange={(event) => updateHttpConnector({ pollingMaxAttempts: event.target.value })} placeholder="30" spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-response-type">{t("opsTtsAi.httpPollResponseType")}</label>
                                <select
                                  id="tts-http-poll-response-type"
                                  value={form.httpConnector.pollingResponseType}
                                  onChange={(event) => updateHttpConnector({ pollingResponseType: event.target.value as Exclude<HttpConnectorResponseType, "async_json"> })}
                                >
                                  <option value="json_url">{t("opsTtsAi.httpResponseUrl")}</option>
                                  <option value="json_base64">{t("opsTtsAi.httpResponseBase64")}</option>
                                  <option value="binary">{t("opsTtsAi.httpResponseBinary")}</option>
                                </select>
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-audio-path">{t("opsTtsAi.httpPollAudioPath")}</label>
                                <input id="tts-http-poll-audio-path" value={form.httpConnector.pollingAudioPath} onChange={(event) => updateHttpConnector({ pollingAudioPath: event.target.value })} placeholder="data.audio_url" spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-mime-path">{t("opsTtsAi.httpPollMimePath")}</label>
                                <input id="tts-http-poll-mime-path" value={form.httpConnector.pollingMimeTypePath} onChange={(event) => updateHttpConnector({ pollingMimeTypePath: event.target.value })} placeholder="data.mime_type" spellCheck={false} />
                              </div>
                              <div className="ops-form-field">
                                <label htmlFor="tts-http-poll-duration-path">{t("opsTtsAi.httpPollDurationPath")}</label>
                                <input id="tts-http-poll-duration-path" value={form.httpConnector.pollingDurationPath} onChange={(event) => updateHttpConnector({ pollingDurationPath: event.target.value })} placeholder="data.duration" spellCheck={false} />
                              </div>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </details>
                  </>
                ) : null}

                <details className="ops-tts-http-curl">
                  <summary>{t("opsTtsAi.httpCurlTitle")}</summary>
                  <p>{t("opsTtsAi.httpCurlHint")}</p>
                  <textarea
                    rows={3}
                    value={curlImportDraft}
                    onChange={(event) => {
                      setCurlImportDraft(event.target.value);
                      setCurlImportFeedback(null);
                    }}
                    placeholder={t("opsTtsAi.httpCurlPlaceholder")}
                    spellCheck={false}
                    aria-label={t("opsTtsAi.httpCurlTitle")}
                  />
                  <div className="ops-tts-http-curl__actions">
                    <button type="button" className="ops-tts-action-btn" onClick={importHttpCurl} disabled={!curlImportDraft.trim() || testing}>
                      {t("opsTtsAi.httpCurlImport")}
                    </button>
                    {curlImportFeedback ? (
                      <span className={`ops-tts-http-curl__feedback ${curlImportFeedback.ok ? "is-ok" : "is-error"}`} role={curlImportFeedback.ok ? "status" : "alert"}>
                        {curlImportFeedback.message}
                      </span>
                    ) : null}
                  </div>
                </details>
              </div>
            ) : null}
          </section>
        ) : null}

        {isLocal && !localDraftNeedsProvider ? (
          <section className="ops-tts-section ops-tts-section--install">
            <header
              className="ops-tts-section__head"
              title={recipe ? t(recipe.hintKey) : t("opsTtsAi.sectionInstallHint")}
            >
              <h3>{t("opsTtsAi.sectionInstall")}</h3>
            </header>
            <div className="ops-tts-install-primary">
              <div className="ops-form-field">
                <label htmlFor="tts-ai-install">{t("opsTtsAi.installCommand")}</label>
                <div className="ops-tts-install-command-bar">
                  <input
                    id="tts-ai-install"
                    value={form.installCommand}
                    onChange={(e) => setForm({ ...form, installCommand: e.target.value })}
                    placeholder={t("opsTtsAi.installCommandPlaceholder")}
                    title={t("opsTtsAi.installCommandHint")}
                    spellCheck={false}
                  />
                  <button
                    type="button"
                    className="ops-tts-action-btn"
                    onClick={() => void copyInstallCommand()}
                    disabled={!form.installCommand.trim()}
                    aria-label={copied ? t("opsTtsAi.copied") : t("opsTtsAi.copyInstall")}
                    title={copied ? t("opsTtsAi.copied") : t("opsTtsAi.copyInstall")}
                  >
                    <TtsSetupActionIcon kind="copy" />
                    <span className="ops-tts-editor-actions__label">
                      {copied ? t("opsTtsAi.copied") : t("opsTtsAi.copyInstall")}
                    </span>
                  </button>
                  <AsyncButton
                    className="ops-tts-action-btn is-primary"
                    pending={asyncAction.isPending("install")}
                    pendingLabel={t("opsTtsAi.installing")}
                    leadingIcon={<TtsSetupActionIcon kind="install" />}
                    onClick={() => void asyncAction.run("install", () => onInstall())}
                    disabled={
                      saving ||
                      testing ||
                      (!form.installCommand.trim() && !form.packageName.trim() && !form.repoUrl.trim())
                    }
                    aria-label={
                      installing
                        ? t("opsTtsAi.installing")
                        : installResult?.already_satisfied || runtime?.last_install?.already_satisfied
                          ? t("opsTtsAi.useInstalled")
                          : t("opsTtsAi.install")
                    }
                    title={
                      installing
                        ? t("opsTtsAi.installing")
                        : installResult?.already_satisfied || runtime?.last_install?.already_satisfied
                          ? t("opsTtsAi.useInstalled")
                          : t("opsTtsAi.install")
                    }
                  >
                    <span className="ops-tts-editor-actions__label">
                      {installResult?.already_satisfied || runtime?.last_install?.already_satisfied
                        ? t("opsTtsAi.useInstalled")
                        : t("opsTtsAi.install")}
                    </span>
                  </AsyncButton>
                </div>
                <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.installCommandHint")}</p>
              </div>
              <div className="ops-tts-install-actions">
                {hadInstall || installResult?.already_satisfied ? (
                  <AsyncButton
                    className="ops-tts-action-btn"
                    pending={asyncAction.isPending("install")}
                    pendingLabel={t("opsTtsAi.installing")}
                    leadingIcon={<TtsSetupActionIcon kind="reinstall" />}
                    onClick={() => void asyncAction.run("install", () => onInstall({ forceReinstall: true }))}
                    disabled={
                      saving ||
                      testing ||
                      (!form.installCommand.trim() && !form.packageName.trim() && !form.repoUrl.trim())
                    }
                    aria-label={installing ? t("opsTtsAi.installing") : t("opsTtsAi.reinstallUpgrade")}
                    title={installing ? t("opsTtsAi.installing") : t("opsTtsAi.reinstallUpgrade")}
                  >
                    <span className="ops-tts-editor-actions__label">{t("opsTtsAi.reinstallUpgrade")}</span>
                  </AsyncButton>
                ) : null}
                {form.packageName ? (
                  <span className="ops-tts-chip is-muted">
                    {t("opsTtsAi.packageLabel")}: {form.packageName}
                  </span>
                ) : null}
                {runtime?.last_install?.at ? (
                  <span className="ops-tts-chip is-muted" title={runtime.last_install.detail || undefined}>
                    {t("opsTtsAi.lastInstallAt")}: {runtime.last_install.at}
                    {runtime.last_install.already_satisfied ? ` · ${t("opsTtsAi.alreadySatisfiedShort")}` : ""}
                  </span>
                ) : null}
              </div>
              {installing ? (
                <div className="ops-tts-test-banner is-busy" role="status">
                  <span className="ops-tts-test-banner__icon" aria-hidden="true">
                    <svg viewBox="0 0 20 20">
                      <circle
                        cx="10"
                        cy="10"
                        r="6.25"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.75"
                        strokeDasharray="28 12"
                      />
                    </svg>
                  </span>
                  <div className="ops-tts-test-banner__body">
                    <strong>
                      {t("opsTtsAi.installing")}
                      {installResult?.command ? ` · ${installResult.command}` : ""}
                    </strong>
                    <span className="ops-tts-test-banner__message">
                      {installResult?.detail && installResult.detail !== t("opsTtsAi.installing")
                        ? installResult.detail
                        : t("opsTtsAi.installingHint")}
                    </span>
                    {installResult?.log_tail ? (
                      <pre className="ops-tts-install-log">{installResult.log_tail}</pre>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {!installing && installResult?.ok ? (
                <div className="ops-tts-test-banner is-ok" role="status">
                  <span className="ops-tts-test-banner__icon" aria-hidden="true">
                    <svg viewBox="0 0 20 20">
                      <path
                        d="M5 10.2 8.2 13.5 15 6.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.9"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                  <div className="ops-tts-test-banner__body">
                    <div className="ops-tts-test-banner__title-row">
                      <strong>
                        {installResult.already_satisfied
                          ? t("opsTtsAi.installAlready")
                          : t("opsTtsAi.installOk")}
                      </strong>
                      {(form.packageName.trim() || installResult.command) ? (
                        <span className="ops-tts-test-banner__chip">
                          {form.packageName.trim() || installResult.command}
                        </span>
                      ) : null}
                    </div>
                    <span className="ops-tts-test-banner__message">
                      {installResult.already_satisfied
                        ? t("opsTtsAi.installAlreadyHint")
                        : installResult.detail}
                    </span>
                    <span className="ops-tts-test-banner__hint">{t("opsTtsAi.installSuccessHint")}</span>
                  </div>
                  <button
                    type="button"
                    className="ops-tts-test-banner__dismiss"
                    aria-label={t("common.close")}
                    title={t("common.close")}
                    onClick={() => setInstallResult(null)}
                  >
                    <svg viewBox="0 0 20 20" aria-hidden="true">
                      <path
                        d="M6.5 6.5 13.5 13.5M13.5 6.5 6.5 13.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.75"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                </div>
              ) : null}
              {!installing && installResult && !installResult.ok ? (
                <div className="ops-tts-test-banner is-error" role="alert">
                  <span className="ops-tts-test-banner__icon" aria-hidden="true">
                    <svg viewBox="0 0 20 20">
                      <circle cx="10" cy="10" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.75" />
                      <path
                        d="M10 7.2v3.6M10 13.2h.01"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.75"
                        strokeLinecap="round"
                      />
                    </svg>
                  </span>
                  <div className="ops-tts-test-banner__body">
                    <strong>
                      {t("opsTtsAi.installFail")}
                      {installResult.command ? ` · ${installResult.command}` : ""}
                    </strong>
                    <span className="ops-tts-test-banner__message">{installResult.detail}</span>
                    {installResult.log_tail ? (
                      <pre className="ops-tts-install-log">{installResult.log_tail}</pre>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className="ops-tts-test-banner__dismiss"
                    aria-label={t("common.close")}
                    title={t("common.close")}
                    onClick={() => setInstallResult(null)}
                  >
                    <svg viewBox="0 0 20 20" aria-hidden="true">
                      <path
                        d="M6.5 6.5 13.5 13.5M13.5 6.5 6.5 13.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.75"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                </div>
              ) : null}
            </div>
            <div className="ops-tts-grid ops-tts-install-fields">
              <div className="ops-form-field">
                <label htmlFor="tts-ai-package">{t("opsTtsAi.packageName")}</label>
                <input
                  id="tts-ai-package"
                  value={form.packageName}
                  onChange={(e) => setForm({ ...form, packageName: e.target.value })}
                  placeholder={t("opsTtsAi.packageNamePlaceholder")}
                  title={t("opsTtsAi.packageNameHint")}
                  spellCheck={false}
                />
                <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.packageNameHint")}</p>
              </div>
              <div className="ops-form-field">
                <label htmlFor="tts-ai-repo">{t("opsTtsAi.repoUrl")}</label>
                <input
                  id="tts-ai-repo"
                  value={form.repoUrl}
                  onChange={(e) => applyRepoUrl(e.target.value)}
                  placeholder={t("opsTtsAi.repoUrlPlaceholder")}
                  title={t("opsTtsAi.repoUrlHint")}
                  spellCheck={false}
                />
                <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.repoUrlHint")}</p>
              </div>
              <div className="ops-form-field ops-tts-span-2">
                <label htmlFor="tts-ai-extra">{t("opsTtsAi.extraRequirement")}</label>
                <input
                  id="tts-ai-extra"
                  value={form.extraRequirement}
                  onChange={(e) => setForm({ ...form, extraRequirement: e.target.value })}
                  placeholder={t("opsTtsAi.extraRequirementPlaceholder")}
                  title={t("opsTtsAi.extraRequirementHint")}
                />
                <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.extraRequirementHint")}</p>
              </div>
            </div>
          </section>
        ) : null}

        {(isLocal || isCloud || isHttp) && !localDraftNeedsProvider ? (
          <section className="ops-tts-section">
            <header
              className="ops-tts-section__head ops-tts-section__head--with-action"
              title={t("opsTtsAi.sectionVoiceHint")}
            >
              <div>
                <h3>{t("opsTtsAi.sectionVoice")}</h3>
                <p>{t("opsTtsAi.sectionVoiceHint")}</p>
              </div>
              <button
                className={`ops-tts-catalog-refresh${
                  catalogRefreshPhase === "preparing"
                    ? " is-preparing"
                    : catalogRefreshPhase === "loading"
                      ? " is-loading"
                      : ""
                }`}
                type="button"
                onClick={() => void onRefreshCatalog()}
                disabled={catalogRefreshBusy || testing}
                aria-busy={catalogRefreshBusy}
                aria-live="polite"
                data-phase={catalogRefreshPhase}
              >
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path
                    d="M15.2 7.1A5.8 5.8 0 1 0 15 13.2M15.2 7.1V3.8m0 3.3h-3.3"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                {catalogRefreshPhase === "preparing"
                  ? t("opsTtsAi.catalogPreparing")
                  : catalogRefreshPhase === "loading"
                    ? t("opsTtsAi.catalogLoading")
                    : t("opsTtsAi.catalogRefresh")}
              </button>
            </header>
              {catalog ? (
                <>
                  <div className="ops-tts-status ops-tts-status--compact" aria-label={t("opsTtsAi.providerMetaLabel")}>
                    <span className={`ops-tts-chip ${catalogDiscoveryStatus === "unavailable" ? "is-warn" : "is-ok"}`}>
                      {t("opsTtsAi.catalogSource")}: {catalog.source || "—"}
                    </span>
                    {catalog.discovery ? (
                      <span className={`ops-tts-chip is-${catalogDiscoveryStatus === "complete" ? "ok" : "warn"}`}>
                        {t(discoveryLabelKey)}
                      </span>
                    ) : null}
                    {catalogStale ? <span className="ops-tts-chip is-warn">{t("opsTtsAi.catalogStale")}</span> : null}
                    {allCatalogVoices.length ? (
                      <span className="ops-tts-chip is-muted">
                        {t("opsTtsAi.catalogVoicesCount")}: {allCatalogVoices.length}
                      </span>
                    ) : null}
                    {allCatalogModels.length ? (
                      <span className="ops-tts-chip is-muted">
                        {t("opsTtsAi.catalogModelsCount")}: {allCatalogModels.length}
                      </span>
                    ) : null}
                    {allCatalogLanguages.length ? (
                      <span className="ops-tts-chip is-muted">
                        {t("opsTtsAi.catalogLanguagesCount")}: {allCatalogLanguages.length}
                      </span>
                    ) : null}
                    {catalog.sample_rate ? (
                      <span className="ops-tts-chip is-muted">
                        {t("opsTtsAi.sampleRate")}: {catalog.sample_rate} Hz
                      </span>
                    ) : null}
                    {catalog.discovery?.config_fingerprint ? (
                      <span className="ops-tts-chip is-muted" title={t("opsTtsAi.httpFingerprintHint")}>
                        {t("opsTtsAi.httpFingerprint")}: {catalog.discovery.config_fingerprint.slice(0, 8)}
                      </span>
                    ) : null}
                  </div>
                  {catalogWarnings.length ? (
                    <div className="ops-tts-catalog-notice is-warn" role="status">
                      <strong>{t("opsTtsAi.catalogWarningTitle")}</strong>
                      <span>{catalogWarnings.join(" · ")}</span>
                    </div>
                  ) : null}
                </>
              ) : isRemoteCatalogProvider && testResult?.ok ? (
                <div className="ops-tts-catalog-notice is-muted" role="status">
                  <strong>{t("opsTtsAi.catalogUnavailableTitle")}</strong>
                  <span>{t("opsTtsAi.catalogUnavailableHint")}</span>
                </div>
              ) : isRemoteCatalogProvider ? (
                <div className="ops-tts-catalog-notice is-muted" role="status">
                  <strong>{t("opsTtsAi.catalogNotLoadedTitle")}</strong>
                  <span>{t("opsTtsAi.catalogNotLoadedHint")}</span>
                </div>
              ) : null}
              <div className="ops-tts-grid">
                {fieldCaps.voice ? (
                  <div className="ops-form-field ops-tts-span-2">
                    <label htmlFor="tts-ai-voice">{t("opsTtsAi.voiceId")}</label>
                    {isRemoteCatalogProvider && allCatalogVoices.length ? (
                      <>
                        <select
                          id="tts-ai-voice"
                          value={remoteVoiceSelectValue}
                          onChange={(e) =>
                            setForm({
                              ...form,
                              voiceId: e.target.value === TTS_CATALOG_MANUAL_VALUE ? "" : e.target.value
                            })
                          }
                        >
                          <option value={TTS_CATALOG_MANUAL_VALUE}>{t("opsTtsAi.catalogManualOption")}</option>
                          {allCatalogVoices.map((voice) => {
                            const compatible = remoteCatalogVoices.some((candidate) =>
                              sameCatalogId(candidate.id, voice.id)
                            );
                            return (
                              <option key={voice.id} value={voice.id} title={voice.description || undefined}>
                                {voice.label || voice.id}
                                {voice.gender ? ` · ${voice.gender}` : ""}
                                {compatible ? "" : ` — ${t("opsTtsAi.catalogMayNotMatch")}`}
                              </option>
                            );
                          })}
                        </select>
                        <p className="ops-tts-field-hint ops-tts-field-hint--quiet">
                          {t("opsTtsAi.catalogAllChoicesHint")
                            .replace("{total}", String(allCatalogVoices.length))
                            .replace("{compatible}", String(remoteCatalogVoices.length))}
                        </p>
                        {remoteVoiceSelectValue === TTS_CATALOG_MANUAL_VALUE ? (
                          <input
                            className="ops-tts-catalog-manual-input"
                            value={form.voiceId}
                            onChange={(e) => setForm({ ...form, voiceId: e.target.value })}
                            placeholder={t("opsTtsAi.voiceOptionalPlaceholder")}
                            spellCheck={false}
                          />
                        ) : null}
                      </>
                    ) : catalogVoices ? (
                      <select
                        id="tts-ai-voice"
                        value={
                          catalogVoices.some((v) => v.id === form.voiceId)
                            ? form.voiceId
                            : catalog?.default_voice_id || catalogVoices[0]?.id || ""
                        }
                        onChange={(e) => setForm({ ...form, voiceId: e.target.value })}
                      >
                        {catalogVoices.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.label || v.id}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id="tts-ai-voice"
                        value={form.voiceId}
                        onChange={(e) => setForm({ ...form, voiceId: e.target.value })}
                        placeholder={
                          activeProvider === "edge"
                            ? t("opsTtsAi.voiceIdPlaceholder")
                            : t("opsTtsAi.voiceOptionalPlaceholder")
                        }
                        title={
                          catalogVoices
                            ? t("opsTtsAi.voiceFromCatalog")
                            : activeProvider === "edge"
                              ? t("opsTtsAi.voicePresetHint")
                              : t("opsTtsAi.voiceAdaptiveHint")
                        }
                        spellCheck={false}
                      />
                    )}
                    <p className="ops-tts-field-hint ops-tts-field-hint--quiet">
                      {isLucylabJsonRpc
                        ? t("opsTtsAi.httpLucylabVoiceHint")
                        : (isRemoteCatalogProvider && allCatalogVoices.length) || catalogVoices
                        ? t("opsTtsAi.voiceFromCatalog")
                        : activeProvider === "edge"
                          ? t("opsTtsAi.voicePresetHint")
                          : t("opsTtsAi.voiceAdaptiveHint")}
                    </p>
                  </div>
                ) : null}
                <div className="ops-form-field">
                  <label htmlFor="tts-ai-rate">{t("opsTtsAi.speakingRate")}</label>
                  <input
                    id="tts-ai-rate"
                    value={form.speakingRate}
                    onChange={(e) => setForm({ ...form, speakingRate: e.target.value })}
                    placeholder={t("opsTtsAi.speakingRatePlaceholder")}
                    title={t("opsTtsAi.speakingRateHint")}
                  />
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.speakingRateHint")}</p>
                </div>
                <div className="ops-form-field">
                  <label htmlFor="tts-ai-lang">{t("opsTtsAi.languageCode")}</label>
                  {isRemoteCatalogProvider && remoteCatalogLanguages.length ? (
                    <>
                      <select
                        id="tts-ai-lang"
                        value={remoteLanguageSelectValue}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            languageCode: e.target.value === TTS_CATALOG_MANUAL_VALUE ? "" : e.target.value
                          })
                        }
                      >
                        <option value={TTS_CATALOG_MANUAL_VALUE}>{t("opsTtsAi.catalogManualOption")}</option>
                        {remoteCatalogLanguages.map((language) => (
                          <option key={language.code} value={language.code}>
                            {language.label || language.code} · {language.code}
                          </option>
                        ))}
                      </select>
                      {remoteLanguageSelectValue === TTS_CATALOG_MANUAL_VALUE ? (
                        <input
                          className="ops-tts-catalog-manual-input"
                          value={form.languageCode}
                          onChange={(e) => setForm({ ...form, languageCode: e.target.value })}
                          placeholder={t("opsTtsAi.languageCodePlaceholder")}
                          spellCheck={false}
                        />
                      ) : null}
                    </>
                  ) : (
                    <input
                      id="tts-ai-lang"
                      value={form.languageCode}
                      onChange={(e) => setForm({ ...form, languageCode: e.target.value })}
                      placeholder={t("opsTtsAi.languageCodePlaceholder")}
                      title={t("opsTtsAi.languageCodeHint")}
                    />
                  )}
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.languageCodeHint")}</p>
                  {isRemoteCatalogProvider &&
                  allCatalogLanguages.length > 0 &&
                  remoteCatalogLanguages.length === 0 ? (
                    <p className="ops-tts-field-hint is-warn">{t("opsTtsAi.catalogNoCompatibleChoices")}</p>
                  ) : null}
                </div>
                {fieldCaps.model && !isLucylabJsonRpc ? (
                  <div className="ops-form-field ops-tts-span-2">
                    <label htmlFor="tts-ai-model">{t("opsTtsAi.modelId")}</label>
                    {engineModelOptions || (isRemoteCatalogProvider ? allCatalogModels.length : catalogModels) ? (
                      <select
                        id="tts-ai-model"
                        value={
                          engineModelOptions
                            ? engineModelOptions.some((engine) => engine.id === form.modelId)
                              ? form.modelId
                              : catalogModels?.[0] || ""
                            : isRemoteCatalogProvider
                              ? remoteModelSelectValue
                              : catalogModels?.includes(form.modelId)
                                ? form.modelId
                                : catalogModels?.[0] || ""
                        }
                        onChange={(e) =>
                          setForm({
                            ...form,
                            modelId: e.target.value === TTS_CATALOG_MANUAL_VALUE ? "" : e.target.value
                          })
                        }
                      >
                        {engineModelOptions
                          ? engineModelOptions.map((engine) => (
                              <option key={engine.id} value={engine.id} disabled={!engine.selectable}>
                                {engine.label}
                                {engine.selectable ? "" : ` — ${t("opsTtsAi.engineNotReadyShort")}`}
                              </option>
                            ))
                          : isRemoteCatalogProvider
                            ? [
                                { id: TTS_CATALOG_MANUAL_VALUE, label: t("opsTtsAi.catalogManualOption") },
                                ...allCatalogModels
                              ].map((model) => (
                                <option key={model.id} value={model.id} title={model.description || undefined}>
                                  {model.label || model.id}
                                  {model.id === TTS_CATALOG_MANUAL_VALUE ||
                                  remoteCatalogModels.some((candidate) => sameCatalogId(candidate.id, model.id))
                                    ? ""
                                    : ` — ${t("opsTtsAi.catalogMayNotMatch")}`}
                                </option>
                              ))
                            : catalogModels?.map((m) => (
                              <option key={m} value={m}>
                                {m}
                              </option>
                            ))}
                      </select>
                    ) : (
                      <input
                        id="tts-ai-model"
                        value={form.modelId}
                        onChange={(e) => setForm({ ...form, modelId: e.target.value })}
                        placeholder={t("opsTtsAi.modelIdPlaceholder")}
                        title={t("opsTtsAi.modelIdHint")}
                        spellCheck={false}
                      />
                    )}
                    <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.modelIdHint")}</p>
                    {isRemoteCatalogProvider && allCatalogModels.length ? (
                      <p className="ops-tts-field-hint ops-tts-field-hint--quiet">
                        {t("opsTtsAi.catalogAllChoicesHint")
                          .replace("{total}", String(allCatalogModels.length))
                          .replace("{compatible}", String(remoteCatalogModels.length))}
                      </p>
                    ) : null}
                    {remoteCatalogSelectionMismatch ? (
                      <p className="ops-tts-field-hint is-warn">{t("opsTtsAi.catalogSelectionMismatch")}</p>
                    ) : null}
                    {isRemoteCatalogProvider &&
                    allCatalogModels.length > 0 &&
                    remoteModelSelectValue === TTS_CATALOG_MANUAL_VALUE ? (
                      <input
                        className="ops-tts-catalog-manual-input"
                        value={form.modelId}
                        onChange={(e) => setForm({ ...form, modelId: e.target.value })}
                        placeholder={t("opsTtsAi.modelIdPlaceholder")}
                        spellCheck={false}
                      />
                    ) : null}
                    {isRemoteCatalogProvider && selectedCatalogModel ? (
                      <div className="ops-tts-catalog-detail" role="note">
                        <strong>{selectedCatalogModel.label || selectedCatalogModel.id}</strong>
                        {selectedCatalogModel.description ? <span>{selectedCatalogModel.description}</span> : null}
                        {selectedCatalogModel.languages?.length ? (
                          <small>{t("opsTtsAi.catalogLanguagesLabel")}: {selectedCatalogModel.languages.join(", ")}</small>
                        ) : null}
                        {selectedCatalogModel.voices?.length ? (
                          <small>{t("opsTtsAi.catalogVoicesLabel")}: {selectedCatalogModel.voices.join(", ")}</small>
                        ) : null}
                        {selectedCatalogModel.capabilities?.length ? (
                          <small>{t("opsTtsAi.catalogCapabilitiesLabel")}: {selectedCatalogModel.capabilities.join(", ")}</small>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : isLucylabJsonRpc ? (
                  <div className="ops-tts-catalog-notice is-muted ops-tts-span-2" role="note">
                    <strong>{t("opsTtsAi.httpLucylabNoModelTitle")}</strong>
                    <span>{t("opsTtsAi.httpLucylabNoModelHint")}</span>
                  </div>
                ) : null}
              </div>
              {isOmniEngine ? (
                <div className="ops-tts-engine-catalog">
                  <div className="ops-tts-engine-catalog__head">
                    <div>
                      <strong>{t("opsTtsAi.engineCatalogTitle")}</strong>
                      <p>{t("opsTtsAi.engineCatalogHint")}</p>
                      <div
                        className="ops-tts-engine-catalog__meta"
                        aria-label={t("opsTtsAi.engineSummaryLabel")}
                      >
                        <span><strong>{engineCatalog.length}</strong> {t("opsTtsAi.engineSummaryTotal")}</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="ops-tts-catalog-refresh"
                      onClick={() => void loadOmnivoiceEngines()}
                      disabled={engineCatalogLoading || installing}
                    >
                      <svg viewBox="0 0 20 20" aria-hidden="true">
                        <path
                          d="M15.2 7.1A5.8 5.8 0 1 0 15 13.2M15.2 7.1V3.8m0 3.3h-3.3"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.6"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      {engineCatalogLoading
                        ? t("opsTtsAi.engineCatalogLoading")
                        : t("opsTtsAi.engineCatalogRefresh")}
                    </button>
                  </div>
                  {engineCatalogError ? <div className="inline-error">{engineCatalogError}</div> : null}
                  <div
                    className="ops-tts-engine-tabs"
                    role="tablist"
                    aria-label={t("opsTtsAi.engineGroupTabsLabel")}
                  >
                    {engineGroups.map((group) => (
                      <button
                        type="button"
                        role="tab"
                        id={`tts-engine-tab-${group.id}`}
                        aria-controls={`tts-engine-panel-${group.id}`}
                        aria-selected={engineGroupTab === group.id}
                        className={engineGroupTab === group.id ? `is-active is-${group.id}` : `is-${group.id}`}
                        key={group.id}
                        onClick={() => {
                          setEngineGroupTab(group.id);
                          setEngineExpandedId(null);
                        }}
                      >
                        <span className={`ops-tts-engine-tabs__indicator is-${group.id}`} aria-hidden="true" />
                        <span>{group.label}</span>
                        <strong>{group.engines.length}</strong>
                      </button>
                    ))}
                  </div>
                  {activeEngineGroup ? (
                    <div
                      className="ops-tts-engine-tabpanel"
                      role="tabpanel"
                      id={`tts-engine-panel-${activeEngineGroup.id}`}
                      aria-labelledby={`tts-engine-tab-${activeEngineGroup.id}`}
                    >
                      <div className="ops-tts-engine-catalog__grid" role="list">
                        {activeEngineGroup.engines.map((engine) => {
                      const guideOpen = engineExpandedId === engine.id;
                      const activeInstall = engineInstallJob?.engine_id === engine.id ? engineInstallJob : null;
                      const category = engineCatalogCategory(engine);
                      const hasGuide =
                        engine.dependency_status !== "incompatible" &&
                        (engine.install_mode === "manual" || engine.install_mode === "external");
                      const hasDetails = Boolean(engine.install_hint);
                      const installingThisEngine = engineInstallingId === engine.id;
                      const installActionLabel = installingThisEngine
                        ? t("opsTtsAi.engineInstalling")
                        : t("opsTtsAi.engineInstall");
                      const guideActionLabel = guideOpen
                        ? t("opsTtsAi.engineHideGuide")
                        : engine.install_mode === "external"
                          ? t("opsTtsAi.engineConfigure")
                          : t("opsTtsAi.engineSetupGuide");
                      return (
                        <article className={`ops-tts-engine-card is-${category}`} key={engine.id} role="listitem">
                          <div className="ops-tts-engine-card__row">
                            <span className={`ops-tts-engine-card__indicator is-${category}`} aria-hidden="true" />
                            <div className="ops-tts-engine-card__identity">
                              <div className="ops-tts-engine-card__identity-top">
                                <strong>{engine.label}</strong>
                                {engine.estimated_size_gb ? (
                                  <span className="ops-tts-engine-card__size">~{engine.estimated_size_gb} GB</span>
                                ) : null}
                              </div>
                              <div className="ops-tts-engine-card__meta">
                                <span>{engine.id}</span>
                                <i aria-hidden="true" />
                                <span className={`is-${category}`}>
                                  {t(engineDependencyLabelKey(engine.dependency_status))}
                                </span>
                                <i aria-hidden="true" />
                                <span>
                                  {engine.adapter_status === "ready"
                                    ? t("opsTtsAi.engineAdapterReady")
                                    : t("opsTtsAi.engineAdapterPlanned")}
                                </span>
                              </div>
                            </div>
                            <div className="ops-tts-engine-card__controls">
                              {engine.installable ? (
                                <button
                                  type="button"
                                  className="ops-tts-engine-card__action is-icon is-primary"
                                  onClick={() => void onInstallEngine(engine)}
                                  disabled={installing || testing || engineInstallingId !== null}
                                  aria-label={installActionLabel}
                                  title={installActionLabel}
                                >
                                  <EngineCatalogActionIcon kind={installingThisEngine ? "loading" : "install"} />
                                </button>
                              ) : hasGuide ? (
                                <button
                                  type="button"
                                  className={`ops-tts-engine-card__action is-icon${guideOpen ? " is-active" : ""}`}
                                  aria-expanded={guideOpen}
                                  aria-label={guideActionLabel}
                                  title={guideActionLabel}
                                  onClick={() => setEngineExpandedId(guideOpen ? null : engine.id)}
                                >
                                  <EngineCatalogActionIcon
                                    kind={guideOpen
                                      ? "collapse"
                                      : engine.install_mode === "external"
                                        ? "server"
                                        : "guide"}
                                  />
                                </button>
                              ) : null}
                              {hasDetails && !hasGuide ? (
                                <button
                                  type="button"
                                  className={`ops-tts-engine-card__details-toggle${guideOpen ? " is-active" : ""}`}
                                  aria-expanded={guideOpen}
                                  aria-label={guideOpen
                                    ? t("opsTtsAi.engineHideDetails")
                                    : t("opsTtsAi.engineShowDetails")}
                                  title={guideOpen
                                    ? t("opsTtsAi.engineHideDetails")
                                    : t("opsTtsAi.engineShowDetails")}
                                  onClick={() => setEngineExpandedId(guideOpen ? null : engine.id)}
                                >
                                  <svg viewBox="0 0 20 20" aria-hidden="true">
                                    <circle cx="5" cy="10" r="1.15" />
                                    <circle cx="10" cy="10" r="1.15" />
                                    <circle cx="15" cy="10" r="1.15" />
                                  </svg>
                                </button>
                              ) : null}
                            </div>
                          </div>
                          {activeInstall ? (
                            <div
                              className={`ops-tts-engine-card__progress${
                                activeInstall.status === "failed" ? " is-error" : ""
                              }`}
                              aria-live="polite"
                            >
                              <div className="ops-tts-engine-card__progress-heading">
                                <span>{t(engineInstallStepLabelKey(activeInstall.step))}</span>
                                <strong>{activeInstall.progress}%</strong>
                              </div>
                              <progress max={100} value={activeInstall.progress} />
                              <p>
                                {activeInstall.status === "failed"
                                  ? activeInstall.error || activeInstall.detail
                                  : activeInstall.detail}
                              </p>
                            </div>
                          ) : null}
                          {guideOpen && engine.install_hint ? (
                            <p className="ops-tts-engine-card__detail">{engine.install_hint}</p>
                          ) : null}
                        </article>
                      );
                        })}
                        {activeEngineGroup.engines.length === 0 ? (
                          <p className="ops-tts-engine-tabpanel__empty">{t("opsTtsAi.engineGroupEmpty")}</p>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
          </section>
        ) : null}

        {(isLocal || isCloud || isHttp) && !localDraftNeedsProvider ? (
          <section className="ops-tts-section ops-tts-section--preview">
            <header className="ops-tts-section__head" title={t("opsTtsAi.sectionPreviewHint")}>
              <div>
                <h3>{t("opsTtsAi.sectionPreview")}</h3>
                <p>{t("opsTtsAi.sectionPreviewHint")}</p>
              </div>
              {previewMeta ? (
                <span className="ops-tts-chip is-ok" title={previewMeta.detail || undefined}>
                  {previewMeta.provider}
                  {previewMeta.resolvedVoiceId || previewMeta.requestedVoiceId
                    ? ` · ${previewMeta.resolvedVoiceId || previewMeta.requestedVoiceId}`
                    : ""}
                  {previewMeta.resolvedModelId || previewMeta.requestedModelId
                    ? ` · ${previewMeta.resolvedModelId || previewMeta.requestedModelId}`
                    : ""}
                  {` · ${previewMeta.duration.toFixed(1)}s`}
                </span>
              ) : null}
            </header>

            <div className="ops-tts-preview-body">
              <div className="ops-tts-preview-field">
                <div className="ops-tts-preview-field__top">
                  <label htmlFor="tts-ai-preview-text">{t("opsTtsAi.previewText")}</label>
                  <span className="ops-tts-preview-count" aria-live="polite">
                    {previewText.trim().length}/280
                  </span>
                </div>
                <textarea
                  id="tts-ai-preview-text"
                  rows={3}
                  value={previewText}
                  onChange={(e) => {
                    setPreviewText(e.target.value);
                    if (previewFeedback) setPreviewFeedback(null);
                  }}
                  maxLength={280}
                  spellCheck={false}
                  placeholder={t("opsTtsAi.previewTextPlaceholder")}
                  title={t("opsTtsAi.previewTextHint")}
                />
                <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.previewTextHint")}</p>
              </div>

              {previewFeedback ? (
                <div className="ops-tts-preview-feedback" role="alert">
                  <span className="ops-tts-preview-feedback__icon" aria-hidden="true">
                    <svg viewBox="0 0 20 20">
                      <circle cx="10" cy="10" r="6.4" fill="none" stroke="currentColor" strokeWidth="1.6" />
                      <path
                        d="M10 6.8v3.8M10 13.25h.01"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        strokeLinecap="round"
                      />
                    </svg>
                  </span>
                  <div>
                    <strong>{t("opsTtsAi.previewBlockedTitle")}</strong>
                    <span>{previewFeedback}</span>
                  </div>
                  <button
                    type="button"
                    aria-label={t("common.close")}
                    title={t("common.close")}
                    onClick={() => setPreviewFeedback(null)}
                  >
                    <svg viewBox="0 0 20 20" aria-hidden="true">
                      <path
                        d="M6.5 6.5 13.5 13.5M13.5 6.5 6.5 13.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                </div>
              ) : null}

              <div className="ops-tts-preview-bar">
                <AsyncButton
                  className="ops-tts-action-btn is-primary"
                  pending={asyncAction.isPending("preview")}
                  pendingLabel={t("opsTtsAi.previewing")}
                  leadingIcon={<TtsSetupActionIcon kind="preview" />}
                  onClick={() => void asyncAction.run("preview", onPreview)}
                  disabled={saving || testing || installing || !previewText.trim()}
                  aria-label={previewing ? t("opsTtsAi.previewing") : t("opsTtsAi.preview")}
                  title={previewing ? t("opsTtsAi.previewing") : t("opsTtsAi.preview")}
                >
                  <span className="ops-tts-editor-actions__label">{t("opsTtsAi.preview")}</span>
                </AsyncButton>
                <AsyncButton
                  className="ops-tts-action-btn"
                  pending={asyncAction.isPending("cancel-preview")}
                  pendingLabel={t("opsTtsAi.previewCancel")}
                  leadingIcon={<TtsSetupActionIcon kind="stop" />}
                  onClick={() => void asyncAction.run("cancel-preview", onCancelPreview)}
                  disabled={saving || testing || installing}
                  aria-label={t("opsTtsAi.previewCancel")}
                  title={t("opsTtsAi.previewCancelHint")}
                >
                  <span className="ops-tts-editor-actions__label">{t("opsTtsAi.previewCancel")}</span>
                </AsyncButton>
                {previewAudioUrl ? (
                  <audio controls src={previewAudioUrl} className="ops-tts-preview-audio" preload="metadata">
                    <track kind="captions" />
                  </audio>
                ) : previewing && previewMeta?.detail ? (
                  <p className="ops-tts-preview-idle">{previewMeta.detail}</p>
                ) : (
                  <p className="ops-tts-preview-idle">{t("opsTtsAi.previewIdle")}</p>
                )}
              </div>
            </div>
          </section>
        ) : null}

        {isSystem ? (
          <section className="ops-tts-section">
            <header className="ops-tts-section__head">
              <h3>{t("opsTtsAi.sectionSystem")}</h3>
              <p>
                {activeProvider === "placeholder" ? t("opsTtsAi.hintPlaceholder") : t("opsTtsAi.hintAuto")}
              </p>
            </header>
          </section>
        ) : null}

        {!isSystem && !localDraftNeedsProvider ? (
          <section className="ops-tts-section ops-tts-section--advanced">
            <header className="ops-tts-section__head">
              <h3>{t("opsTtsAi.sectionAdvanced")}</h3>
              <p>{t("opsTtsAi.sectionAdvancedHint")}</p>
            </header>
            <div className="ops-tts-grid">
                <div className="ops-form-field">
                  <label htmlFor="tts-ai-timeout">{t("opsTtsAi.timeoutSeconds")}</label>
                  <input
                    id="tts-ai-timeout"
                    value={form.timeoutSeconds}
                    onChange={(e) => setForm({ ...form, timeoutSeconds: e.target.value })}
                    placeholder={t("opsTtsAi.timeoutSecondsPlaceholder")}
                    title={t("opsTtsAi.timeoutSecondsHint")}
                  />
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.timeoutSecondsHint")}</p>
                </div>
                <div className="ops-form-field">
                  <label htmlFor="tts-ai-fallback">{t("opsTtsAi.fallbackProvider")}</label>
                  <select
                    id="tts-ai-fallback"
                    value={form.fallbackProvider}
                    onChange={(e) => {
                      const next = e.target.value;
                      setForm({ ...form, fallbackProvider: next, fallbackVoiceId: "" });
                    }}
                    title={t("opsTtsAi.fallbackProviderHint")}
                  >
                    <option value="">{t("opsTtsAi.fallbackProviderPlaceholder")}</option>
                    {TTS_FALLBACK_PROVIDERS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.fallbackProviderHint")}</p>
                </div>
                <div className="ops-form-field">
                  <label htmlFor="tts-ai-fallback-voice">{t("opsTtsAi.fallbackVoiceId")}</label>
                  {form.fallbackProvider === "edge" ? (
                    <select
                      id="tts-ai-fallback-voice"
                      value={
                        EDGE_FALLBACK_VOICE_OPTIONS.some((v) => v.id === form.fallbackVoiceId)
                          ? form.fallbackVoiceId
                          : ""
                      }
                      onChange={(e) => setForm({ ...form, fallbackVoiceId: e.target.value })}
                      title={t("opsTtsAi.fallbackVoiceIdHint")}
                    >
                      <option value="">{t("opsTtsAi.fallbackVoiceIdPlaceholder")}</option>
                      {EDGE_FALLBACK_VOICE_OPTIONS.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.label}
                        </option>
                      ))}
                    </select>
                  ) : form.fallbackProvider === "vieneu" && catalogVoices ? (
                    <select
                      id="tts-ai-fallback-voice"
                      value={
                        catalogVoices.some((v) => v.id === form.fallbackVoiceId)
                          ? form.fallbackVoiceId
                          : ""
                      }
                      onChange={(e) => setForm({ ...form, fallbackVoiceId: e.target.value })}
                      title={t("opsTtsAi.fallbackVoiceIdHint")}
                    >
                      <option value="">{t("opsTtsAi.fallbackVoiceIdPlaceholder")}</option>
                      {catalogVoices.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.label || v.id}
                        </option>
                      ))}
                    </select>
                  ) : !form.fallbackProvider || form.fallbackProvider === "none" ? (
                    <input
                      id="tts-ai-fallback-voice"
                      value=""
                      disabled
                      placeholder={t("opsTtsAi.fallbackVoiceIdPlaceholder")}
                      title={t("opsTtsAi.fallbackVoiceIdHint")}
                    />
                  ) : (
                    <input
                      id="tts-ai-fallback-voice"
                      value={form.fallbackVoiceId}
                      onChange={(e) => setForm({ ...form, fallbackVoiceId: e.target.value })}
                      placeholder={t("opsTtsAi.fallbackVoiceIdPlaceholder")}
                      title={t("opsTtsAi.fallbackVoiceIdHint")}
                      spellCheck={false}
                    />
                  )}
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.fallbackVoiceIdHint")}</p>
                </div>
                {isLocal && fieldCaps.local_backend ? (
                  <>
                    <div className="ops-form-field">
                      <label htmlFor="tts-ai-backend">{t("opsTtsAi.localBackend")}</label>
                      <select
                        id="tts-ai-backend"
                        value={form.localBackend}
                        onChange={(e) => setForm({ ...form, localBackend: e.target.value })}
                        title={t("opsTtsAi.localBackendHint")}
                      >
                        <option value="">{t("opsTtsAi.localBackendPlaceholder")}</option>
                        {(catalog?.backends?.length
                          ? catalog.backends
                          : ["auto", "onnx", "pytorch", "remote"]
                        ).map((backend) => (
                          <option key={backend} value={backend}>
                            {backend}
                          </option>
                        ))}
                      </select>
                      <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.localBackendHint")}</p>
                    </div>
                    <div className="ops-form-field">
                      <label htmlFor="tts-ai-device">{t("opsTtsAi.device")}</label>
                      <select
                        id="tts-ai-device"
                        value={form.device}
                        onChange={(e) => setForm({ ...form, device: e.target.value })}
                        title={t("opsTtsAi.deviceHint")}
                      >
                        <option value="">{t("opsTtsAi.devicePlaceholder")}</option>
                        <option value="auto">auto</option>
                        <option value="cpu">cpu</option>
                        <option value="cuda">cuda</option>
                      </select>
                      <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.deviceHint")}</p>
                    </div>
                    {fieldCaps.styles ? (
                      <div className="ops-form-field">
                        <label htmlFor="tts-ai-style">{t("opsTtsAi.style")}</label>
                        <select
                          id="tts-ai-style"
                          value={form.style}
                          onChange={(e) => setForm({ ...form, style: e.target.value })}
                          title={t("opsTtsAi.styleHint")}
                        >
                          <option value="">{t("opsTtsAi.stylePlaceholder")}</option>
                          {(catalogStyles || ["tu_nhien", "tin_tuc", "doc_truyen"]).map((style) => (
                            <option key={style} value={style}>
                              {style}
                            </option>
                          ))}
                        </select>
                        <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.styleHint")}</p>
                      </div>
                    ) : null}
                  </>
                ) : null}
                {isLocal && fieldCaps.cli_binary ? (
                  <div className="ops-form-field ops-tts-span-2">
                    <label htmlFor="tts-ai-cli">{t("opsTtsAi.cliBinary")}</label>
                    <input
                      id="tts-ai-cli"
                      value={form.cliBinary}
                      onChange={(e) => setForm({ ...form, cliBinary: e.target.value })}
                      placeholder={t("opsTtsAi.cliBinaryPlaceholder")}
                      title={t("opsTtsAi.cliBinaryHint")}
                      spellCheck={false}
                    />
                    <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.cliBinaryHint")}</p>
                  </div>
                ) : null}
                {isLocal && (fieldCaps.base_url || fieldCaps.api_key) ? (
                  <>
                    {fieldCaps.base_url ? (
                      <div className="ops-form-field ops-tts-span-2">
                        <label htmlFor="tts-ai-base-url-local">{t("opsTtsAi.baseUrl")}</label>
                        <input
                          id="tts-ai-base-url-local"
                          value={form.baseUrl}
                          onChange={(e) => setForm({ ...form, baseUrl: e.target.value })}
                          placeholder={t("opsTtsAi.baseUrlPlaceholder")}
                          title={t("opsTtsAi.baseUrlHint")}
                          spellCheck={false}
                          autoComplete="off"
                        />
                        <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.sectionRemoteOptionalHint")}</p>
                      </div>
                    ) : null}
                    {fieldCaps.api_key ? (
                      <>
                        <div className="ops-form-field ops-tts-span-2">
                          <label htmlFor="tts-ai-api-key-local">{t("opsTtsAi.apiKey")}</label>
                          <input
                            id="tts-ai-api-key-local"
                            type="password"
                            autoComplete="off"
                            placeholder={meta.apiKeySet ? t("opsTtsAi.apiKeyKeep") : t("opsTtsAi.apiKeyPlaceholder")}
                            title={t("opsTtsAi.apiKeyHint")}
                            value={form.apiKeyInput}
                            onChange={(e) => setForm({ ...form, apiKeyInput: e.target.value })}
                          />
                          <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.apiKeyHint")}</p>
                        </div>
                      </>
                    ) : null}
                  </>
                ) : null}
            </div>
          </section>
        ) : null}
        </div>
      </OpsPanel>
    </main>
    </OpsConsoleShell>
  );
}
