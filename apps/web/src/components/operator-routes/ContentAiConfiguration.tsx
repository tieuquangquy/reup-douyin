"use client";

import { useEffect, useMemo, useState } from "react";
import {
  activateContentAiPrompt,
  createContentAiPrompt,
  fetchContentAiConfig,
  testContentAi,
  updateContentAiConfig,
  updateContentAiPrompt,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import type {
  ContentAiConfig,
  ContentAiConfigUpdate,
  ContentAiFallbackMode,
  ContentAiMode,
  ContentAiProvider,
} from "../../types/content-intelligence";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";


type ConfigurationSection = "CONNECTION" | "PROMPTS";


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

  if (!config || !draft) {
    return <section className="content-ai-page"><p className="muted">{busy === "load" ? t("contentAi.loading") : error || t("contentAi.loadError")}</p></section>;
  }

  return <section className="content-ai-page">
    <header className="content-ai-header"><div><span>{t("contentAi.eyebrow")}</span><strong>{t("contentAi.title")}</strong><small>{t("contentAi.hint")}</small></div><AsyncButton pending={busy === "load"} onClick={() => void load(true)}>{t("common.refresh")}</AsyncButton></header>
    {error ? <div className="inline-error" role="alert">{error}</div> : null}
    <nav aria-label={t("contentAi.sections")} className="content-ai-tabs" role="tablist"><button aria-selected={section === "CONNECTION"} className={section === "CONNECTION" ? "is-active" : ""} onClick={() => setSection("CONNECTION")} role="tab" type="button">{t("contentAi.connectionTab")}</button><button aria-selected={section === "PROMPTS"} className={section === "PROMPTS" ? "is-active" : ""} onClick={() => setSection("PROMPTS")} role="tab" type="button">{t("contentAi.promptsTab")}</button></nav>

    {section === "CONNECTION" ? <>
      <section className="content-ai-status"><article className={draft.enabled ? "is-on" : "is-off"}><span>{t("contentAi.runtime")}</span><strong>{draft.enabled ? t("contentAi.enabled") : t("contentAi.disabled")}</strong><small>{draft.mode.replaceAll("_", " ")}</small></article><article><span>{t("contentAi.provider")}</span><strong>{draft.provider}</strong><small>{draft.model || t("contentAi.modelNotSet")}</small></article><article><span>{t("contentAi.secret")}</span><strong>{config.api_key_set ? t("contentAi.secretStored") : t("contentAi.secretMissing")}</strong><small>{config.api_key_masked || t("contentAi.localNoKey")}</small></article><article><span>{t("contentAi.activePrompt")}</span><strong>{config.active_prompt_name}</strong><small>{config.active_prompt_version}</small></article></section>
      <section className="content-ai-connection-card">
        <header><div><strong>{t("contentAi.policyTitle")}</strong><small>{t("contentAi.policyHint")}</small></div><label className="content-ai-enable"><input checked={draft.enabled} onChange={(event) => patchDraft({ enabled: event.target.checked })} type="checkbox" /><span>{t("contentAi.useAi")}</span></label></header>
        <div className="content-ai-mode-grid">{(["HYBRID", "AI_ONLY", "LOCAL_ONLY"] as ContentAiMode[]).map((mode) => <button className={draft.mode === mode ? "is-selected" : ""} key={mode} onClick={() => patchDraft({ mode })} type="button"><strong>{t(`contentAi.mode.${mode}`)}</strong><small>{t(`contentAi.modeHint.${mode}`)}</small></button>)}</div>
        <div className="content-ai-form-grid">
          <label><span>{t("contentAi.provider")}</span><select onChange={(event) => patchDraft({ provider: event.target.value as ContentAiProvider })} value={draft.provider}><option value="auto">Auto</option><option value="gemini">Gemini</option><option value="openai_compatible">OpenAI-compatible</option><option value="ollama">Ollama</option></select></label>
          <label><span>{t("contentAi.model")}</span><input onChange={(event) => patchDraft({ model: event.target.value })} placeholder={draft.provider === "ollama" ? "qwen2.5:7b" : "gemini-2.0-flash"} value={draft.model} /></label>
          <label className="is-wide"><span>{t("contentAi.baseUrl")}</span><input onChange={(event) => patchDraft({ base_url: event.target.value })} placeholder={draft.provider === "ollama" ? "http://127.0.0.1:11434" : "https://api.openai.com/v1"} value={draft.base_url} /></label>
          <label><span>{t("contentAi.apiKey")}</span><input autoComplete="off" onChange={(event) => { setApiKey(event.target.value); setClearApiKey(false); }} placeholder={config.api_key_set ? t("contentAi.keepSecret") : t("contentAi.enterSecret")} type="password" value={apiKey} /></label>
          <label><span>{t("contentAi.timeout")}</span><input min="5" max="300" onChange={(event) => patchDraft({ timeout_seconds: Number(event.target.value) })} type="number" value={draft.timeout_seconds} /></label>
          <label><span>{t("contentAi.fallback")}</span><select onChange={(event) => patchDraft({ fallback_mode: event.target.value as ContentAiFallbackMode })} value={draft.fallback_mode}><option value="local_keyword">{t("contentAi.localFallback")}</option><option value="none">{t("contentAi.noFallback")}</option></select></label>
          <label><span>{t("contentAi.threshold")}</span><input max="0.99" min="0.5" onChange={(event) => patchDraft({ local_confidence_threshold: Number(event.target.value) })} step="0.01" type="number" value={draft.local_confidence_threshold} /></label>
          <label><span>{t("contentAi.temperature")}</span><input max="1" min="0" onChange={(event) => patchDraft({ temperature: Number(event.target.value) })} step="0.05" type="number" value={draft.temperature} /></label>
          <label><span>{t("contentAi.maxTokens")}</span><input max="4000" min="200" onChange={(event) => patchDraft({ max_output_tokens: Number(event.target.value) })} type="number" value={draft.max_output_tokens} /></label>
        </div>
        {config.api_key_set ? <label className="content-ai-clear-key"><input checked={clearApiKey} onChange={(event) => { setClearApiKey(event.target.checked); if (event.target.checked) setApiKey(""); }} type="checkbox" /><span>{t("contentAi.clearSecret")}</span></label> : null}
        <footer><div>{testResult ? <span className="content-ai-test-result">✓ {t("contentAi.testPassed")} · {testResult}</span> : <small>{t("contentAi.testConsent")}</small>}</div><AsyncButton pending={busy === "test"} onClick={() => void testConnection()}>{t("contentAi.test")}</AsyncButton><AsyncButton className="primary" disabled={!connectionDirty} pending={busy === "save"} onClick={() => void persistConfig()}>{t("common.save")}</AsyncButton></footer>
      </section>
    </> : <section className="content-ai-prompts-layout">
      <aside><header><div><strong>{t("contentAi.promptProfiles")}</strong><small>{t("contentAi.promptProfilesHint")}</small></div></header><div className="content-ai-prompt-list">{config.prompts.map((prompt) => <button className={`${selectedPromptId === prompt.id ? "is-selected" : ""} ${prompt.is_active ? "is-active" : ""}`} key={prompt.id} onClick={() => selectPrompt(prompt.id)} type="button"><span><strong>{prompt.name}</strong><small>{prompt.version}</small></span>{prompt.is_active ? <i>{t("contentAi.active")}</i> : null}</button>)}</div><form onSubmit={(event) => { event.preventDefault(); void createPrompt(); }}><input maxLength={80} onChange={(event) => setNewPromptName(event.target.value)} placeholder={t("contentAi.newPromptName")} value={newPromptName} /><AsyncButton disabled={!newPromptName.trim()} pending={busy === "prompt-create"} type="submit">{t("contentAi.createPrompt")}</AsyncButton></form></aside>
      <section className="content-ai-prompt-editor"><header><div><strong>{t("contentAi.promptEditor")}</strong><small>{t("contentAi.promptSecurityHint")}</small></div>{selectedPrompt ? <span>{selectedPrompt.version}</span> : null}</header><label><span>{t("contentAi.promptName")}</span><input onChange={(event) => setPromptName(event.target.value)} value={promptName} /></label><label><span>{t("contentAi.promptText")}</span><textarea onChange={(event) => setPromptText(event.target.value)} rows={20} value={promptText} /></label><div className="content-ai-template-contract"><strong>{t("contentAi.requiredContract")}</strong><code>{"{{taxonomy}} · {{evidence}} · JSON only"}</code></div><footer><small>{promptText.length} {t("contentAi.characters")}</small><div>{selectedPrompt && !selectedPrompt.is_active ? <AsyncButton pending={busy === `activate-${selectedPrompt.id}`} onClick={() => void activatePrompt(selectedPrompt.id)}>{t("contentAi.activate")}</AsyncButton> : <span className="content-ai-active-note">{t("contentAi.currentlyActive")}</span>}<AsyncButton className="primary" disabled={!promptDirty || promptText.trim().length < 80 || !promptName.trim()} pending={busy === "prompt-save"} onClick={() => void savePrompt()}>{t("contentAi.saveNewVersion")}</AsyncButton></div></footer></section>
    </section>}
  </section>;
}
