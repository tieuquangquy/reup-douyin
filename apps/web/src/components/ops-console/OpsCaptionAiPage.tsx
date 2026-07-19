"use client";

import { useEffect, useState } from "react";
import {
  fetchCaptionAi,
  listCaptionAiModels,
  saveCaptionAi,
  testCaptionAi,
  type TranslationAiResponse
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import {
  formatConnectionTestSummary,
  formatProviderError,
  type ConnectionTestResult,
  type ProviderErrorView
} from "../../lib/opsTranslationAiFormat";
import { OpsPanel, OpsState } from "./OpsShared";
import { OpsCaptionSettingsTabs } from "./OpsCaptionSettingsTabs";

type FormState = {
  enabled: boolean;
  provider: string;
  model: string;
  apiKeyInput: string;
  clearApiKey: boolean;
  baseUrl: string;
  timeoutSeconds: string;
  fallbackProvider: string;
  fallbackModel: string;
};

/** Provider-aware gate: Model picker only after required connection fields are filled. */
export function captionModelListReady(provider: string, hasApiKey: boolean, baseUrl: string): boolean {
  const mode = provider.trim().toLowerCase();
  const base = baseUrl.trim();
  if (mode === "openai_compatible") return hasApiKey && Boolean(base);
  if (mode === "gemini") return hasApiKey;
  if (mode === "ollama") return Boolean(base);
  return false;
}

export function captionCanShowModel(provider: string, hasApiKey: boolean, baseUrl: string): boolean {
  return captionModelListReady(provider, hasApiKey, baseUrl);
}

function showsBaseUrl(provider: string): boolean {
  const mode = provider.trim().toLowerCase();
  return mode === "openai_compatible" || mode === "ollama";
}

function showsApiKey(provider: string): boolean {
  const mode = provider.trim().toLowerCase();
  return mode === "openai_compatible" || mode === "gemini";
}

function toForm(data: TranslationAiResponse): FormState {
  return {
    enabled: data.enabled,
    provider: data.provider || "auto",
    model: data.model || "",
    apiKeyInput: "",
    clearApiKey: false,
    baseUrl: data.base_url || "",
    timeoutSeconds: String(data.timeout_seconds ?? 90),
    fallbackProvider: data.fallback_provider || "none",
    fallbackModel: data.fallback_model || ""
  };
}

export function OpsCaptionAiPage() {
  const t = useT();
  const [form, setForm] = useState<FormState | null>(null);
  const [meta, setMeta] = useState<{ apiKeySet: boolean; apiKeyMasked: string; source: string }>({
    apiKeySet: false,
    apiKeyMasked: "",
    source: "env"
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelListError, setModelListError] = useState<ProviderErrorView | null>(null);
  const [manualModel, setManualModel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    setSavedMessage(null);
    setTestResult(null);
    try {
      const data = await fetchCaptionAi();
      setForm(toForm(data));
      setMeta({
        apiKeySet: data.api_key_set,
        apiKeyMasked: data.api_key_masked,
        source: data.source
      });
      setManualModel(false);
      setModelOptions(data.model ? [data.model] : []);
      setModelListError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsCaptionAi.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  useEffect(() => {
    if (!savedMessage) return;
    const timer = window.setTimeout(() => setSavedMessage(null), 4000);
    return () => window.clearTimeout(timer);
  }, [savedMessage]);

  const hasApiKey =
    Boolean(form) &&
    !form!.clearApiKey &&
    (Boolean(form!.apiKeyInput.trim()) || meta.apiKeySet);
  const readyForModels = form ? captionModelListReady(form.provider, hasApiKey, form.baseUrl) : false;
  const showModel = form ? captionCanShowModel(form.provider, hasApiKey, form.baseUrl) : false;

  function providerErrorLabels() {
    return {
      unauthorized: t("opsCaptionAi.errorUnauthorized"),
      forbidden: t("opsCaptionAi.errorForbidden"),
      notFound: t("opsCaptionAi.errorNotFound"),
      rateLimited: t("opsCaptionAi.errorRateLimited"),
      failed: t("opsCaptionAi.errorFailed"),
      checkKey: t("opsCaptionAi.errorCheckKey"),
      checkEndpoint: t("opsCaptionAi.errorCheckEndpoint")
    };
  }

  async function refreshModels() {
    if (!form || !readyForModels) return;
    setLoadingModels(true);
    setModelListError(null);
    try {
      const payload: Parameters<typeof listCaptionAiModels>[0] = {
        provider: form.provider,
        base_url: form.baseUrl.trim() || null,
        clear_api_key: form.clearApiKey,
        timeout_seconds: Number(form.timeoutSeconds) || 30
      };
      if (!form.clearApiKey && form.apiKeyInput.trim()) {
        payload.api_key = form.apiKeyInput.trim();
      } else if (!form.clearApiKey) {
        payload.api_key = null;
      }
      const result = await listCaptionAiModels(payload);
      if (result.ok && result.models.length > 0) {
        setModelOptions(result.models);
        setManualModel(false);
        if (form.model && !result.models.includes(form.model)) {
          setModelOptions([form.model, ...result.models]);
        }
        setModelListError(null);
      } else {
        setModelOptions(form.model ? [form.model] : []);
        setManualModel(true);
        setModelListError(
          formatProviderError(result.detail || t("opsCaptionAi.modelsEmpty"), providerErrorLabels())
        );
      }
    } catch (err) {
      setModelOptions(form.model ? [form.model] : []);
      setManualModel(true);
      setModelListError(
        formatProviderError(
          err instanceof Error ? err.message : t("opsCaptionAi.modelsError"),
          providerErrorLabels()
        )
      );
    } finally {
      setLoadingModels(false);
    }
  }

  useEffect(() => {
    if (!form || !readyForModels) {
      if (form && !readyForModels) {
        setModelListError(null);
      }
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshModels();
    }, 400);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reload when credentials change
  }, [form?.provider, form?.baseUrl, form?.apiKeyInput, form?.clearApiKey, meta.apiKeySet, readyForModels]);

  function buildPayload() {
    if (!form) return null;
    const timeout = Number(form.timeoutSeconds);
    const payload: Parameters<typeof saveCaptionAi>[0] = {
      enabled: form.enabled,
      provider: form.provider,
      model: form.model.trim(),
      base_url: form.baseUrl.trim(),
      timeout_seconds: Number.isFinite(timeout) && timeout > 0 ? timeout : 90,
      fallback_provider: form.fallbackProvider,
      fallback_model: form.fallbackModel.trim(),
      clear_api_key: form.clearApiKey
    };
    if (!form.clearApiKey && form.apiKeyInput.trim()) {
      payload.api_key = form.apiKeyInput.trim();
    } else if (!form.clearApiKey) {
      payload.api_key = null;
    }
    return payload;
  }

  async function onSave() {
    const payload = buildPayload();
    if (!payload) return;
    setSaving(true);
    setError(null);
    setSavedMessage(null);
    try {
      const data = await saveCaptionAi(payload);
      setForm(toForm(data));
      setMeta({
        apiKeySet: data.api_key_set,
        apiKeyMasked: data.api_key_masked,
        source: data.source
      });
      setSavedMessage(t("opsCaptionAi.saved"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsCaptionAi.saveError"));
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    const payload = buildPayload();
    if (!payload) return;
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const result = await testCaptionAi(payload);
      setTestResult({
        ok: result.ok,
        provider: result.provider,
        detail: result.detail
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsCaptionAi.testError"));
    } finally {
      setTesting(false);
    }
  }

  function onProviderChange(next: string) {
    if (!form) return;
    const patch: FormState = { ...form, provider: next };
    if (next === "ollama" && !patch.baseUrl.trim()) {
      patch.baseUrl = "http://127.0.0.1:11434";
    }
    if (next === "openai_compatible" && !patch.baseUrl.trim()) {
      patch.baseUrl = "https://api.openai.com/v1";
    }
    setForm(patch);
    setManualModel(false);
    setModelOptions([]);
    setModelListError(null);
  }

  if (loading || !form) {
    return <OpsState title={t("ops.loadingTitle")} detail={t("opsCaptionAi.loadingDetail")} />;
  }

  const testFailure =
    testResult && !testResult.ok
      ? formatProviderError(testResult.detail || t("opsCaptionAi.testFail"), providerErrorLabels())
      : null;

  return (
    <main className="ops-page ops-page--settings ops-ai-page is-compact">
      <OpsCaptionSettingsTabs />

      {error ? <div className="inline-error">{error}</div> : null}

      <OpsPanel
        title={t("opsCaptionAi.panelTitle")}
        actions={
          <div className="ops-header-actions ops-ai-toolbar" role="group" aria-label={t("opsCaptionAi.panelTitle")}>
            {savedMessage ? <span className="ops-connection-status is-ok">{t("opsCaptionAi.saved")}</span> : null}
            {testResult?.ok ? (
              <span className="ops-connection-status is-ok">
                {formatConnectionTestSummary(testResult, {
                  ok: t("opsCaptionAi.testOk"),
                  fail: t("opsCaptionAi.testFail")
                })}
              </span>
            ) : null}
            <div className="ops-ai-toolbar__group">
              <button
                type="button"
                className="ops-ai-toolbar__refresh"
                onClick={() => void load()}
                disabled={saving || testing}
                aria-label={t("common.refresh")}
                title={t("common.refresh")}
              >
                <span aria-hidden="true">↻</span>
              </button>
              <button type="button" onClick={() => void onTest()} disabled={saving || testing}>
                {testing ? t("opsCaptionAi.testing") : t("opsCaptionAi.test")}
              </button>
              <button type="button" className="primary" onClick={() => void onSave()} disabled={saving || testing}>
                {saving ? t("opsCaptionAi.saving") : t("opsCaptionAi.save")}
              </button>
            </div>
          </div>
        }
        meta={
          <div className="ops-ai-meta">
            <div className="ops-ai-status" aria-label={t("opsCaptionAi.statusLabel")}>
              <span className={`ops-ai-chip ${meta.source === "workspace_db" ? "is-active" : "is-muted"}`}>
                {meta.source === "workspace_db" ? t("opsCaptionAi.sourceDbShort") : t("opsCaptionAi.sourceEnvShort")}
              </span>
              <span className={`ops-ai-chip ${meta.apiKeySet ? "is-ok" : "is-muted"}`}>
                {meta.apiKeySet ? `${t("opsCaptionAi.keySet")}: ${meta.apiKeyMasked}` : t("opsCaptionAi.keyUnset")}
              </span>
              <span className="ops-ai-chip is-muted">{form.provider}</span>
              <label className="ops-ai-toggle ops-ai-toggle--flush" title={t("opsCaptionAi.disableHint")}>
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
                />
                <span>
                  <strong>{t("opsCaptionAi.enabled")}</strong>
                </span>
              </label>
            </div>
          </div>
        }
      >
        {testFailure ? (
          <div className="ops-field-alert is-error" role="alert" title={testResult?.detail || undefined}>
            <strong>
              {testFailure.title}
              {testFailure.httpStatus ? ` · HTTP ${testFailure.httpStatus}` : ""}
              {testResult?.provider ? ` · ${testResult.provider}` : ""}
            </strong>
            <span>{testFailure.message}</span>
            <span className="ops-field-alert-hint">{t("opsCaptionAi.testErrorHint")}</span>
          </div>
        ) : null}

        <section className="ops-ai-section">
          <header className="ops-ai-section__head">
            <h3>{t("opsCaptionAi.sectionConnection")}</h3>
          </header>
          <div className="ops-ai-grid">
            <div className="ops-form-field">
              <label htmlFor="caption-ai-provider">{t("opsCaptionAi.provider")}</label>
              <select
                id="caption-ai-provider"
                value={form.provider}
                onChange={(event) => onProviderChange(event.target.value)}
              >
                <option value="auto">auto</option>
                <option value="gemini">gemini</option>
                <option value="openai_compatible">openai_compatible</option>
                <option value="ollama">ollama</option>
                <option value="placeholder">placeholder</option>
              </select>
            </div>
            <div className="ops-form-field">
              <label htmlFor="caption-ai-timeout">{t("opsCaptionAi.timeout")}</label>
              <input
                id="caption-ai-timeout"
                type="number"
                min={1}
                max={600}
                value={form.timeoutSeconds}
                onChange={(event) => setForm({ ...form, timeoutSeconds: event.target.value })}
              />
            </div>
            {showsBaseUrl(form.provider) ? (
              <div className="ops-form-field ops-ai-span-2">
                <label htmlFor="caption-ai-base-url">{t("opsCaptionAi.baseUrl")}</label>
                <input
                  id="caption-ai-base-url"
                  name="caption-ai-base-url"
                  type="text"
                  inputMode="url"
                  value={form.baseUrl}
                  onChange={(event) => setForm({ ...form, baseUrl: event.target.value })}
                  placeholder={
                    form.provider === "ollama" ? "http://127.0.0.1:11434" : "https://api.openai.com/v1"
                  }
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>
            ) : null}
            {showsApiKey(form.provider) ? (
              <>
                <div className="ops-form-field ops-ai-span-2">
                  <label htmlFor="caption-ai-api-key">{t("opsCaptionAi.apiKey")}</label>
                  <input
                    id="caption-ai-api-key"
                    name="caption-ai-api-key"
                    type="password"
                    value={form.apiKeyInput}
                    onChange={(event) => setForm({ ...form, apiKeyInput: event.target.value, clearApiKey: false })}
                    placeholder={
                      meta.apiKeySet ? t("opsCaptionAi.apiKeyKeepPlaceholder") : t("opsCaptionAi.apiKeyPlaceholder")
                    }
                    autoComplete="new-password"
                    spellCheck={false}
                  />
                </div>
                <label className="ops-form-field-inline ops-ai-span-2">
                  <input
                    type="checkbox"
                    checked={form.clearApiKey}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        clearApiKey: event.target.checked,
                        apiKeyInput: event.target.checked ? "" : form.apiKeyInput
                      })
                    }
                  />
                  <span>{t("opsCaptionAi.clearApiKey")}</span>
                </label>
              </>
            ) : null}
          </div>
        </section>

        <section className="ops-ai-section">
          <header className="ops-ai-section__head">
            <h3>{t("opsCaptionAi.sectionModelFallback")}</h3>
          </header>
          {showModel ? (
            <div className="ops-form-field">
              <label htmlFor="caption-ai-model">{t("opsCaptionAi.model")}</label>
              {manualModel || modelOptions.length === 0 ? (
                <input
                  id="caption-ai-model"
                  value={form.model}
                  onChange={(event) => setForm({ ...form, model: event.target.value })}
                  placeholder="gemini-2.5-flash / gpt-4o-mini / qwen2.5:14b"
                  autoComplete="off"
                  spellCheck={false}
                />
              ) : (
                <select
                  id="caption-ai-model"
                  value={form.model}
                  onChange={(event) => setForm({ ...form, model: event.target.value })}
                >
                  <option value="">{t("opsCaptionAi.modelSelectPlaceholder")}</option>
                  {modelOptions.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              )}
              <div className="ops-form-actions">
                <button type="button" onClick={() => void refreshModels()} disabled={loadingModels || !readyForModels}>
                  {loadingModels ? t("opsCaptionAi.loadingModels") : t("opsCaptionAi.loadModels")}
                </button>
                <button type="button" onClick={() => setManualModel((value) => !value)}>
                  {manualModel ? t("opsCaptionAi.useModelList") : t("opsCaptionAi.typeModelManually")}
                </button>
              </div>
              {modelListError ? (
                <div className="ops-field-alert is-error" role="alert" title={modelListError.raw}>
                  <strong>
                    {modelListError.title}
                    {modelListError.httpStatus ? ` · HTTP ${modelListError.httpStatus}` : ""}
                  </strong>
                  <span>{modelListError.message}</span>
                  <span className="ops-field-alert-hint">{t("opsCaptionAi.modelsErrorHint")}</span>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="ops-muted">{t("opsCaptionAi.modelGateHint")}</p>
          )}
          <div className="ops-ai-grid">
            <div className="ops-form-field">
              <label htmlFor="caption-ai-fallback">{t("opsCaptionAi.fallbackProvider")}</label>
              <select
                id="caption-ai-fallback"
                value={form.fallbackProvider}
                onChange={(event) => setForm({ ...form, fallbackProvider: event.target.value })}
              >
                <option value="none">none</option>
                <option value="ollama">ollama</option>
                <option value="gemini">gemini</option>
                <option value="openai_compatible">openai_compatible</option>
              </select>
            </div>
            <div className="ops-form-field">
              <label htmlFor="caption-ai-fallback-model">{t("opsCaptionAi.fallbackModel")}</label>
              <input
                id="caption-ai-fallback-model"
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
  );
}
