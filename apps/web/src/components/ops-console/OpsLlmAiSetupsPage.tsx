"use client";

import { useEffect, useRef, useState } from "react";
import {
  activateCaptionAiProfile,
  activateTranslationAiProfile,
  createCaptionAiProfile,
  createTranslationAiProfile,
  deleteCaptionAiProfile,
  deleteTranslationAiProfile,
  fetchCaptionAi,
  fetchCaptionAiProfile,
  fetchTranslationAi,
  fetchTranslationAiProfile,
  listCaptionAiModels,
  listTranslationAiModels,
  renameCaptionAiProfile,
  renameTranslationAiProfile,
  reorderCaptionAiProfiles,
  reorderTranslationAiProfiles,
  saveCaptionAiProfile,
  saveTranslationAiProfile,
  setCaptionAiProfileEnabled,
  setTranslationAiProfileEnabled,
  testCaptionAi,
  testTranslationAi,
  type TranslationAiPayload,
  type TranslationAiProfileSummary,
  type TranslationAiResponse
} from "../../lib/api";
import {
  defaultBaseUrlFor,
  defaultModelFor,
  LLM_PROVIDER_OPTIONS,
  llmProviderLabel,
  llmRuntimeMode,
  showsLlmApiKey,
  showsLlmBaseUrl,
  showsLlmRegion
} from "../../lib/opsLlmProviderCatalog";
import { isSetupTableInteractiveDragTarget, moveItemIndex, profileIdsOf } from "../../lib/opsProfileReorder";
import { useT } from "../../lib/i18n";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { useLatestRequest } from "../../lib/useLatestRequest";
import {
  formatLlmProbeSuccess,
  formatProviderError,
  providerTestErrorHint,
  type ConnectionTestResult,
  type ProviderErrorView
} from "../../lib/opsTranslationAiFormat";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsCaptionSettingsTabs } from "./OpsCaptionSettingsTabs";
import { OpsPanel } from "./OpsShared";
import { OpsTranslationSettingsTabs } from "./OpsTranslationSettingsTabs";

export type LlmAiVariant = "translation" | "caption";

type FormState = {
  enabled: boolean;
  provider: string;
  model: string;
  apiKeyInput: string;
  baseUrl: string;
  region: string;
  timeoutSeconds: string;
  fallbackProvider: string;
  fallbackModel: string;
};

/** Provider-aware gate: Model picker only after required connection fields are filled. */
export function modelListReady(provider: string, hasApiKey: boolean, baseUrl: string): boolean {
  const mode = llmRuntimeMode(provider);
  const base = baseUrl.trim();
  if (mode === "openai_compatible") return hasApiKey && Boolean(base);
  if (mode === "google_cloud") return hasApiKey;
  if (mode === "gemini") return hasApiKey;
  if (mode === "ollama") return Boolean(base);
  return false;
}

export function canShowModel(provider: string, hasApiKey: boolean, baseUrl: string): boolean {
  return modelListReady(provider, hasApiKey, baseUrl);
}

export const captionModelListReady = modelListReady;
export const captionCanShowModel = canShowModel;

function showsBaseUrl(provider: string): boolean {
  return showsLlmBaseUrl(provider);
}

function showsApiKey(provider: string): boolean {
  return showsLlmApiKey(provider);
}

