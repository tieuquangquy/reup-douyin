"use client";

import { useEffect, useMemo, useState } from "react";
import {
  activateContentAiPrompt,
  createContentAiPrompt,
  deleteContentAiPrompt,
  fetchContentAiConfig,
  listContentAiModels,
  testContentAi,
  updateContentAiConfig,
  updateContentAiPrompt,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import { formatContentAiPromptVersion } from "../../lib/contentAiPromptVersion";
import type {
  ContentAiConfig,
  ContentAiConfigUpdate,
  ContentAiFallbackMode,
  ContentAiMode,
  ContentAiProvider,
} from "../../types/content-intelligence";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { IntelligenceSettingsStageSkeleton } from "./IntelligenceDataSkeleton";
import { PublishingSettingsNav } from "./PublishingSettingsNav";


type ConfigurationSection = "CONNECTION" | "PROMPTS";


function resolveContentAiListProvider(
  provider: ContentAiProvider,
  hasApiKey: boolean,
  baseUrl: string,
  model: string,
): ContentAiProvider {
  if (provider !== "auto") return provider;
  const base = baseUrl.toLowerCase();
  const mid = model.toLowerCase();
  if (base.includes("11434") || (!hasApiKey && mid.includes(":"))) return "ollama";
  if (!base.trim() || base.includes("googleapis.com") || mid.startsWith("gemini")) return "gemini";
  return "openai_compatible";
}


function contentAiModelListReady(
  provider: ContentAiProvider,
  hasApiKey: boolean,
  baseUrl: string,
  model: string,
): boolean {
  const resolved = resolveContentAiListProvider(provider, hasApiKey, baseUrl, model);
  if (resolved === "openai_compatible") return hasApiKey && Boolean(baseUrl.trim());
  if (resolved === "gemini") return hasApiKey;
  if (resolved === "ollama") return Boolean(baseUrl.trim());
  return false;
}


type ContentAiActionIconKind = "refresh" | "reload" | "list" | "edit" | "test" | "save" | "plus" | "check" | "delete";


function ContentAiActionIcon({ kind }: { kind: ContentAiActionIconKind }) {
  if (kind === "save") {
    return (
      <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
        <path d="M4.5 4.5h9.2L15.5 6.3V15.5H4.5V4.5z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.75" />
        <path d="M7 4.5v3.8h5.2V4.5M7 15.5v-4.2h6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
      </svg>
    );
  }
  if (kind === "test") {
    return (
      <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
        <path d="M7.2 12.8 12.8 7.2M8.4 6.4l1.2-1.2a2.1 2.1 0 0 1 3 3L11.4 9.4M11.6 13.6l-1.2 1.2a2.1 2.1 0 0 1-3-3l1.2-1.2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
      </svg>
    );
  }
  if (kind === "list") {
    return (
      <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
        <path d="M4.5 5.5h11M4.5 10h11M4.5 14.5h11" stroke="currentColor" strokeLinecap="round" strokeWidth="1.75" />
      </svg>
    );
  }
  if (kind === "edit") {
    return (
      <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
        <path d="M3.6 16.4h3.4L15.6 7.8a1.5 1.5 0 0 0 0-2.1L14.3 4.4a1.5 1.5 0 0 0-2.1 0L3.6 13.1v3.3z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.75" />
        <path d="M11.2 5.6 14.4 8.8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.75" />
      </svg>
    );
  }
  if (kind === "plus") {
    return (
      <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
        <path d="M10 4.5v11M4.5 10h11" stroke="currentColor" strokeLinecap="round" strokeWidth="1.75" />
      </svg>
    );
  }
  if (kind === "delete") {
    return (
      <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
        <path d="M7.2 4.5h5.6M5 6.5h10" stroke="currentColor" strokeLinecap="round" strokeWidth="1.75" />
        <path d="M8 8.4v5M12 8.4v5M6.5 6.5l.55 8.1a1.4 1.4 0 0 0 1.4 1.3h3.1a1.4 1.4 0 0 0 1.4-1.3l.55-8.1" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
      </svg>
    );
  }
  if (kind === "check") {
    return (
      <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
        <path d="m5.2 10.4 3.1 3.1 6.5-6.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
      </svg>
    );
  }
  if (kind === "reload") {
    return (
      <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
        <path d="M4.5 10a5.5 5.5 0 0 1 9.4-3.9M15.5 10a5.5 5.5 0 0 1-9.4 3.9" stroke="currentColor" strokeLinecap="round" strokeWidth="1.75" />
        <path d="M14.2 3.8v3.2h-3.2M5.8 16.2v-3.2h3.2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="content-ai-action-icon" fill="none" viewBox="0 0 20 20">
      <path d="M15.8 6.8V10h-3.2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
      <path d="M4.2 13.2V10h3.2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
      <path d="M6.1 7.6a5.2 5.2 0 0 1 8.6-1.4L15.8 7.6M4.2 12.4l1.4 1.4a5.2 5.2 0 0 0 8.6-1.4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
    </svg>
  );
}


function editableConfig(config: ContentAiConfig): ContentAiConfigUpdate {
  return {
    enabled: config.enabled,
    provider: config.provider,
    model: config.model,
    base_url: config.base_url,
    timeout_seconds: config.timeout_seconds,
    fallback_mode: config.fallback_mode,
    mode: config.mode,
    local_confidence_threshold: config.local_confidence_threshold,
    temperature: config.temperature,
    max_output_tokens: config.max_output_tokens,
  };
}


export function ContentAiConfiguration() {
  const t = useT();
  const { notify } = useNotice();
  const [config, setConfig] = useState<ContentAiConfig | null>(null);
  const [draft, setDraft] = useState<ContentAiConfigUpdate | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [section, setSection] = useState<ConfigurationSection>("CONNECTION");
  const [selectedPromptId, setSelectedPromptId] = useState("");
  const [promptName, setPromptName] = useState("");
  const [promptText, setPromptText] = useState("");
  const [newPromptName, setNewPromptName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [manualModel, setManualModel] = useState(true);
  const [modelListError, setModelListError] = useState<string | null>(null);

  function applyConfig(payload: ContentAiConfig, preferredPromptId?: string) {
    setConfig(payload);
    setDraft(editableConfig(payload));
    const prompt = payload.prompts.find((item) => item.id === (preferredPromptId || selectedPromptId))
      ?? payload.prompts.find((item) => item.is_active)
      ?? payload.prompts[0];
    setSelectedPromptId(prompt?.id ?? "");
    setPromptName(prompt?.name ?? "");
    setPromptText(prompt?.prompt ?? "");
    setApiKey("");
    setClearApiKey(false);
    setModelOptions(payload.model ? [payload.model] : []);
    setManualModel(true);
    setModelListError(null);
  }

  async function load(showNotice = false) {
    setBusy("load");
    setError(null);
    try {
      const payload = await fetchContentAiConfig();
      applyConfig(payload);
      if (showNotice) notify({ message: t("contentAi.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentAi.loadError"));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => { void load(); }, []);

  function patchDraft(patch: Partial<ContentAiConfigUpdate>) {
    setDraft((current) => current ? { ...current, ...patch } : current);
    setTestResult(null);
  }

  async function persistConfig(showNotice = true): Promise<boolean> {
    if (!draft) return false;
    setBusy("save");
    setError(null);
    try {
      const payload = await updateContentAiConfig({
        ...draft,
        api_key: apiKey.trim() || undefined,
        clear_api_key: clearApiKey,
      });
      applyConfig(payload);
      if (showNotice) notify({ message: t("contentAi.saved"), tone: "success" });
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentAi.saveError"));
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function testConnection() {
    if (!await persistConfig(false)) return;
    setBusy("test");
    setError(null);
    setTestResult(null);
    try {
      const result = await testContentAi();
      setTestResult(`${result.provider} · ${result.model}`);
      notify({ message: t("contentAi.testPassed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentAi.testError"));
    } finally {
      setBusy(null);
    }
  }

  async function refreshModels() {
    if (!draft || !contentAiModelListReady(
      draft.provider,
      Boolean(apiKey.trim() || (config?.api_key_set && !clearApiKey)),
      draft.base_url,
      draft.model,
    )) return;
    setBusy("models");
    setModelListError(null);
    try {
      const result = await listContentAiModels({
        provider: draft.provider,
        api_key: apiKey.trim() || null,
        clear_api_key: clearApiKey,
        base_url: draft.base_url.trim() || null,
        timeout_seconds: 12,
      });
      if (result.models.length > 0) {
        const next = draft.model && !result.models.includes(draft.model)
          ? [draft.model, ...result.models]
          : result.models;
        setModelOptions(next);
        setManualModel(false);
        setModelListError(result.ok ? null : (result.detail || t("contentAi.modelsEmpty")));
      } else {
        setModelOptions(draft.model ? [draft.model] : []);
        setManualModel(true);
        setModelListError(result.detail || t("contentAi.modelsEmpty"));
      }
    } catch (err) {
      setModelOptions(draft.model ? [draft.model] : []);
      setManualModel(true);
      setModelListError(err instanceof Error ? err.message : t("contentAi.modelsError"));
    } finally {
      setBusy(null);
    }
  }

  function selectPrompt(promptId: string) {
    const prompt = config?.prompts.find((item) => item.id === promptId);
    if (!prompt) return;
    setSelectedPromptId(prompt.id);
    setPromptName(prompt.name);
    setPromptText(prompt.prompt);
    setError(null);
  }

  async function savePrompt() {
    if (!selectedPromptId || promptText.trim().length < 80 || !promptName.trim()) return;
    setBusy("prompt-save");
    setError(null);
    try {
      const payload = await updateContentAiPrompt(selectedPromptId, {
        name: promptName.trim(),
        prompt: promptText.trim(),
      });
      applyConfig(payload, selectedPromptId);
      notify({ message: t("contentAi.promptSaved"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentAi.promptSaveError"));
    } finally {
      setBusy(null);
    }
  }

  async function activatePrompt(promptId: string) {
    setBusy(`activate-${promptId}`);
    setError(null);
    try {
      const payload = await activateContentAiPrompt(promptId);
      applyConfig(payload, promptId);
      notify({ message: t("contentAi.promptActivated"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentAi.promptActivateError"));
    } finally {
      setBusy(null);
    }
  }

  async function createPrompt() {
    if (!newPromptName.trim()) return;
    setBusy("prompt-create");
    setError(null);
    try {
      const payload = await createContentAiPrompt(newPromptName.trim());
      const created = payload.prompts.find((item) => item.name === newPromptName.trim());
      applyConfig(payload, created?.id);
      setNewPromptName("");
      notify({ message: t("contentAi.promptCreated"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentAi.promptCreateError"));
    } finally {
      setBusy(null);
    }
  }

  async function deletePrompt(promptId: string, name: string) {
    if (!config || config.prompts.length <= 1) {
      setError(t("contentAi.deleteLastError"));
      return;
    }
    if (!window.confirm(`${t("contentAi.deletePromptConfirm")} (${name})`)) return;
    setBusy(`delete-${promptId}`);
    setError(null);
    try {
      const payload = await deleteContentAiPrompt(promptId);
      const nextId = payload.prompts.find((item) => item.id === selectedPromptId)?.id
        ?? payload.prompts.find((item) => item.is_active)?.id
        ?? payload.prompts[0]?.id;
      applyConfig(payload, nextId);
      notify({ message: t("contentAi.promptDeleted"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentAi.promptDeleteError"));
    } finally {
      setBusy(null);
    }
  }

  const selectedPrompt = useMemo(
    () => config?.prompts.find((item) => item.id === selectedPromptId) ?? null,
    [config, selectedPromptId],
  );
  const connectionDirty = Boolean(config && draft && (
    JSON.stringify(editableConfig(config)) !== JSON.stringify(draft) || apiKey.trim() || clearApiKey
  ));
  const promptDirty = Boolean(selectedPrompt && (
    promptName !== selectedPrompt.name || promptText !== selectedPrompt.prompt
  ));
  const hasApiKey = Boolean(apiKey.trim() || (config?.api_key_set && !clearApiKey));
  const readyForModels = Boolean(
    draft && contentAiModelListReady(draft.provider, hasApiKey, draft.base_url, draft.model),
  );

  useEffect(() => {
    if (!draft || !readyForModels) {
      if (draft && !readyForModels) setModelListError(null);
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshModels();
    }, 700);
    return () => window.clearTimeout(timer);
  }, [draft?.provider, draft?.base_url, apiKey, clearApiKey, config?.api_key_set, readyForModels]);

  if (!config || !draft) {
    if (!error) {
      return (
        <OperatorStudioShell
          actions={<TopbarRefreshButton busy={busy === "load"} disabled={busy === "load"} onClick={() => void load(true)} />}
          description={t("publishingSettings.contentIntelligenceHint")}
          title={t("publishingSettings.contentIntelligence")}
        >
          <main className="publishing-settings-page is-v1 is-v4">
            <PublishingSettingsNav />
            <section className="content-ai-page is-v6">
              <IntelligenceSettingsStageSkeleton label={t("contentAi.loading")} />
            </section>
          </main>
        </OperatorStudioShell>
      );
    }
    return (
      <OperatorStudioShell
        actions={<TopbarRefreshButton busy={busy === "load"} disabled={busy === "load"} onClick={() => void load(true)} />}
        description={t("publishingSettings.contentIntelligenceHint")}
        title={t("publishingSettings.contentIntelligence")}
      >
        <main className="publishing-settings-page is-v1 is-v4">
          <PublishingSettingsNav />
          <section className="content-ai-page is-v6"><p className="muted">{error || t("contentAi.loadError")}</p></section>
        </main>
      </OperatorStudioShell>
    );
  }

  const meterClass = draft.mode === "AI_ONLY" ? "is-ai" : draft.mode === "LOCAL_ONLY" ? "is-local" : "is-hybrid";

  return (
    <OperatorStudioShell
      actions={<TopbarRefreshButton busy={busy === "load"} disabled={busy === "load"} onClick={() => void load(true)} />}
      description={t("publishingSettings.contentIntelligenceHint")}
      title={t("publishingSettings.contentIntelligence")}
    >
      <main className="publishing-settings-page is-v1 is-v4">
        <PublishingSettingsNav />
    <section className="content-ai-page is-v6">
      <div className="content-ai-stage">
        <aside className="content-ai-stage__panel">
          <header>
            <strong>{t("contentAi.title")}</strong>
            <small>{t("contentAi.hint")}</small>
          </header>
          <div className={`content-ai-stage__meter ${meterClass}`} aria-hidden="true">
            <b>{t(`contentAi.mode.${draft.mode}`)}</b>
            <small>{draft.enabled ? t("contentAi.enabled") : t("contentAi.disabled")}</small>
          </div>
          <dl className="content-ai-stage__facts">
            <div>
              <dt>{t("contentAi.provider")}</dt>
              <dd className="is-mono" title={`${draft.provider} · ${draft.model || t("contentAi.modelNotSet")}`}>{draft.model || draft.provider}</dd>
            </div>
            <div>
              <dt>{t("contentAi.secret")}</dt>
              <dd>{config.api_key_set ? t("contentAi.secretStored") : t("contentAi.secretMissing")}</dd>
            </div>
            <div>
              <dt>{t("contentAi.activePrompt")}</dt>
              <dd title={config.active_prompt_name}>{config.active_prompt_name}</dd>
            </div>
          </dl>
          <nav aria-label={t("contentAi.sections")} className="content-ai-stage__tabs" role="tablist">
            <button aria-selected={section === "CONNECTION"} className={section === "CONNECTION" ? "is-active" : ""} onClick={() => setSection("CONNECTION")} role="tab" type="button">{t("contentAi.connectionTab")}</button>
            <button aria-selected={section === "PROMPTS"} className={section === "PROMPTS" ? "is-active" : ""} onClick={() => setSection("PROMPTS")} role="tab" type="button">{t("contentAi.promptsTab")}</button>
          </nav>
          <AsyncButton className="content-ai-stage__refresh" leadingIcon={<ContentAiActionIcon kind="refresh" />} pending={busy === "load"} onClick={() => void load(true)}>{t("common.refresh")}</AsyncButton>
        </aside>

        <div className="content-ai-worksheet">
          {section === "CONNECTION" ? (
            <>
              <div className="content-ai-worksheet__policy">
                <div>
                  <strong>{t("contentAi.policyTitle")}</strong>
                  <small>{t("contentAi.policyHint")}</small>
                </div>
                <div className="content-ai-modes is-stage" role="group" aria-label={t("contentAi.policyTitle")}>
                  {(["HYBRID", "AI_ONLY", "LOCAL_ONLY"] as ContentAiMode[]).map((mode) => (
                    <button className={draft.mode === mode ? "is-selected" : ""} key={mode} onClick={() => patchDraft({ mode })} type="button">
                      <strong>{t(`contentAi.mode.${mode}`)}</strong>
                      <small>{t(`contentAi.modeHint.${mode}`)}</small>
                    </button>
                  ))}
                </div>
                <label className="content-ai-enable">
                  <input checked={draft.enabled} onChange={(event) => patchDraft({ enabled: event.target.checked })} type="checkbox" />
                  <span>{t("contentAi.useAi")}</span>
                </label>
              </div>

              <div className="content-ai-form-group">
                <span className="content-ai-form-group__eyebrow">{t("contentAi.connectionGroup")}</span>
                <div className="content-ai-form-grid is-v1">
                  <label>
                    <span>{t("contentAi.provider")}</span>
                    <select onChange={(event) => patchDraft({ provider: event.target.value as ContentAiProvider })} value={draft.provider}>
                      <option value="auto">Auto</option>
                      <option value="gemini">Gemini</option>
                      <option value="openai_compatible">OpenAI-compatible</option>
                      <option value="ollama">Ollama</option>
                    </select>
                  </label>
                  <label>
                    <span>{t("contentAi.timeout")}</span>
                    <input min="5" max="300" onChange={(event) => patchDraft({ timeout_seconds: Number(event.target.value) })} type="number" value={draft.timeout_seconds} />
                  </label>
                  <label className="is-wide">
                    <span>{t("contentAi.baseUrl")}</span>
                    <input onChange={(event) => patchDraft({ base_url: event.target.value })} placeholder={draft.provider === "ollama" ? "http://127.0.0.1:11434" : "https://api.openai.com/v1"} value={draft.base_url} />
                  </label>
                  <label className="is-wide">
                    <span>{t("contentAi.apiKey")}</span>
                    <input autoComplete="off" onChange={(event) => { setApiKey(event.target.value); setClearApiKey(false); }} placeholder={config.api_key_set ? (config.api_key_masked || t("contentAi.keepSecret")) : t("contentAi.enterSecret")} spellCheck={false} type="text" value={apiKey} />
                  </label>
                  <div className="content-ai-model-field is-wide">
                    <label>
                      <span>{t("contentAi.model")}</span>
                      {manualModel || modelOptions.length === 0 ? (
                        <input onChange={(event) => patchDraft({ model: event.target.value })} placeholder={draft.provider === "ollama" ? "qwen2.5:7b" : "gemini-2.0-flash"} value={draft.model} />
                      ) : (
                        <select onChange={(event) => patchDraft({ model: event.target.value })} value={draft.model}>
                          <option value="">{t("contentAi.modelSelectPlaceholder")}</option>
                          {modelOptions.map((name) => (
                            <option key={name} value={name}>{name}</option>
                          ))}
                        </select>
                      )}
                    </label>
                    <div className="content-ai-model-actions">
                      <AsyncButton disabled={!readyForModels} leadingIcon={<ContentAiActionIcon kind="reload" />} pending={busy === "models"} pendingLabel={t("contentAi.loadingModels")} onClick={() => void refreshModels()}>{t("contentAi.loadModels")}</AsyncButton>
                      <button onClick={() => setManualModel((value) => !value)} type="button">
                        <ContentAiActionIcon kind={manualModel ? "list" : "edit"} />
                        <span>{manualModel ? t("contentAi.useModelList") : t("contentAi.typeModelManually")}</span>
                      </button>
                    </div>
                    {modelListError ? (
                      <p className="content-ai-worksheet__note" role="status">
                        <span>{t("contentAi.model")}</span>
                        {modelListError}
                      </p>
                    ) : null}
                  </div>
                </div>
                {config.api_key_set ? (
                  <label className="content-ai-clear-key">
                    <input checked={clearApiKey} onChange={(event) => { setClearApiKey(event.target.checked); if (event.target.checked) setApiKey(""); }} type="checkbox" />
                    <span>{t("contentAi.clearSecret")}</span>
                  </label>
                ) : null}
              </div>

              <div className="content-ai-form-group">
                <span className="content-ai-form-group__eyebrow">{t("contentAi.tuningGroup")}</span>
                <div className="content-ai-form-grid is-v1 is-behavior">
                  <label>
                    <span>{t("contentAi.fallback")}</span>
                    <select onChange={(event) => patchDraft({ fallback_mode: event.target.value as ContentAiFallbackMode })} value={draft.fallback_mode}>
                      <option value="local_keyword">{t("contentAi.localFallback")}</option>
                      <option value="none">{t("contentAi.noFallback")}</option>
                    </select>
                  </label>
                  <label>
                    <span>{t("contentAi.threshold")}</span>
                    <input max="0.99" min="0.5" onChange={(event) => patchDraft({ local_confidence_threshold: Number(event.target.value) })} step="0.01" type="number" value={draft.local_confidence_threshold} />
                  </label>
                  <label>
                    <span>{t("contentAi.temperature")}</span>
                    <input max="1" min="0" onChange={(event) => patchDraft({ temperature: Number(event.target.value) })} step="0.05" type="number" value={draft.temperature} />
                  </label>
                  <label>
                    <span>{t("contentAi.maxTokens")}</span>
                    <input max="4000" min="200" onChange={(event) => patchDraft({ max_output_tokens: Number(event.target.value) })} type="number" value={draft.max_output_tokens} />
                  </label>
                </div>
              </div>

              <footer className="content-ai-worksheet__footer">
                <div>
                  {error ? (
                    <p className="content-ai-worksheet__note" role="alert">
                      <span>{t("contentAi.connectionGroup")}</span>
                      {error}
                    </p>
                  ) : testResult ? (
                    <span className="content-ai-test-result">✓ {t("contentAi.testPassed")} · {testResult}</span>
                  ) : (
                    <small>{t("contentAi.testConsent")}</small>
                  )}
                </div>
                <AsyncButton leadingIcon={<ContentAiActionIcon kind="test" />} pending={busy === "test"} onClick={() => void testConnection()}>{t("contentAi.test")}</AsyncButton>
                <AsyncButton className="primary" disabled={!connectionDirty} leadingIcon={<ContentAiActionIcon kind="save" />} pending={busy === "save"} onClick={() => void persistConfig()}>{t("common.save")}</AsyncButton>
              </footer>
            </>
          ) : (
            <section className="content-ai-prompts-layout">
              <aside>
                <header>
                  <div>
                    <strong>{t("contentAi.promptProfiles")}</strong>
                    <small>{t("contentAi.promptProfilesHint")}</small>
                  </div>
                </header>
                <div className="content-ai-prompt-list">
                  {config.prompts.map((prompt) => (
                    <div className={`content-ai-prompt-row ${selectedPromptId === prompt.id ? "is-selected" : ""} ${prompt.is_active ? "is-active" : ""}`} key={prompt.id}>
                      <button onClick={() => selectPrompt(prompt.id)} type="button">
                        <span>
                          <strong>{prompt.name}</strong>
                          <small className="content-ai-prompt-version" title={prompt.version}>{formatContentAiPromptVersion(prompt.version)}</small>
                        </span>
                        {prompt.is_active ? <i>{t("contentAi.active")}</i> : null}
                      </button>
                      <AsyncButton
                        aria-label={t("contentAi.deletePrompt")}
                        className="content-ai-icon-btn"
                        disabled={config.prompts.length <= 1}
                        leadingIcon={<ContentAiActionIcon kind="delete" />}
                        pending={busy === `delete-${prompt.id}`}
                        onClick={() => void deletePrompt(prompt.id, prompt.name)}
                      >
                        {t("contentAi.deletePrompt")}
                      </AsyncButton>
                    </div>
                  ))}
                </div>
                <form onSubmit={(event) => { event.preventDefault(); void createPrompt(); }}>
                  <input maxLength={80} onChange={(event) => setNewPromptName(event.target.value)} placeholder={t("contentAi.newPromptName")} value={newPromptName} />
                  <AsyncButton aria-label={t("contentAi.createPrompt")} className="content-ai-icon-btn" disabled={!newPromptName.trim()} leadingIcon={<ContentAiActionIcon kind="plus" />} pending={busy === "prompt-create"} type="submit">{t("contentAi.createPrompt")}</AsyncButton>
                </form>
              </aside>
              <section className="content-ai-prompt-editor">
                <header>
                  <div>
                    <strong>{t("contentAi.promptEditor")}</strong>
                    <small>{t("contentAi.promptSecurityHint")}</small>
                  </div>
                  {selectedPrompt ? <code className="content-ai-prompt-version" title={selectedPrompt.version}>{formatContentAiPromptVersion(selectedPrompt.version)}</code> : null}
                </header>
                <label>
                  <span>{t("contentAi.promptName")}</span>
                  <input onChange={(event) => setPromptName(event.target.value)} value={promptName} />
                </label>
                <label>
                  <span>{t("contentAi.promptText")}</span>
                  <textarea onChange={(event) => setPromptText(event.target.value)} rows={20} value={promptText} />
                </label>
                <footer>
                  {error ? (
                    <p className="content-ai-worksheet__note" role="alert">
                      <span>{t("contentAi.promptsTab")}</span>
                      {error}
                    </p>
                  ) : (
                    <div className="content-ai-prompt-editor__meta">
                      <small>{promptText.length} {t("contentAi.characters")}</small>
                      <p className="content-ai-template-contract">
                        <strong>{t("contentAi.requiredContract")}</strong>
                        <code>{"{{taxonomy}} · {{evidence}} · JSON only"}</code>
                      </p>
                    </div>
                  )}
                  <div>
                    {selectedPrompt && !selectedPrompt.is_active ? (
                      <AsyncButton leadingIcon={<ContentAiActionIcon kind="check" />} pending={busy === `activate-${selectedPrompt.id}`} onClick={() => void activatePrompt(selectedPrompt.id)}>{t("contentAi.activate")}</AsyncButton>
                    ) : null}
                    <AsyncButton className="primary" disabled={!promptDirty || promptText.trim().length < 80 || !promptName.trim()} leadingIcon={<ContentAiActionIcon kind="save" />} pending={busy === "prompt-save"} onClick={() => void savePrompt()}>{t("contentAi.saveNewVersion")}</AsyncButton>
                  </div>
                </footer>
              </section>
            </section>
          )}
        </div>
      </div>
    </section>
      </main>
    </OperatorStudioShell>
  );
}
