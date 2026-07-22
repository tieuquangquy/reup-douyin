"use client";

import { useEffect, useRef, useState } from "react";
import {
  activateTtsAiProfile,
  createTtsAiProfile,
  deleteTtsAiProfile,
  fetchTtsAi,
  fetchTtsAiInstallStatus,
  fetchTtsAiPreviewStatus,
  cancelTtsAiPreview,
  fetchTtsAiProfile,
  installTtsAiPackage,
  previewTtsAiSpeech,
  renameTtsAiProfile,
  reorderTtsAiProfiles,
  saveTtsAiProfile,
  setTtsAiProfileEnabled,
  testTtsAi,
  type TtsAiCatalog,
  type TtsAiInstallResponse,
  type TtsAiProfileSummary,
  type TtsAiResponse,
  type TtsAiRuntime
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { isSetupTableInteractiveDragTarget, moveItemIndex, profileIdsOf } from "../../lib/opsProfileReorder";
import {
  formatProviderError,
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
  defaultProviderForKind,
  getLocalInstallRecipe,
  getOmnivoiceCuratedCatalogCapabilities,
  getTtsFieldCapabilities,
  isCustomLocalProvider,
  isPresetLocalProvider,
  looksLikeEdgeVoiceId,
  OMNIVOICE_CURATED_MODELS,
  OMNIVOICE_CURATED_VOICES,
  resolveProviderSlugFromInstall,
  resolveTtsProviderKind,
  showsTtsApiKey,
  showsTtsBaseUrl,
  showsTtsCliBinary,
  showsTtsLocalBackend,
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
  baseUrl: string;
  timeoutSeconds: string;
  fallbackProvider: string;
  fallbackVoiceId: string;
  localBackend: string;
  device: string;
  cliBinary: string;
  style: string;
  installCommand: string;
  extraRequirement: string;
  packageName: string;
  repoUrl: string;
};

function resolveProviderChoice(provider: string): { choice: string; customSlug: string } {
  if (isPresetLocalProvider(provider) || resolveTtsProviderKind(provider) !== "local") {
    return { choice: provider, customSlug: "" };
  }
  return { choice: "custom", customSlug: provider };
}

function toForm(data: TtsAiResponse): FormState {
  const options = data.options_json || {};
  const provider = data.provider || "auto";
  const recipe = getLocalInstallRecipe(provider);
  const choice = resolveProviderChoice(provider);
  return {
    enabled: data.enabled,
    provider,
    providerChoice: choice.choice,
    customProviderSlug: choice.customSlug,
    voiceId: data.voice_id || "",
    speakingRate: String(data.speaking_rate ?? 1),
    languageCode: data.language_code || "vi",
    modelId: data.model_id || "",
    apiKeyInput: "",
    baseUrl: data.base_url || "",
    timeoutSeconds: String(data.timeout_seconds ?? 120),
    fallbackProvider: data.fallback_provider || "none",
    fallbackVoiceId: data.fallback_voice_id || "",
    localBackend: data.local_backend || "auto",
    device: data.device || "auto",
    cliBinary: data.cli_binary || "",
    style: typeof options.style === "string" ? options.style : "tu_nhien",
    installCommand:
      typeof options.install_command === "string" && options.install_command.trim()
        ? options.install_command
        : recipe?.installCommand || "",
    extraRequirement:
      typeof options.extra_requirement === "string" && options.extra_requirement.trim()
        ? options.extra_requirement
        : recipe?.extraRequirement || "",
    packageName: typeof options.package_name === "string" ? options.package_name : recipe?.packageName || "",
    repoUrl: typeof options.repo_url === "string" ? options.repo_url : ""
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
    baseUrl: "",
    timeoutSeconds: "",
    fallbackProvider: "",
    fallbackVoiceId: "",
    localBackend: "",
    device: "",
    cliBinary: "",
    style: "",
    installCommand: "",
    extraRequirement: "",
    packageName: "",
    repoUrl: ""
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
  const [meta, setMeta] = useState<{ apiKeySet: boolean; apiKeyMasked: string; source: string }>({
    apiKeySet: false,
    apiKeyMasked: "",
    source: "env"
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [catalog, setCatalog] = useState<TtsAiCatalog | null>(null);
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
  const [previewMeta, setPreviewMeta] = useState<{ provider: string; duration: number; detail: string } | null>(
    null
  );
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
  const previewPollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewPollCancelledRef = useRef(false);

  function applyCatalog(nextCatalog: TtsAiCatalog | null, base: FormState) {
    setCatalog(nextCatalog);
    if (!nextCatalog) return base;
    const patch = { ...base };
    const voices = nextCatalog.voices || [];
    if (voices.length > 0) {
      if (!patch.voiceId.trim() || !voices.some((v) => v.id === patch.voiceId)) {
        // Keep operator-saved voice when catalog refresh still lists it; only fill when empty/unknown.
        patch.voiceId = nextCatalog.default_voice_id || voices[0]?.id || patch.voiceId;
      }
    }
    if (nextCatalog.styles?.length > 0 && !nextCatalog.styles.includes(patch.style)) {
      patch.style = nextCatalog.styles[0] || patch.style;
    }
    if (nextCatalog.models?.length > 0 && !patch.modelId.trim()) {
      patch.modelId = nextCatalog.models[0] || patch.modelId;
    }
    return patch;
  }

  function applyListResponse(data: TtsAiResponse) {
    setProfiles(data.profiles || []);
    setActiveProfileId(data.active_profile_id || "");
  }

  function applyResponse(data: TtsAiResponse) {
    let next = toForm(data);
    setRuntime(data.runtime || null);
    setLiveImportOk(data.live_import_ok ?? null);
    applyListResponse(data);
    const hydrated = catalogFromRuntime(data.runtime || null);
    if (hydrated) {
      next = applyCatalog(hydrated, next);
    } else {
      setCatalog(null);
    }
    // Banners are session action feedback only — durable status stays on runtime chips.
    setTestResult(null);
    setInstallResult(null);
    setForm(next);
    setKind(resolveTtsProviderKind(next.provider));
    setMeta({
      apiKeySet: data.api_key_set,
      apiKeyMasked: data.api_key_masked,
      source: data.source
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
    const options_json: Record<string, unknown> = {};
    if (resolveTtsProviderKind(provider) === "local") {
      if (form.installCommand.trim()) options_json.install_command = form.installCommand.trim();
      if (form.extraRequirement.trim()) options_json.extra_requirement = form.extraRequirement.trim();
      if (form.packageName.trim()) options_json.package_name = form.packageName.trim();
      if (form.repoUrl.trim()) options_json.repo_url = form.repoUrl.trim();
      if (provider === "vieneu") options_json.style = form.style || "tu_nhien";
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
    setRuntime(null);
    setLiveImportOk(null);
    setTestResult(null);
    setInstallResult(null);
    setMeta({ apiKeySet: false, apiKeyMasked: "", source: "env" });
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
    // On/Off = Set active. On another row → switch active (+ enable). Off on active → disable override.
    setProfileBusy(true);
    setError(null);
    try {
      if (!nextOn) {
        if (profileId === activeProfileId) {
          applyListResponse(await setTtsAiProfileEnabled(profileId, false));
        }
        return;
      }
      if (profileId !== activeProfileId) {
        await activateTtsAiProfile(profileId);
      }
      applyListResponse(await setTtsAiProfileEnabled(profileId, true));
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

  async function onTest() {
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
      if (kind === "cloud") {
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
      if (kind === "http") {
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
      const result = await testTtsAi({ ...payload, profile_id: editingProfileId || undefined });
      setTestResult({ ok: result.ok, provider: result.provider, detail: result.detail });
      notify({
        id: "tts-settings-test",
        message: result.ok ? t("opsTtsAi.testOk") : t("opsTtsAi.testFail"),
        tone: result.ok ? "success" : "warning"
      });
      if (result.runtime) setRuntime(result.runtime);
      const nextCatalog = result.catalog && result.ok ? result.catalog : null;
      if (form) {
        setForm(applyCatalog(nextCatalog, form));
      } else {
        setCatalog(nextCatalog);
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
    const list = TTS_PROVIDERS_BY_KIND[nextKind];
    const currentChoice = form.providerChoice === "custom" ? "custom" : form.provider;
    const staysInKind =
      (nextKind === "local" && (form.providerChoice === "custom" || isCustomLocalProvider(form.provider))) ||
      list.includes(currentChoice as (typeof list)[number]);
    setKind(nextKind);
    setTestResult(null);
    setCatalog(null);
    setInstallResult(null);
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
    patch.provider = effectiveProvider(patch);
    setForm(patch);
    setKind(isCustom || patch.providerChoice === "custom" ? "local" : resolveTtsProviderKind(patch.provider));
    setTestResult(null);
    setCatalog(null);
    setInstallResult(null);
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
      setInstallResult(null);
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
    setInstallResult(null);
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
      next.providerChoice = "custom";
      next.customProviderSlug = slug;
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
        nextForm.providerChoice = "custom";
        nextForm.customProviderSlug = slug;
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
      const apiCatalogRich = Boolean(
        apiCatalog &&
          (apiCatalog.voices?.length ?? 0) >= 5 &&
          (apiCatalog.models?.length ?? 0) >= 5
      );
      const nextCatalog = apiCatalogRich
        ? apiCatalog
        : slug === "omnivoice" || packageName.toLowerCase().includes("omnivoice")
          ? ({
              source: "curated",
              voices: OMNIVOICE_CURATED_VOICES.map((v) => ({ id: v.id, label: v.label })),
              styles: [],
              models: [...OMNIVOICE_CURATED_MODELS],
              default_voice_id: "auto",
              warning: "",
              capabilities: getOmnivoiceCuratedCatalogCapabilities()
            } satisfies TtsAiCatalog)
          : apiCatalog && (apiCatalog.voices?.length || apiCatalog.models?.length)
            ? apiCatalog
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
      setForm(applyCatalog(nextCatalog ?? null, nextForm));
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

  async function pollInstallUntilDone(workingForm: FormState) {
    const maxAttempts = 180;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      if (installPollCancelledRef.current) return;
      await waitInstallPollDelay(2000);
      if (installPollCancelledRef.current) return;
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
      return;
    }
    setInstallResult({
      ok: false,
      detail: t("opsTtsAi.installPollTimeout"),
      command: workingForm.installCommand,
      log_tail: "",
      already_satisfied: false
    });
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

  async function onPreview() {
    const payload = buildPayload();
    if (!payload) return;
    const sample = previewText.trim();
    if (!sample) {
      setError(t("opsTtsAi.previewEmpty"));
      return;
    }
    previewPollCancelledRef.current = false;
    setPreviewing(true);
    setError(null);
    setPreviewMeta(null);
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
          detail: started.detail || t("opsTtsAi.previewing")
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
              detail: status.detail || t("opsTtsAi.previewing")
            });
            continue;
          }
          if (!status.ok || status.status === "failed" || status.status === "cancelled") {
            if (status.status === "cancelled") {
              setPreviewMeta(null);
              setError(null);
              return;
            }
            setError(status.detail || t("opsTtsAi.previewError"));
            return;
          }
          if (!status.audio_base64) {
            setError(t("opsTtsAi.previewError"));
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
            detail: status.detail
          });
          notify({ id: "tts-preview-finished", message: status.detail || t("opsTtsAi.preview"), tone: "success" });
          return;
        }
        setError(t("opsTtsAi.previewPollTimeout"));
        try {
          await cancelTtsAiPreview();
        } catch {
          // Best-effort unlock so the next Preview is not blocked.
        }
        return;
      }
      if (!started.ok || !started.audio_base64) {
        setError(started.detail || t("opsTtsAi.previewError"));
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
        detail: started.detail
      });
      notify({ id: "tts-preview-finished", message: started.detail || t("opsTtsAi.preview"), tone: "success" });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("opsTtsAi.previewError");
      // Older API builds returned 409 for a stuck lock — cancel once so the next click works.
      if (/already running/i.test(message)) {
        try {
          await cancelTtsAiPreview();
          setError(t("opsTtsAi.previewUnlockedRetry"));
        } catch {
          setError(message);
        }
        return;
      }
      setError(message);
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
      setPreviewMeta(null);
      notify({ id: "tts-preview-cancelled", message: t("opsTtsAi.previewCancel"), tone: "info" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.previewCancelError"));
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
    const activeOnProfile = profiles.find(
      (profile) =>
        (Boolean(profile.is_active) || profile.id === activeProfileId) && Boolean(profile.enabled)
    );
    return (
      <OpsConsoleShell
        actions={refreshAction}
        description={t("nav.ttsSettingsDesc")}
        title={t("nav.ttsSettings")}
      >
      <main className="ops-page ops-page--settings ops-tts-page ops-ai-page is-compact">
        {error ? <div className="inline-error">{error}</div> : null}
        <div className="ops-tts-list-header">
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
            <table className="ops-tts-setup-table">
              <thead>
                <tr>
                  <th scope="col" className="ops-tts-setup-table__drag-col">
                    <span className="visually-hidden">{t("common.dragToReorder")}</span>
                  </th>
                  <th scope="col">{t("opsTtsAi.profileNameCol")}</th>
                  <th scope="col">{t("opsTtsAi.statusLabel")}</th>
                  <th scope="col">{t("opsTtsAi.profileActiveCol")}</th>
                  <th scope="col">{t("opsTtsAi.apiKey")}</th>
                  <th scope="col">{t("opsTtsAi.provider")}</th>
                  <th scope="col">{t("opsTtsAi.voiceId")}</th>
                  <th scope="col">{t("opsTtsAi.languageCode")}</th>
                  <th scope="col">{t("opsTtsAi.speakingRate")}</th>
                  <th scope="col">{t("opsTtsAi.modelId")}</th>
                  <th scope="col">{t("opsTtsAi.fallbackProvider")}</th>
                  <th scope="col">{t("opsTtsAi.localBackend")}</th>
                  <th scope="col">{t("opsTtsAi.profileActionsCol")}</th>
                </tr>
              </thead>
              <tbody>
                  {profiles.map((profile) => {
                  const isActive = Boolean(profile.is_active) || profile.id === activeProfileId;
                  const isOn = isActive && Boolean(profile.enabled);
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
                          <>
                            <button
                              type="button"
                              className="ops-tts-setup-table__name-btn"
                              disabled={profileBusy}
                              title={t("opsTtsAi.profileRenameHint")}
                              onClick={() => startRenameProfile(profile.id, profile.name)}
                            >
                              {profile.name}
                            </button>
                          </>
                        )}
                      </td>
                      <td>
                        <div className="ops-tts-setup-table__chips">
                          <span className={`ops-ai-chip ops-tts-chip ${ttsReadyChipClass(rowReady)}`}>
                            {t(ttsReadyLabelKey(rowReady))}
                          </span>
                          <span className="ops-ai-chip ops-tts-chip is-muted">
                            {t(kindLabelKey(resolveTtsProviderKind(profile.provider || "auto")))}
                          </span>
                        </div>
                      </td>
                      <td>
                        <label className="ops-tts-setup-switch" title={t("opsTtsAi.profileActiveHint")}>
                          <input
                            type="checkbox"
                            checked={isOn}
                            disabled={profileBusy}
                            aria-label={
                              isOn
                                ? t("opsTtsAi.profileOn")
                                : t("opsTtsAi.profileOff")
                            }
                            onChange={(e) => void onSetActive(profile.id, e.target.checked)}
                          />
                          <span className="ops-tts-setup-switch__track" aria-hidden="true" />
                        </label>
                      </td>
                      <td
                        className="ops-tts-setup-table__api-key"
                        title={
                          profile.api_key_set
                            ? profile.api_key_masked || t("opsTtsAi.profileKeySet")
                            : t("opsTtsAi.profileKeyUnset")
                        }
                      >
                        {profile.api_key_set ? (
                          <code>{profile.api_key_masked || t("opsTtsAi.profileKeySet")}</code>
                        ) : (
                          <span className="ops-tts-setup-table__api-key--empty">{t("opsTtsAi.profileKeyUnset")}</span>
                        )}
                      </td>
                      <td>{profile.provider || "auto"}</td>
                      <td title={profile.voice_id || undefined}>{profile.voice_id?.trim() || "—"}</td>
                      <td>{profile.language_code || "vi"}</td>
                      <td>×{profile.speaking_rate ?? 1}</td>
                      <td title={profile.model_id || undefined}>{profile.model_id?.trim() || "—"}</td>
                      <td>
                        {profile.fallback_provider && profile.fallback_provider !== "none"
                          ? profile.fallback_provider
                          : "—"}
                      </td>
                      <td>
                        {profile.local_backend || "auto"}
                        {profile.device ? `/${profile.device}` : ""}
                      </td>
                      <td className="ops-tts-setup-table__actions">
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
  const catalogVoices = catalog?.voices?.length ? catalog.voices : null;
  const catalogStyles = catalog?.styles?.length ? catalog.styles : null;
  const catalogModels = catalog?.models?.length ? catalog.models : null;

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
                disabled={saving || installing || previewing || profileBusy}
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
                disabled={testing || installing || previewing || profileBusy}
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
                          : t("opsTtsAi.testErrorHint")}
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
                    : defaultProviderForKind(kind)
              }
              onChange={(e) => onProviderSelect(e.target.value)}
              title={t("opsTtsAi.providerHint")}
            >
              {TTS_PROVIDERS_BY_KIND[kind].map((slug) => (
                <option key={slug} value={slug}>
                  {slug === "custom" ? t("opsTtsAi.providerCustom") : slug}
                </option>
              ))}
            </select>
            <p className="ops-tts-field-hint">{t("opsTtsAi.providerHint")}</p>
          </div>
          {showCustomSlug ? (
            <div className="ops-form-field ops-tts-span-2">
              <label htmlFor="tts-ai-custom-slug">{t("opsTtsAi.customProviderSlug")}</label>
              <input
                id="tts-ai-custom-slug"
                value={form?.customProviderSlug || ""}
                onChange={(e) => onCustomSlugInput(e.target.value)}
                placeholder={t("opsTtsAi.customProviderSlugPlaceholder")}
                title={t("opsTtsAi.customProviderHint")}
                spellCheck={false}
                autoComplete="off"
              />
              <p className="ops-tts-field-hint">{t("opsTtsAi.customProviderHint")}</p>
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
              {(isHttp || fieldCaps.base_url) ? (
                <div className="ops-form-field ops-tts-span-2">
                  <label htmlFor="tts-ai-base-url">{t("opsTtsAi.baseUrl")}</label>
                  <input
                    id="tts-ai-base-url"
                    value={form.baseUrl}
                    onChange={(e) => setForm({ ...form, baseUrl: e.target.value })}
                    placeholder={t("opsTtsAi.baseUrlPlaceholder")}
                    title={t("opsTtsAi.baseUrlHint")}
                    spellCheck={false}
                    autoComplete="off"
                  />
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.baseUrlHint")}</p>
                </div>
              ) : null}
              {(isCloud || isHttp || fieldCaps.api_key) ? (
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
                      onChange={(e) => setForm({ ...form, apiKeyInput: e.target.value })}
                    />
                    <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.apiKeyHint")}</p>
                  </div>
                </>
              ) : null}
            </div>
          </section>
        ) : null}

        {isLocal ? (
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

        {(isLocal || isCloud || isHttp) ? (
          <section className="ops-tts-section">
            <header className="ops-tts-section__head" title={t("opsTtsAi.sectionVoiceHint")}>
              <h3>{t("opsTtsAi.sectionVoice")}</h3>
              <p>{t("opsTtsAi.sectionVoiceHint")}</p>
            </header>
              {catalog ? (
                <div className="ops-tts-status ops-tts-status--compact" aria-label={t("opsTtsAi.providerMetaLabel")}>
                  <span className="ops-tts-chip is-ok">
                    {t("opsTtsAi.catalogSource")}: {catalog.source}
                    {catalogVoices ? ` · ${catalogVoices.length}` : ""}
                  </span>
                  {catalog.sample_rate ? (
                    <span className="ops-tts-chip is-muted">
                      {t("opsTtsAi.sampleRate")}: {catalog.sample_rate} Hz
                    </span>
                  ) : null}
                  {catalog.models?.length ? (
                    <span className="ops-tts-chip is-muted">
                      {t("opsTtsAi.modelId")}: {form.modelId || catalog.models[0]}
                    </span>
                  ) : null}
                </div>
              ) : null}
              <div className="ops-tts-grid">
                {fieldCaps.voice ? (
                  <div className="ops-form-field ops-tts-span-2">
                    <label htmlFor="tts-ai-voice">{t("opsTtsAi.voiceId")}</label>
                    {catalogVoices ? (
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
                      {catalogVoices
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
                  <input
                    id="tts-ai-lang"
                    value={form.languageCode}
                    onChange={(e) => setForm({ ...form, languageCode: e.target.value })}
                    placeholder={t("opsTtsAi.languageCodePlaceholder")}
                    title={t("opsTtsAi.languageCodeHint")}
                  />
                  <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.languageCodeHint")}</p>
                </div>
                {fieldCaps.model ? (
                  <div className="ops-form-field ops-tts-span-2">
                    <label htmlFor="tts-ai-model">{t("opsTtsAi.modelId")}</label>
                    {catalogModels ? (
                      <select
                        id="tts-ai-model"
                        value={catalogModels.includes(form.modelId) ? form.modelId : catalogModels[0] || ""}
                        onChange={(e) => setForm({ ...form, modelId: e.target.value })}
                      >
                        {catalogModels.map((m) => (
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
                  </div>
                ) : null}
              </div>
          </section>
        ) : null}

        {(isLocal || isCloud || isHttp) ? (
          <section className="ops-tts-section ops-tts-section--preview">
            <header className="ops-tts-section__head" title={t("opsTtsAi.sectionPreviewHint")}>
              <div>
                <h3>{t("opsTtsAi.sectionPreview")}</h3>
                <p>{t("opsTtsAi.sectionPreviewHint")}</p>
              </div>
              {previewMeta ? (
                <span className="ops-tts-chip is-ok" title={previewMeta.detail || undefined}>
                  {previewMeta.provider} · {previewMeta.duration.toFixed(1)}s
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
                  onChange={(e) => setPreviewText(e.target.value)}
                  maxLength={280}
                  spellCheck={false}
                  placeholder={t("opsTtsAi.previewTextPlaceholder")}
                  title={t("opsTtsAi.previewTextHint")}
                />
                <p className="ops-tts-field-hint ops-tts-field-hint--quiet">{t("opsTtsAi.previewTextHint")}</p>
              </div>

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

        {!isSystem ? (
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