function compactEndpointLabel(raw: string): string {
  const value = raw.trim();
  if (!value) return "";
  try {
    return new URL(value).host || value;
  } catch {
    return value.replace(/^https?:\/\//i, "").split("/")[0] || value;
  }
}

function toForm(data: TranslationAiResponse): FormState {
  return {
    enabled: data.enabled,
    provider: data.provider || "auto",
    model: data.model || "",
    apiKeyInput: (data.api_key || "").trim(),
    baseUrl: data.base_url || "",
    region: data.region || "global",
    timeoutSeconds: String(data.timeout_seconds ?? 90),
    fallbackProvider: data.fallback_provider || "none",
    fallbackModel: data.fallback_model || ""
  };
}

function blankForm(): FormState {
  return {
    enabled: false,
    provider: "",
    model: "",
    apiKeyInput: "",
    baseUrl: "",
    region: "global",
    timeoutSeconds: "90",
    fallbackProvider: "none",
    fallbackModel: ""
  };
}

function nextBlankSetupName(existing: Array<{ name: string }>): string {
  const used = new Set(existing.map((p) => (p.name || "").trim().toLowerCase()).filter(Boolean));
  let index = existing.length + 1;
  for (;;) {
    const candidate = `Setup ${index}`;
    if (!used.has(candidate.toLowerCase())) return candidate;
    index += 1;
  }
}

type SetupActionIconKind = "edit" | "delete" | "add" | "back" | "test" | "save" | "reload" | "list";

function SetupActionIcon({ kind }: { kind: SetupActionIconKind }) {
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
  if (kind === "reload") {
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
  if (kind === "list") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 5.5h11M4.5 10h11M4.5 14.5h11"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
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

type ApiBundle = {
  fetchList: () => Promise<TranslationAiResponse>;
  fetchProfile: (profileId: string) => Promise<TranslationAiResponse>;
  createProfile: (name: string) => Promise<TranslationAiResponse>;
  saveProfile: (profileId: string, payload: TranslationAiPayload) => Promise<TranslationAiResponse>;
  renameProfile: (profileId: string, name: string) => Promise<TranslationAiResponse>;
  setEnabled: (profileId: string, enabled: boolean) => Promise<TranslationAiResponse>;
  activate: (profileId: string) => Promise<TranslationAiResponse>;
  reorderProfiles: (profileIds: string[]) => Promise<TranslationAiResponse>;
  deleteProfile: (profileId: string) => Promise<TranslationAiResponse>;
  testConnection: (
    payload: Partial<TranslationAiPayload> & { profile_id?: string }
  ) => Promise<{ ok: boolean; provider: string; detail: string }>;
  listModels: (payload: {
    provider: string;
    api_key?: string | null;
    base_url?: string | null;
    region?: string | null;
    timeout_seconds?: number;
    profile_id?: string | null;
  }) => Promise<{ ok: boolean; models: string[]; detail: string }>;
};

function apiForVariant(variant: LlmAiVariant): ApiBundle {
  if (variant === "caption") {
    return {
      fetchList: fetchCaptionAi,
      fetchProfile: fetchCaptionAiProfile,
      createProfile: createCaptionAiProfile,
      saveProfile: saveCaptionAiProfile,
      renameProfile: renameCaptionAiProfile,
      setEnabled: setCaptionAiProfileEnabled,
      activate: activateCaptionAiProfile,
      reorderProfiles: reorderCaptionAiProfiles,
      deleteProfile: deleteCaptionAiProfile,
      testConnection: testCaptionAi,
      listModels: listCaptionAiModels
    };
  }
  return {
    fetchList: fetchTranslationAi,
    fetchProfile: fetchTranslationAiProfile,
    createProfile: createTranslationAiProfile,
    saveProfile: saveTranslationAiProfile,
    renameProfile: renameTranslationAiProfile,
    setEnabled: setTranslationAiProfileEnabled,
    activate: activateTranslationAiProfile,
    reorderProfiles: reorderTranslationAiProfiles,
    deleteProfile: deleteTranslationAiProfile,
    testConnection: testTranslationAi,
    listModels: listTranslationAiModels
  };
}

async function latestOnly<T>(signal: AbortSignal, request: () => Promise<T>): Promise<T> {
  try {
    const value = await request();
    if (signal.aborted) throw new DOMException("Request superseded", "AbortError");
    return value;
  } catch (reason) {
    if (signal.aborted) throw new DOMException("Request superseded", "AbortError");
    throw reason;
  }
}

export function OpsLlmAiSetupsPage({ variant }: { variant: LlmAiVariant }) {
  const t = useT();
  const asyncAction = useAsyncAction();
  const modelRequest = useLatestRequest();
  const { notify } = useNotice();
  const api = apiForVariant(variant);
  const i18n = variant === "caption" ? "opsCaptionAi" : "opsTranslationAi";
  const navTitle = variant === "caption" ? t("nav.captionAiSettings") : t("nav.translationSettings");
  const navDesc =
    variant === "caption" ? t("nav.captionAiSettingsDesc") : t("nav.translationSettingsDesc");
  const idPrefix = variant === "caption" ? "caption-ai" : "translation-ai";

  const [form, setForm] = useState<FormState | null>(null);
  const [meta, setMeta] = useState<{ apiKeySet: boolean; apiKeyMasked: string; source: string }>({
    apiKeySet: false,
    apiKeyMasked: "",
    source: "env"
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const loadingModels = modelRequest.pending;
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelListError, setModelListError] = useState<ProviderErrorView | null>(null);
  const [manualModel, setManualModel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providerMissing, setProviderMissing] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [profiles, setProfiles] = useState<TranslationAiProfileSummary[]>([]);
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

  function applyListResponse(data: TranslationAiResponse) {
    setProfiles(data.profiles || []);
    setActiveProfileId(data.active_profile_id || "");
  }

  function applyEditorResponse(data: TranslationAiResponse) {
    setForm(toForm(data));
    setMeta({
      apiKeySet: data.api_key_set,
      apiKeyMasked: data.api_key_masked,
      source: data.source
    });
    setManualModel(false);
    setModelOptions(data.model ? [data.model] : []);
    setModelListError(null);
    setTestResult(null);
    if (data.profiles) applyListResponse(data);
  }

  async function loadList() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.fetchList();
      applyListResponse(data);
      setViewMode("list");
      setEditingProfileId(null);
      setForm(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.loadError`));
    } finally {
      setLoading(false);
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      if (viewMode === "editor" && editingProfileId) {
        const data = await api.fetchProfile(editingProfileId);
        applyEditorResponse(data);
      } else {
        const data = await api.fetchList();
        applyListResponse(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.loadError`));
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when locale or variant changes
  }, [t, variant]);

  useEffect(() => {
    if (!renamingProfileId) return;
    const input = renameInputRef.current;
    if (!input) return;
    input.focus();
    input.select();
  }, [renamingProfileId]);

  const hasApiKey = Boolean(form) && (Boolean(form!.apiKeyInput.trim()) || meta.apiKeySet);
  const readyForModels = form ? modelListReady(form.provider, hasApiKey, form.baseUrl) : false;
  const showModel = form ? canShowModel(form.provider, hasApiKey, form.baseUrl) : false;

  function providerErrorLabels() {
    return {
      unauthorized: t(`${i18n}.errorUnauthorized`),
      forbidden: t(`${i18n}.errorForbidden`),
      notFound: t(`${i18n}.errorNotFound`),
      rateLimited: t(`${i18n}.errorRateLimited`),
      failed: t(`${i18n}.errorFailed`),
      checkKey: t(`${i18n}.errorCheckKey`),
      checkForbidden: t(`${i18n}.errorCheckForbidden`),
      checkEndpoint: t(`${i18n}.errorCheckEndpoint`)
    };
  }

  async function refreshModels() {
    if (!form || !readyForModels) return;
    setModelListError(null);
    try {
      const payload: Parameters<typeof api.listModels>[0] = {
        provider: form.provider,
        base_url: form.baseUrl.trim() || null,
        region: form.region.trim() || "global",
        // List catalog should fail fast; form timeout is for Test/chat, not model listing.
        timeout_seconds: 12,
        profile_id: editingProfileId || null
      };
      if (form.apiKeyInput.trim()) {
        payload.api_key = form.apiKeyInput.trim();
      } else {
        payload.api_key = null;
      }
      await modelRequest.run(
        (signal) => latestOnly(signal, () => api.listModels(payload)),
        (result) => {
          if (result.models.length > 0) {
            const next = form.model && !result.models.includes(form.model)
              ? [form.model, ...result.models]
              : result.models;
            setModelOptions(next);
            setManualModel(false);
            setModelListError(
              result.ok
                ? null
                : formatProviderError(result.detail || t(`${i18n}.modelsEmpty`), providerErrorLabels())
            );
          } else {
            setModelOptions(form.model ? [form.model] : []);
            setManualModel(true);
            setModelListError(
              formatProviderError(result.detail || t(`${i18n}.modelsEmpty`), providerErrorLabels())
            );
          }
        },
        "refresh"
      );
    } catch (err) {
      setModelOptions(form.model ? [form.model] : []);
      setManualModel(true);
      setModelListError(
        formatProviderError(
          err instanceof Error ? err.message : t(`${i18n}.modelsError`),
          providerErrorLabels()
        )
      );
    }
  }

  useEffect(() => {
    if (!form || !readyForModels || viewMode !== "editor") {
      if (form && !readyForModels) setModelListError(null);
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshModels();
    }, 700);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reload when credentials change
  }, [
    form?.provider,
    form?.baseUrl,
    form?.region,
    form?.apiKeyInput,
    form?.timeoutSeconds,
    meta.apiKeySet,
    editingProfileId,
    readyForModels,
    viewMode
  ]);

  function buildPayload(): TranslationAiPayload | null {
    if (!form) return null;
    if (!form.provider.trim()) {
      setProviderMissing(true);
      setError(null);
      return null;
    }
    setProviderMissing(false);
    const timeout = Number(form.timeoutSeconds);
    const payload: TranslationAiPayload = {
      enabled: form.enabled,
      provider: form.provider,
      model: form.model.trim(),
      base_url: form.baseUrl.trim(),
      region: form.region.trim() || "global",
      timeout_seconds: Number.isFinite(timeout) && timeout > 0 ? timeout : 90,
      fallback_provider: form.fallbackProvider,
      fallback_model: form.fallbackModel.trim()
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
      const data = await api.fetchProfile(profileId);
      applyEditorResponse(data);
      setEditingProfileId(profileId);
      const named = (data.profiles || []).find((p) => p.id === profileId);
      setEditingProfileName(named?.name || "Setup");
      setViewMode("editor");
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.loadError`));
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
        const created = await api.createProfile(setupName);
        profileId = created.focus_profile_id || null;
        if (!profileId) throw new Error(t(`${i18n}.profileError`));
        setEditingProfileId(profileId);
        setEditingProfileName(setupName);
      } else {
        const currentName = profiles.find((p) => p.id === profileId)?.name || "";
        if (setupName && setupName !== currentName) {
          await api.renameProfile(profileId, setupName);
          setEditingProfileName(setupName);
        }
      }
      await api.saveProfile(profileId, payload);
      await loadList();
      notify({ id: `${idPrefix}-saved`, message: t(`${i18n}.saved`), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.saveError`));
    } finally {
      setSaving(false);
    }
  }

  function onCreateProfile() {
    const name = nextBlankSetupName(profiles);
    setError(null);
    setProviderMissing(false);
    setEditingProfileId(null);
    setEditingProfileName(name);
    setForm(blankForm());
    setTestResult(null);
    setModelOptions([]);
    setModelListError(null);
    setManualModel(false);
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
      const data = await api.renameProfile(profileId, name);
      applyListResponse(data);
      cancelRenameProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.profileError`));
    } finally {
      setProfileBusy(false);
    }
  }

  async function onSetActive(profileId: string, nextOn: boolean) {
    if (!profileId) return;
    setProfileBusy(true);
    setError(null);
    try {
      if (!nextOn) {
        if (profileId === activeProfileId) {
          applyListResponse(await api.setEnabled(profileId, false));
        }
        return;
      }
      if (profileId !== activeProfileId) {
        await api.activate(profileId);
      }
      applyListResponse(await api.setEnabled(profileId, true));
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.profileError`));
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
      applyListResponse(await api.reorderProfiles(profileIdsOf(next)));
    } catch (err) {
      setProfiles(previous);
      setError(err instanceof Error ? err.message : t(`${i18n}.profileError`));
    } finally {
      setProfileBusy(false);
      setDragFromId(null);
      setDragOverId(null);
    }
  }

  async function onDeleteProfile(profileId: string, name: string) {
    if (profiles.length <= 1) {
      setError(t(`${i18n}.profileLastError`));
      return;
    }
    if (!window.confirm(`${t(`${i18n}.profileDeleteConfirm`)} (${name})`)) return;
    setProfileBusy(true);
    setError(null);
    try {
      const data = await api.deleteProfile(profileId);
      applyListResponse(data);
      } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.profileError`));
    } finally {
      setProfileBusy(false);
    }
  }

  async function onTest() {
    const payload = buildPayload();
    if (!payload) return;
    setTesting(true);
    setError(null);
    try {
      const result = await api.testConnection({
        ...payload,
        profile_id: editingProfileId || undefined
      });
      setTestResult({
        ok: result.ok,
        provider: result.provider,
        detail: result.detail
      });
      if (result.ok) {
        notify({
          id: `${idPrefix}-test`,
          message: t(`${i18n}.testOk`),
          tone: "success"
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.testError`));
    } finally {
      setTesting(false);
    }
  }

  function onProviderChange(next: string) {
    if (!form) return;
    const patch: FormState = { ...form, provider: next };
    if (!patch.baseUrl.trim()) {
      const preset = defaultBaseUrlFor(next);
      if (preset) patch.baseUrl = preset;
    }
    if (!patch.model.trim()) {
      const modelPreset = defaultModelFor(next);
      if (modelPreset) patch.model = modelPreset;
    }
    if (llmRuntimeMode(next) === "google_cloud" && !patch.region.trim()) {
      patch.region = "global";
    }
    setForm(patch);
    setProviderMissing(false);
    setError(null);
    setManualModel(false);
    setModelOptions([]);
    setModelListError(null);
  }

  const refreshAction = (
    <TopbarRefreshButton
      busy={refreshing}
      disabled={refreshing || profileBusy || saving || testing}
      onClick={() => void onRefresh()}
    />
  );

  const settingsTabs =
    variant === "caption" ? <OpsCaptionSettingsTabs /> : <OpsTranslationSettingsTabs />;

  if (loading && profiles.length === 0 && viewMode === "list") {
    return (
      <OpsConsoleShell actions={refreshAction} description={navDesc} title={navTitle}>
        <AsyncContentBoundary status="loading" skeletonVariant="list" loadingLabel={t(`${i18n}.loadingDetail`)}>
          {null}
        </AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  if (viewMode === "list") {
    const activeOnProfile = profiles.find(
      (profile) =>
        (Boolean(profile.is_active) || profile.id === activeProfileId) && Boolean(profile.enabled)
    );
    return (
      <OpsConsoleShell actions={refreshAction} description={navDesc} title={navTitle}>
        <main className={`ops-page ops-page--settings ops-ai-page is-compact ops-ai-control-center is-${variant}`}>
          {error ? <div className="inline-error">{error}</div> : null}
          <div className="ops-tts-list-header">
            {settingsTabs}
            <div className="ops-tts-list-toolbar">
              <div className="ops-tts-list-toolbar__cluster" aria-label={t(`${i18n}.sectionProfiles`)}>
                {activeOnProfile ? (
                  <>
                    <span className="ops-tts-list-toolbar__active" title={t(`${i18n}.profileActiveHint`)}>
                      <span className="ops-tts-list-toolbar__dot" aria-hidden="true" />
                      <span className="ops-tts-list-toolbar__active-label">{t(`${i18n}.profileActive`)}</span>
                      <strong>{activeOnProfile.name}</strong>
                    </span>
                    <span className="ops-tts-list-toolbar__divider" aria-hidden="true" />
                  </>
                ) : null}
                <span className="ops-tts-list-toolbar__count">
                  <strong>{profiles.length}</strong>
                  <span>{t(`${i18n}.profileSetupsCount`)}</span>
                </span>
                <button
                  type="button"
                  className="ops-tts-list-toolbar__new"
                  onClick={() => onCreateProfile()}
                  disabled={profileBusy}
                  aria-label={t(`${i18n}.profileNew`)}
                  title={t(`${i18n}.profileNew`)}
                >
                  <SetupActionIcon kind="add" />
                  <span>{t(`${i18n}.profileNew`)}</span>
                </button>
              </div>
            </div>
          </div>
          {profiles.length === 0 ? (
            <p className="ops-tts-empty">{t(`${i18n}.profileEmpty`)}</p>
          ) : (
            <div className="ops-tts-setup-table-wrap">
              <table className="ops-tts-setup-table ops-ai-registry-table is-llm">
                <colgroup>
                  <col className="ops-ai-col-drag" />
                  <col className="ops-ai-col-setup" />
                  <col className="ops-ai-col-runtime" />
                  <col className="ops-ai-col-connection" />
                  <col className="ops-ai-col-active" />
                  <col className="ops-ai-col-actions" />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col" className="ops-tts-setup-table__drag-col">
                      <span className="visually-hidden">{t("common.dragToReorder")}</span>
                    </th>
                    <th scope="col">{t(`${i18n}.profileNameCol`)}</th>
                    <th scope="col">{t(`${i18n}.runtimeCol`)}</th>
                    <th scope="col">{t(`${i18n}.connectionCol`)}</th>
                    <th scope="col">{t(`${i18n}.profileActiveCol`)}</th>
                    <th scope="col">{t(`${i18n}.profileActionsCol`)}</th>
                  </tr>
                </thead>
                <tbody>
                  {profiles.map((profile) => {
                    const isActive = Boolean(profile.is_active) || profile.id === activeProfileId;
                    const isOn = isActive && Boolean(profile.enabled);
                    const providerLabel = llmProviderLabel(profile.provider) || profile.provider || "auto";
                    const hasFallback = Boolean(
                      profile.fallback_provider?.trim() && profile.fallback_provider.trim().toLowerCase() !== "none"
                    );
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
                          <span
                            className="ops-tts-setup-table__drag-handle"
                            aria-hidden="true"
                          >
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
                                aria-label={t(`${i18n}.profileRename`)}
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
                                title={t(`${i18n}.profileRenameHint`)}
                                onClick={() => startRenameProfile(profile.id, profile.name)}
                              >
                                {profile.name}
                              </button>
                            )}
                          </div>
                        </td>
                        <td>
                          <div
                            className="ops-ai-inline-config"
                            title={[providerLabel, profile.model?.trim(), hasFallback ? `FB: ${profile.fallback_provider}` : ""]
                              .filter(Boolean)
                              .join(" · ")}
                          >
                            <strong>{providerLabel}</strong>
                            <span aria-hidden="true">·</span>
                            <span>{profile.model?.trim() || "—"}</span>
                            {showsLlmRegion(profile.provider) ? <span className="is-muted">· {profile.region || "global"}</span> : null}
                            {hasFallback ? (
                              <span className="is-muted">· FB: {profile.fallback_provider}{profile.fallback_model?.trim() ? ` / ${profile.fallback_model}` : ""}</span>
                            ) : null}
                          </div>
                        </td>
                        <td title={profile.base_url || undefined}>
                          <div className={`ops-ai-inline-connection ${showsApiKey(profile.provider) ? (profile.api_key_set ? "is-key-set" : "is-key-missing") : "is-keyless"}`}>
                            <span className="ops-ai-inline-dot" aria-hidden="true" />
                            <span>{showsApiKey(profile.provider) ? (profile.api_key_set ? t(`${i18n}.profileKeySet`) : t(`${i18n}.profileKeyUnset`)) : t(`${i18n}.keyNotRequired`)}</span>
                            {profile.base_url?.trim() ? <><span aria-hidden="true">·</span><span>{compactEndpointLabel(profile.base_url)}</span></> : null}
                          </div>
                        </td>
                        <td>
                          <div className="ops-ai-inline-status">
                            <label className="ops-tts-setup-switch" title={t(`${i18n}.profileActiveHint`)}>
                              <input
                                type="checkbox"
                                checked={isOn}
                                disabled={profileBusy}
                                aria-label={isOn ? t(`${i18n}.profileOn`) : t(`${i18n}.profileOff`)}
                                onChange={(e) => void onSetActive(profile.id, e.target.checked)}
                              />
                              <span className="ops-tts-setup-switch__track" aria-hidden="true" />
                            </label>
                            <span className="ops-ai-active-label">{isOn ? t(`${i18n}.profileOn`) : t(`${i18n}.profileOff`)}</span>
                          </div>
                        </td>
                        <td className="ops-tts-setup-table__actions">
                          <div className="ops-ai-row-actions">
                            <button
                              type="button"
                              className="ops-tts-setup-table__icon-btn"
                              disabled={profileBusy}
                              aria-label={t(`${i18n}.profileEdit`)}
                              title={t(`${i18n}.profileEdit`)}
                              onClick={() => void openEditor(profile.id)}
                            >
                              <SetupActionIcon kind="edit" />
                            </button>
                            <button
                              type="button"
                              className="ops-tts-setup-table__icon-btn ops-tts-setup-table__icon-btn--danger"
                              disabled={profileBusy || profiles.length <= 1}
                              aria-label={t(`${i18n}.profileDelete`)}
                              title={t(`${i18n}.profileDelete`)}
                              onClick={() => void onDeleteProfile(profile.id, profile.name)}
                            >
                              <SetupActionIcon kind="delete" />
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
      <OpsConsoleShell actions={refreshAction} description={navDesc} title={navTitle}>
        <AsyncContentBoundary status="loading" skeletonVariant="form" loadingLabel={t(`${i18n}.loadingDetail`)}>
          <span />
        </AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  const testFailure =
    testResult && !testResult.ok
      ? formatProviderError(testResult.detail || t(`${i18n}.testFail`), {
          ...providerErrorLabels(),
          failed: t(`${i18n}.testFail`)
        })
      : null;
  const testSuccess =
    testResult && testResult.ok
      ? formatLlmProbeSuccess(testResult, {
          passed: t(`${i18n}.testOk`),
          generic: t(`${i18n}.testOkGeneric`)
        })
      : null;

  function renderProviderAlert(
    view: ProviderErrorView,
    hint: string,
    provider?: string | null
  ) {
    return (
      <div className="ops-field-alert is-error" role="alert" title={view.raw}>
        <div className="ops-field-alert__head">
          <strong>{view.title}</strong>
          {view.httpStatus ? (
            <span className="ops-field-alert__badge">HTTP {view.httpStatus}</span>
          ) : null}
          {provider ? <span className="ops-field-alert__badge is-muted">{provider}</span> : null}
        </div>
        <span className="ops-field-alert__message">{view.message}</span>
        <span className="ops-field-alert-hint">{hint}</span>
      </div>
    );
  }

  function renderFormAlert(title: string, message: string, hint?: string) {
    return (
      <div className="ops-field-alert is-error" role="alert">
        <div className="ops-field-alert__head">
          <strong>{title}</strong>
        </div>
        <span className="ops-field-alert__message">{message}</span>
        {hint ? <span className="ops-field-alert-hint">{hint}</span> : null}
      </div>
    );
  }

  function renderTestBanner() {
    if (!testResult) return null;
    if (testResult.ok && testSuccess) {
      return (
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
              {editingProfileId ? t(`${i18n}.testOkHint`) : t(`${i18n}.testOkDraftHint`)}
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
      );
    }
    return (
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
              {testFailure?.title || t(`${i18n}.testFail`)}
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
            {providerTestErrorHint(testFailure?.httpStatus, {
              key: t(`${i18n}.testErrorHintKey`),
              forbidden: t(`${i18n}.testErrorHintForbidden`),
              quota: t(`${i18n}.testErrorHintQuota`),
              generic: t(`${i18n}.testErrorHint`)
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
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={navDesc} title={navTitle}>
      <main className="ops-page ops-page--settings ops-ai-page is-compact">
        {settingsTabs}

        <OpsPanel
          title={`${t(`${i18n}.panelTitle`)} · ${editingProfileName || t(`${i18n}.profileNew`)}`}
          actions={
            <div
              className="ops-header-actions ops-ai-toolbar"
              role="group"
              aria-label={t(`${i18n}.panelTitle`)}
            >
              <div className="ops-ai-toolbar__group">
                <button
                  type="button"
                  onClick={() => void loadList()}
                  disabled={saving || testing || profileBusy}
                  aria-label={t(`${i18n}.profileBack`)}
                  title={t(`${i18n}.profileBack`)}
                >
                  <SetupActionIcon kind="back" />
                  <span className="ops-tts-editor-actions__label">{t(`${i18n}.actionBack`)}</span>
                </button>
                <AsyncButton
                  pending={asyncAction.isPending("test")}
                  pendingLabel={t(`${i18n}.testing`)}
                  leadingIcon={<SetupActionIcon kind="test" />}
                  onClick={() => void asyncAction.run("test", onTest)}
                  disabled={saving || profileBusy}
                  aria-label={t(`${i18n}.test`)}
                  title={t(`${i18n}.test`)}
                >
                  <span className="ops-tts-editor-actions__label">{t(`${i18n}.actionTest`)}</span>
                </AsyncButton>
                <AsyncButton
                  className="primary"
                  pending={asyncAction.isPending("save")}
                  pendingLabel={t(`${i18n}.saving`)}
                  leadingIcon={<SetupActionIcon kind="save" />}
                  onClick={() => void asyncAction.run("save", onSave)}
                  disabled={testing || profileBusy}
                  aria-label={t(`${i18n}.save`)}
                  title={t(`${i18n}.save`)}
                >
                  <span className="ops-tts-editor-actions__label">{t(`${i18n}.actionSave`)}</span>
                </AsyncButton>
              </div>
            </div>
          }
        >
          {renderTestBanner()}
          {providerMissing
            ? renderFormAlert(
                t(`${i18n}.providerRequiredTitle`),
                t(`${i18n}.providerRequired`),
                t(`${i18n}.providerRequiredHint`)
              )
            : null}
          {error ? renderFormAlert(t(`${i18n}.formErrorTitle`), error) : null}

          <div className="ops-form-field ops-ai-setup-name">
            <label htmlFor={`${idPrefix}-setup-name`}>{t(`${i18n}.setupName`)}</label>
            <input
              id={`${idPrefix}-setup-name`}
              type="text"
              value={editingProfileName}
              maxLength={80}
              onChange={(event) => setEditingProfileName(event.target.value)}
              placeholder={t(`${i18n}.setupNamePlaceholder`)}
              title={t(`${i18n}.setupNameHint`)}
              autoComplete="off"
              spellCheck={false}
            />
            <p className="ops-tts-field-hint">{t(`${i18n}.setupNameHint`)}</p>
          </div>

          <section className="ops-ai-section">
            <header className="ops-ai-section__head">
              <h3>{t(`${i18n}.sectionConnection`)}</h3>
            </header>
            <div className="ops-ai-grid">
              <div className="ops-form-field">
                <label htmlFor={`${idPrefix}-provider`}>{t(`${i18n}.provider`)}</label>
                <select
                  id={`${idPrefix}-provider`}
                  value={form.provider}
                  onChange={(event) => onProviderChange(event.target.value)}
                >
                  <option value="">{t(`${i18n}.providerSelectPlaceholder`)}</option>
                  {form.provider &&
                  !LLM_PROVIDER_OPTIONS.some((option) => option.id === form.provider) ? (
                    <option value={form.provider}>{form.provider}</option>
                  ) : null}
                  {LLM_PROVIDER_OPTIONS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ops-form-field">
                <label htmlFor={`${idPrefix}-timeout`}>{t(`${i18n}.timeout`)}</label>
                <input
                  id={`${idPrefix}-timeout`}
                  type="number"
                  min={1}
                  max={600}
                  value={form.timeoutSeconds}
                  onChange={(event) => setForm({ ...form, timeoutSeconds: event.target.value })}
                />
              </div>
              {showsBaseUrl(form.provider) ? (
                <div className="ops-form-field ops-ai-span-2">
                  <label htmlFor={`${idPrefix}-base-url`}>{t(`${i18n}.baseUrl`)}</label>
                  <input
                    id={`${idPrefix}-base-url`}
                    name={`${idPrefix}-base-url`}
                    type="text"
                    inputMode="url"
                    value={form.baseUrl}
                    onChange={(event) => setForm({ ...form, baseUrl: event.target.value })}
                    placeholder={
                      form.provider === "ollama"
                        ? "http://127.0.0.1:11434"
                        : "https://api.openai.com/v1"
                    }
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
              ) : null}
              {showsLlmRegion(form.provider) ? (
                <div className="ops-form-field">
                  <label htmlFor={`${idPrefix}-region`}>{t(`${i18n}.region`)}</label>
                  <select
                    id={`${idPrefix}-region`}
                    value={form.region}
                    onChange={(event) => setForm({ ...form, region: event.target.value })}
                  >
                    <option value="global">global</option>
                  </select>
                  <p className="ops-tts-field-hint">{t(`${i18n}.regionHint`)}</p>
                </div>
              ) : null}
              {showsApiKey(form.provider) ? (
                <div className="ops-form-field ops-ai-span-2">
                  <label htmlFor={`${idPrefix}-api-key`}>{t(`${i18n}.apiKey`)}</label>
                  <input
                    id={`${idPrefix}-api-key`}
                    name={`${idPrefix}-api-key`}
                    type="text"
                    value={form.apiKeyInput}
                    onChange={(event) => setForm({ ...form, apiKeyInput: event.target.value })}
                    placeholder={t(`${i18n}.apiKeyPlaceholder`)}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
              ) : null}
            </div>
          </section>

          <section className="ops-ai-section">
            <header className="ops-ai-section__head">
              <h3>{t(`${i18n}.sectionModelFallback`)}</h3>
            </header>
            {showModel ? (
              <div className="ops-form-field ops-ai-model-field">
                <label htmlFor={`${idPrefix}-model`}>{t(`${i18n}.model`)}</label>
                {manualModel || modelOptions.length === 0 ? (
                  <input
                    id={`${idPrefix}-model`}
                    value={form.model}
                    onChange={(event) => setForm({ ...form, model: event.target.value })}
                    placeholder="gemini-3.7-flash / gemini-2.5-flash / gpt-4o-mini / qwen2.5:14b"
                    autoComplete="off"
                    spellCheck={false}
                  />
                ) : (
                  <select
                    id={`${idPrefix}-model`}
                    value={form.model}
                    onChange={(event) => setForm({ ...form, model: event.target.value })}
                  >
                    <option value="">{t(`${i18n}.modelSelectPlaceholder`)}</option>
                    {modelOptions.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                )}
                <div className="ops-form-actions ops-ai-model-actions">
                  <AsyncButton
                    className="ops-ai-model-action"
                    pending={loadingModels}
                    pendingLabel={t(`${i18n}.loadingModels`)}
                    leadingIcon={<SetupActionIcon kind="reload" />}
                    onClick={() => void asyncAction.run("models", refreshModels, "replace")}
                    disabled={!readyForModels}
                  >
                    <span>{t(`${i18n}.loadModels`)}</span>
                  </AsyncButton>
                  <button
                    type="button"
                    className="ops-ai-model-action"
                    onClick={() => setManualModel((value) => !value)}
                  >
                    <SetupActionIcon kind={manualModel ? "list" : "edit"} />
                    <span>{manualModel ? t(`${i18n}.useModelList`) : t(`${i18n}.typeModelManually`)}</span>
                  </button>
                </div>
                {modelListError && !testFailure && !testing
                  ? renderProviderAlert(modelListError, t(`${i18n}.modelsErrorHint`))
                  : null}
              </div>
            ) : (
              <p className="ops-ai-gate-hint">
                {form.provider.trim()
                  ? t(`${i18n}.modelGateHint`)
                  : t(`${i18n}.providerGateHint`)}
              </p>
            )}
            <div className="ops-ai-grid ops-ai-fallback-grid">
              <div className="ops-form-field">
                <label htmlFor={`${idPrefix}-fallback`}>{t(`${i18n}.fallbackProvider`)}</label>
                <select
                  id={`${idPrefix}-fallback`}
                  value={form.fallbackProvider}
                  onChange={(event) => setForm({ ...form, fallbackProvider: event.target.value })}
                >
                  <option value="none">none</option>
                  {LLM_PROVIDER_OPTIONS.filter((option) => option.id !== "google_cloud").map((option) => (
                    <option key={`fallback-${option.id}`} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ops-form-field">
                <label htmlFor={`${idPrefix}-fallback-model`}>{t(`${i18n}.fallbackModel`)}</label>
                <input
                  id={`${idPrefix}-fallback-model`}
                  value={form.fallbackModel}
                  onChange={(event) => setForm({ ...form, fallbackModel: event.target.value })}
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>
            </div>
          </section>
        </OpsPanel>
      </main>
    </OpsConsoleShell>
  );
}
