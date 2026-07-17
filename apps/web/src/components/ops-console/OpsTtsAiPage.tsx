"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchTtsAi, installTtsAiPackage, previewTtsAiSpeech, saveTtsAi, testTtsAi, type TtsAiCatalog, type TtsAiResponse, type TtsAiRuntime } from "../../lib/api";
import { useT } from "../../lib/i18n";
import {
  formatConnectionTestSummary,
  formatProviderError,
  type ConnectionTestResult
} from "../../lib/opsTranslationAiFormat";
import {
  catalogFromRuntime,
  resolveTtsReadyState,
  ttsReadyChipClass,
  ttsReadyLabelKey
} from "../../lib/opsTtsReadyState";
import {
  defaultProviderForKind,
  getLocalInstallRecipe,
  isCustomLocalProvider,
  isPresetLocalProvider,
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
import { OpsPanel, OpsState } from "./OpsShared";

export {
  showsTtsApiKey,
  showsTtsBaseUrl,
  showsTtsCliBinary,
  showsTtsLocalBackend,
  resolveTtsProviderKind,
  getLocalInstallRecipe
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
  clearApiKey: boolean;
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
    clearApiKey: false,
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

export function OpsTtsAiPage() {
  const t = useT();
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
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
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

  function applyCatalog(nextCatalog: TtsAiCatalog | null, base: FormState) {
    if (!nextCatalog?.voices?.length) {
      setCatalog(nextCatalog);
      return base;
    }
    setCatalog(nextCatalog);
    const patch = { ...base };
    if (!patch.voiceId.trim() || !nextCatalog.voices.some((v) => v.id === patch.voiceId)) {
      // Keep operator-saved voice when catalog refresh still lists it; only fill when empty/unknown.
      patch.voiceId = nextCatalog.default_voice_id || nextCatalog.voices[0]?.id || patch.voiceId;
    }
    if (nextCatalog.styles.length > 0 && !nextCatalog.styles.includes(patch.style)) {
      patch.style = nextCatalog.styles[0] || patch.style;
    }
    if (nextCatalog.models.length > 0 && !patch.modelId.trim()) {
      patch.modelId = nextCatalog.models[0] || patch.modelId;
    }
    return patch;
  }

  async function load() {
    setLoading(true);
    setError(null);
    setSavedMessage(null);
    setTestResult(null);
    setInstallResult(null);
    try {
      const data = await fetchTtsAi();
      let next = toForm(data);
      setRuntime(data.runtime || null);
      setLiveImportOk(data.live_import_ok ?? null);
      const hydrated = catalogFromRuntime(data.runtime || null);
      if (hydrated) {
        next = applyCatalog(hydrated, next);
      } else {
        setCatalog(null);
      }
      if (data.runtime?.last_probe) {
        setTestResult({
          ok: Boolean(data.runtime.last_probe.ok),
          provider: data.runtime.last_probe.provider || data.provider,
          detail: data.runtime.last_probe.detail || ""
        });
      }
      if (data.runtime?.last_install) {
        setInstallResult({
          ok: Boolean(data.runtime.last_install.ok),
          detail: data.runtime.last_install.detail || "",
          command: data.runtime.last_install.command || "",
          log_tail: "",
          already_satisfied: Boolean(data.runtime.last_install.already_satisfied)
        });
      }
      setForm(next);
      setKind(resolveTtsProviderKind(next.provider));
      setMeta({
        apiKeySet: data.api_key_set,
        apiKeyMasked: data.api_key_masked,
        source: data.source
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.loadError"));
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

  const providersInKind = useMemo(() => TTS_PROVIDERS_BY_KIND[kind], [kind]);
  const activeProvider = form ? effectiveProvider(form) : "auto";
  const recipe = form ? getLocalInstallRecipe(activeProvider) : null;
  const showCustomSlug = Boolean(form && form.providerChoice === "custom");

  function buildPayload() {
    if (!form) return null;
    const provider = effectiveProvider(form);
    if (form.providerChoice === "custom" && !/^[a-z][a-z0-9_\-]{0,62}$/.test(provider)) {
      setError(t("opsTtsAi.customProviderInvalid"));
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
    const payload: Parameters<typeof saveTtsAi>[0] = {
      enabled: form.enabled,
      provider,
      voice_id: form.voiceId.trim(),
      speaking_rate: Number.isFinite(rate) && rate >= 0.5 && rate <= 2 ? rate : 1,
      language_code: form.languageCode.trim() || "vi",
      model_id: form.modelId.trim(),
      base_url: form.baseUrl.trim(),
      timeout_seconds: Number.isFinite(timeout) && timeout > 0 ? timeout : 120,
      fallback_provider: form.fallbackProvider,
      fallback_voice_id: form.fallbackVoiceId.trim(),
      local_backend: form.localBackend,
      device: form.device,
      cli_binary: form.cliBinary.trim(),
      options_json,
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
      const data = await saveTtsAi(payload);
      const next = toForm(data);
      setForm(next);
      setKind(resolveTtsProviderKind(next.provider));
      setMeta({
        apiKeySet: data.api_key_set,
        apiKeyMasked: data.api_key_masked,
        source: data.source
      });
      setSavedMessage(t("opsTtsAi.saved"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.saveError"));
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    const payload = buildPayload();
    if (!payload) return;
    setTesting(true);
    setError(null);
    try {
      const result = await testTtsAi(payload);
      setTestResult({ ok: result.ok, provider: result.provider, detail: result.detail });
      if (result.runtime) setRuntime(result.runtime);
      const nextCatalog = result.catalog && result.ok ? result.catalog : null;
      if (form) {
        setForm(applyCatalog(nextCatalog, form));
      } else {
        setCatalog(nextCatalog);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.testError"));
    } finally {
      setTesting(false);
    }
  }

  function onKindChange(nextKind: TtsProviderKind) {
    if (!form) return;
    const list = TTS_PROVIDERS_BY_KIND[nextKind];
    const currentChoice = form.providerChoice === "custom" ? "custom" : form.provider;
    const nextProvider = list.includes(currentChoice as (typeof list)[number])
      ? currentChoice
      : defaultProviderForKind(nextKind);
    setKind(nextKind);
    applyProvider(nextProvider, { ...form });
  }

  function applyProvider(next: string, base: FormState) {
    const isCustom = next === "custom" || isCustomLocalProvider(next);
    const patch: FormState = {
      ...base,
      provider: isCustom ? base.customProviderSlug || next : next,
      providerChoice: isCustom ? "custom" : next,
      customProviderSlug: isCustom ? (next === "custom" ? base.customProviderSlug : next) : ""
    };
    const nextRecipe = getLocalInstallRecipe(isCustom ? "" : next);
    if (nextRecipe) {
      patch.voiceId = nextRecipe.defaultVoice;
      if (nextRecipe.defaultModel) patch.modelId = nextRecipe.defaultModel;
      patch.installCommand = nextRecipe.installCommand;
      patch.extraRequirement = nextRecipe.extraRequirement;
      patch.packageName = nextRecipe.packageName;
      patch.repoUrl = "";
    } else if (isCustom) {
      patch.installCommand = base.installCommand;
      patch.extraRequirement = base.extraRequirement;
    }
    if (next === "openai_compatible" && !patch.baseUrl.trim()) {
      patch.baseUrl = "https://api.openai.com/v1";
    }
    if (next === "vieneu" && patch.localBackend === "remote" && !patch.baseUrl.trim()) {
      patch.baseUrl = "http://127.0.0.1:23333/v1";
    }
    patch.provider = effectiveProvider(patch);
    setForm(patch);
    setKind(isCustom || patch.providerChoice === "custom" ? "local" : resolveTtsProviderKind(patch.provider));
    setTestResult(null);
    setCatalog(null);
    setInstallResult(null);
  }

  function onProviderChange(next: string) {
    if (!form) return;
    applyProvider(next, form);
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

  async function onInstall() {
    if (!form) return;
    setInstalling(true);
    setError(null);
    setInstallResult(null);
    try {
      const result = await installTtsAiPackage({
        install_command: form.installCommand.trim() || null,
        package: form.packageName.trim() || null,
        repo_url: form.repoUrl.trim() || null,
        timeout_seconds: 300,
        provider: effectiveProvider(form)
      });
      setInstallResult({
        ok: result.ok,
        detail: result.detail,
        command: result.command,
        log_tail: result.log_tail,
        already_satisfied: Boolean(result.already_satisfied)
      });
      if (result.runtime) setRuntime(result.runtime);
      if (result.ok) {
        if (typeof result.probe_ok === "boolean") {
          setTestResult({
            ok: result.probe_ok,
            provider: result.provider || effectiveProvider(form),
            detail: result.probe_detail || ""
          });
          setLiveImportOk(result.probe_ok);
        }
        const nextCatalog = result.catalog && result.probe_ok ? result.catalog : null;
        let nextForm = form;
        if (result.command) {
          nextForm = { ...nextForm, installCommand: result.command };
        }
        setForm(applyCatalog(nextCatalog, nextForm));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.installError"));
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
    setPreviewing(true);
    setError(null);
    try {
      const result = await previewTtsAiSpeech({
        ...payload,
        text: sample,
        max_chars: 280
      });
      const binary = Uint8Array.from(atob(result.audio_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([binary], { type: result.mime_type || "audio/wav" });
      const url = URL.createObjectURL(blob);
      setPreviewAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setPreviewMeta({
        provider: result.provider,
        duration: result.duration_seconds,
        detail: result.detail
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTtsAi.previewError"));
    } finally {
      setPreviewing(false);
    }
  }

  if (loading || !form) {
    return <OpsState title={t("ops.loadingTitle")} detail={t("opsTtsAi.loadingDetail")} />;
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

  const isLocal = kind === "local";
  const isCloud = kind === "cloud";
  const isHttp = kind === "http";
  const isSystem = kind === "system";
  const readyState = resolveTtsReadyState({
    test: testResult ? { ok: testResult.ok, detail: testResult.detail } : null,
    install: installResult ? { ok: installResult.ok, detail: installResult.detail } : null,
    runtime,
    liveImportOk
  });
  const hadInstall = Boolean(runtime?.last_install?.ok || installResult?.ok);
  const catalogVoices = catalog?.voices?.length ? catalog.voices : null;
  const catalogStyles = catalog?.styles?.length ? catalog.styles : null;
  const catalogModels = catalog?.models?.length ? catalog.models : null;

  return (
    <main className="ops-page ops-page--settings ops-tts-page">
      {error ? <div className="inline-error">{error}</div> : null}

      <OpsPanel
        title={t("opsTtsAi.panelTitle")}
        actions={
          <div className="ops-header-actions">
            {savedMessage ? <span className="ops-connection-status is-ok">{t("opsTtsAi.saved")}</span> : null}
            {testResult?.ok ? (
              <span className="ops-connection-status is-ok">
                {formatConnectionTestSummary(testResult, {
                  ok: t("opsTtsAi.testOk"),
                  fail: t("opsTtsAi.testFail")
                })}
              </span>
            ) : null}
            <button type="button" onClick={() => void load()} disabled={saving || testing || installing || previewing}>
              {t("common.refresh")}
            </button>
            <button type="button" onClick={() => void onTest()} disabled={saving || testing || installing || previewing}>
              {testing ? t("opsTtsAi.testing") : t("opsTtsAi.test")}
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => void onSave()}
              disabled={saving || testing || installing || previewing}
            >
              {saving ? t("opsTtsAi.saving") : t("opsTtsAi.save")}
            </button>
          </div>
        }
      >
        <div className="ops-tts-status" aria-label={t("opsTtsAi.statusLabel")}>
          <span className={`ops-tts-chip ${meta.source === "workspace_db" ? "is-active" : "is-muted"}`}>
            {meta.source === "workspace_db" ? t("opsTtsAi.sourceDbShort") : t("opsTtsAi.sourceEnvShort")}
          </span>
          <span className={`ops-tts-chip ${meta.apiKeySet ? "is-ok" : "is-muted"}`}>
            {meta.apiKeySet ? `${t("opsTtsAi.keySet")}: ${meta.apiKeyMasked}` : t("opsTtsAi.keyUnset")}
          </span>
          <span className="ops-tts-chip is-muted">{activeProvider}</span>
          <span className="ops-tts-chip is-muted">{t(kindLabelKey(kind))}</span>
          <span
            className={`ops-tts-chip ${ttsReadyChipClass(readyState)}`}
            title={t("opsTtsAi.readyHint")}
            data-ready-state={readyState}
          >
            {t(ttsReadyLabelKey(readyState))}
          </span>
          {catalog?.source ? (
            <span className="ops-tts-chip is-ok" title={catalog.warning || undefined} data-catalog-source={catalog.source}>
              {t("opsTtsAi.catalogSource")}: {catalog.source}
              {catalogVoices ? ` · ${catalogVoices.length}` : ""}
            </span>
          ) : null}
        </div>

        <p className="ops-muted ops-tts-lede">{t("opsTtsAi.lede")}</p>
        <ol className="ops-tts-steps" aria-label={t("opsTtsAi.stepsLabel")}>
          <li>{t("opsTtsAi.step1")}</li>
          <li>{t("opsTtsAi.step2")}</li>
          <li>{t("opsTtsAi.step3")}</li>
          <li>{t("opsTtsAi.step4")}</li>
        </ol>
        <p className="ops-muted ops-tts-lede">{t("opsTtsAi.readyHint")}</p>

        {savedMessage ? (
          <div className="ops-field-alert is-success" role="status">
            <strong>{t("opsTtsAi.saved")}</strong>
            <span>{t("opsTtsAi.savedHint")}</span>
          </div>
        ) : null}

        {testFailure ? (
          <div className="ops-field-alert is-error" role="alert" title={testResult?.detail || undefined}>
            <strong>
              {testFailure.title}
              {testResult?.provider ? ` · ${testResult.provider}` : ""}
            </strong>
            <span>{testFailure.message}</span>
          </div>
        ) : null}

        <section className="ops-tts-section">
          <header className="ops-tts-section__head">
            <h3>{t("opsTtsAi.sectionAuthority")}</h3>
            <p>{t("opsTtsAi.sectionAuthorityHint")}</p>
          </header>
          <label className="ops-tts-toggle">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            />
            <span>
              <strong>{t("opsTtsAi.enabled")}</strong>
              <small>{t("opsTtsAi.enabledHint")}</small>
            </span>
          </label>
        </section>

        <section className="ops-tts-section">
          <header className="ops-tts-section__head">
            <h3>{t("opsTtsAi.sectionKind")}</h3>
            <p>{t(kindHintKey(kind))}</p>
          </header>

          <div className="ops-tts-kind-tabs" role="tablist" aria-label={t("opsTtsAi.sectionKind")}>
            {TTS_KIND_ORDER.map((item) => (
              <button
                key={item}
                type="button"
                role="tab"
                aria-selected={kind === item}
                className={`ops-tts-kind-tab${kind === item ? " is-active" : ""}`}
                onClick={() => onKindChange(item)}
              >
                {t(kindLabelKey(item))}
              </button>
            ))}
          </div>

          <div className="ops-tts-grid" style={{ marginTop: "0.85rem" }}>
            <div className="ops-form-field">
              <label htmlFor="tts-ai-provider">{t("opsTtsAi.provider")}</label>
              <select
                id="tts-ai-provider"
                value={
                  kind === "local" && (form.providerChoice === "custom" || isCustomLocalProvider(form.provider))
                    ? "custom"
                    : form.providerChoice
                }
                onChange={(e) => onProviderChange(e.target.value)}
              >
                {providersInKind.map((p) => (
                  <option key={p} value={p}>
                    {p === "custom" ? t("opsTtsAi.providerCustom") : p}
                  </option>
                ))}
              </select>
            </div>
            <div className="ops-form-field">
              <label htmlFor="tts-ai-timeout">{t("opsTtsAi.timeoutSeconds")}</label>
              <input
                id="tts-ai-timeout"
                value={form.timeoutSeconds}
                onChange={(e) => setForm({ ...form, timeoutSeconds: e.target.value })}
              />
            </div>
            {showCustomSlug ? (
              <div className="ops-form-field ops-tts-span-2">
                <label htmlFor="tts-ai-custom-slug">{t("opsTtsAi.customProviderSlug")}</label>
                <input
                  id="tts-ai-custom-slug"
                  value={form.customProviderSlug}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      customProviderSlug: e.target.value,
                      provider: e.target.value.trim().toLowerCase() || "custom",
                      providerChoice: "custom"
                    })
                  }
                  placeholder="my_tts_provider"
                  spellCheck={false}
                />
                <p className="ops-tts-field-hint">{t("opsTtsAi.customProviderHint")}</p>
              </div>
            ) : null}
          </div>
        </section>

        {isLocal ? (
          <section className="ops-tts-section ops-tts-section--install">
            <header className="ops-tts-section__head">
              <h3>{t("opsTtsAi.sectionInstall")}</h3>
              <p>{recipe ? t(recipe.hintKey) : t("opsTtsAi.sectionInstallHint")}</p>
            </header>
            <div className="ops-tts-grid">
              <div className="ops-form-field">
                <label htmlFor="tts-ai-package">{t("opsTtsAi.packageName")}</label>
                <input
                  id="tts-ai-package"
                  value={form.packageName}
                  onChange={(e) => setForm({ ...form, packageName: e.target.value })}
                  placeholder="edge-tts"
                  spellCheck={false}
                />
              </div>
              <div className="ops-form-field">
                <label htmlFor="tts-ai-repo">{t("opsTtsAi.repoUrl")}</label>
                <input
                  id="tts-ai-repo"
                  value={form.repoUrl}
                  onChange={(e) => setForm({ ...form, repoUrl: e.target.value })}
                  placeholder="https://github.com/org/repo.git"
                  spellCheck={false}
                />
              </div>
              <div className="ops-form-field ops-tts-span-2">
                <label htmlFor="tts-ai-install">{t("opsTtsAi.installCommand")}</label>
                <div className="ops-tts-install-row">
                  <input
                    id="tts-ai-install"
                    value={form.installCommand}
                    onChange={(e) => setForm({ ...form, installCommand: e.target.value })}
                    placeholder="pip install …"
                    spellCheck={false}
                  />
                  <button type="button" onClick={() => void copyInstallCommand()} disabled={!form.installCommand.trim()}>
                    {copied ? t("opsTtsAi.copied") : t("opsTtsAi.copyInstall")}
                  </button>
                </div>
                <p className="ops-tts-field-hint">{t("opsTtsAi.installCommandHint")}</p>
              </div>
              <div className="ops-form-field ops-tts-span-2">
                <label htmlFor="tts-ai-extra">{t("opsTtsAi.extraRequirement")}</label>
                <input
                  id="tts-ai-extra"
                  value={form.extraRequirement}
                  onChange={(e) => setForm({ ...form, extraRequirement: e.target.value })}
                  placeholder={t("opsTtsAi.extraRequirementPlaceholder")}
                />
              </div>
              <div className="ops-tts-span-2 ops-tts-install-actions">
                <button
                  type="button"
                  className="primary"
                  onClick={() => void onInstall()}
                  disabled={
                    installing ||
                    saving ||
                    testing ||
                    (!form.installCommand.trim() && !form.packageName.trim() && !form.repoUrl.trim())
                  }
                >
                  {installing
                    ? t("opsTtsAi.installing")
                    : hadInstall
                      ? t("opsTtsAi.reinstall")
                      : t("opsTtsAi.install")}
                </button>
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
              {installResult ? (
                <div
                  className={`ops-field-alert ops-tts-span-2 ${installResult.ok ? "is-success" : "is-error"}`}
                  role="status"
                >
                  <strong>
                    {installResult.ok
                      ? installResult.already_satisfied
                        ? t("opsTtsAi.installAlready")
                        : t("opsTtsAi.installOk")
                      : t("opsTtsAi.installFail")}
                    {installResult.command ? ` · ${installResult.command}` : ""}
                  </strong>
                  <span>
                    {installResult.already_satisfied
                      ? t("opsTtsAi.installAlreadyHint")
                      : installResult.detail}
                  </span>
                  {installResult.log_tail ? (
                    <pre className="ops-tts-install-log">{installResult.log_tail}</pre>
                  ) : null}
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        {(isLocal || isCloud || isHttp) && (
          <section className="ops-tts-section">
            <header className="ops-tts-section__head">
              <h3>{t("opsTtsAi.sectionVoice")}</h3>
              <p>{t("opsTtsAi.sectionVoiceHint")}</p>
            </header>
            {catalog ? (
              <div className="ops-tts-status" aria-label={t("opsTtsAi.providerMetaLabel")}>
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
                    placeholder={recipe?.defaultVoice || "vi-VN-HoaiMyNeural"}
                    spellCheck={false}
                  />
                )}
                <p className="ops-tts-field-hint">
                  {catalogVoices ? t("opsTtsAi.voiceFromCatalog") : t("opsTtsAi.voicePresetHint")}
                </p>
              </div>
              <div className="ops-form-field">
                <label htmlFor="tts-ai-rate">{t("opsTtsAi.speakingRate")}</label>
                <input
                  id="tts-ai-rate"
                  value={form.speakingRate}
                  onChange={(e) => setForm({ ...form, speakingRate: e.target.value })}
                />
              </div>
              <div className="ops-form-field">
                <label htmlFor="tts-ai-lang">{t("opsTtsAi.languageCode")}</label>
                <input
                  id="tts-ai-lang"
                  value={form.languageCode}
                  onChange={(e) => setForm({ ...form, languageCode: e.target.value })}
                />
              </div>
              {(isCloud || isHttp || activeProvider === "vieneu") && (
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
                      spellCheck={false}
                    />
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {(isLocal || isCloud || isHttp) && (
          <section className="ops-tts-section ops-tts-section--preview">
            <header className="ops-tts-section__head ops-tts-preview-head">
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
                  rows={2}
                  value={previewText}
                  onChange={(e) => setPreviewText(e.target.value)}
                  maxLength={280}
                  spellCheck={false}
                  placeholder={t("opsTtsAi.previewTextPlaceholder")}
                />
              </div>

              <div className="ops-tts-preview-bar">
                <button
                  type="button"
                  className="primary"
                  onClick={() => void onPreview()}
                  disabled={previewing || saving || testing || installing || !previewText.trim()}
                >
                  {previewing ? t("opsTtsAi.previewing") : t("opsTtsAi.preview")}
                </button>
                {previewAudioUrl ? (
                  <audio controls src={previewAudioUrl} className="ops-tts-preview-audio" preload="metadata">
                    <track kind="captions" />
                  </audio>
                ) : (
                  <p className="ops-tts-preview-idle">{t("opsTtsAi.previewIdle")}</p>
                )}
              </div>
            </div>
          </section>
        )}

        {isLocal && (showsTtsLocalBackend(activeProvider) || showsTtsCliBinary(activeProvider)) ? (
          <section className="ops-tts-section">
            <header className="ops-tts-section__head">
              <h3>{t("opsTtsAi.sectionRuntime")}</h3>
              <p>{t("opsTtsAi.sectionRuntimeHint")}</p>
            </header>
            <div className="ops-tts-grid">
              {showsTtsLocalBackend(activeProvider) ? (
                <>
                  <div className="ops-form-field">
                    <label htmlFor="tts-ai-backend">{t("opsTtsAi.localBackend")}</label>
                    <select
                      id="tts-ai-backend"
                      value={form.localBackend}
                      onChange={(e) => setForm({ ...form, localBackend: e.target.value })}
                    >
                      {(catalog?.backends?.length ? catalog.backends : ["auto", "onnx", "pytorch", "remote"]).map(
                        (backend) => (
                          <option key={backend} value={backend}>
                            {backend}
                          </option>
                        )
                      )}
                    </select>
                  </div>
                  <div className="ops-form-field">
                    <label htmlFor="tts-ai-device">{t("opsTtsAi.device")}</label>
                    <select
                      id="tts-ai-device"
                      value={form.device}
                      onChange={(e) => setForm({ ...form, device: e.target.value })}
                    >
                      <option value="auto">auto</option>
                      <option value="cpu">cpu</option>
                      <option value="cuda">cuda</option>
                    </select>
                  </div>
                  <div className="ops-form-field">
                    <label htmlFor="tts-ai-style">{t("opsTtsAi.style")}</label>
                    <select
                      id="tts-ai-style"
                      value={form.style}
                      onChange={(e) => setForm({ ...form, style: e.target.value })}
                    >
                      {(catalogStyles || ["tu_nhien", "tin_tuc", "doc_truyen"]).map((style) => (
                        <option key={style} value={style}>
                          {style}
                        </option>
                      ))}
                    </select>
                    <p className="ops-tts-field-hint">{t("opsTtsAi.styleHint")}</p>
                  </div>
                </>
              ) : null}
              {showsTtsCliBinary(activeProvider) ? (
                <div className="ops-form-field ops-tts-span-2">
                  <label htmlFor="tts-ai-cli">{t("opsTtsAi.cliBinary")}</label>
                  <input
                    id="tts-ai-cli"
                    value={form.cliBinary}
                    onChange={(e) => setForm({ ...form, cliBinary: e.target.value })}
                    placeholder="edge-tts"
                    spellCheck={false}
                  />
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        {(isCloud ||
          isHttp ||
          (isLocal && showsTtsBaseUrl(activeProvider, form.localBackend))) && (
          <section className="ops-tts-section">
            <header className="ops-tts-section__head">
              <h3>{t(isLocal ? "opsTtsAi.sectionRemoteOptional" : "opsTtsAi.sectionCredentials")}</h3>
              <p>
                {t(
                  isLocal
                    ? "opsTtsAi.sectionRemoteOptionalHint"
                    : isHttp
                      ? "opsTtsAi.sectionHttpHint"
                      : "opsTtsAi.sectionCredentialsHint"
                )}
              </p>
            </header>
            <div className="ops-tts-grid">
              {showsTtsBaseUrl(activeProvider, form.localBackend) ? (
                <div className="ops-form-field ops-tts-span-2">
                  <label htmlFor="tts-ai-base-url">{t("opsTtsAi.baseUrl")}</label>
                  <input
                    id="tts-ai-base-url"
                    value={form.baseUrl}
                    onChange={(e) => setForm({ ...form, baseUrl: e.target.value })}
                    placeholder={
                      activeProvider === "vieneu"
                        ? "http://127.0.0.1:23333/v1"
                        : "https://api.openai.com/v1"
                    }
                    spellCheck={false}
                    autoComplete="off"
                  />
                </div>
              ) : null}
              {showsTtsApiKey(activeProvider) ? (
                <>
                  <div className="ops-form-field ops-tts-span-2">
                    <label htmlFor="tts-ai-api-key">{t("opsTtsAi.apiKey")}</label>
                    <input
                      id="tts-ai-api-key"
                      type="password"
                      autoComplete="off"
                      placeholder={meta.apiKeySet ? t("opsTtsAi.apiKeyKeep") : t("opsTtsAi.apiKeyPlaceholder")}
                      value={form.apiKeyInput}
                      onChange={(e) => setForm({ ...form, apiKeyInput: e.target.value, clearApiKey: false })}
                    />
                  </div>
                  <label className="ops-form-field-inline ops-tts-span-2">
                    <input
                      type="checkbox"
                      checked={form.clearApiKey}
                      onChange={(e) => setForm({ ...form, clearApiKey: e.target.checked, apiKeyInput: "" })}
                    />
                    <span>{t("opsTtsAi.clearApiKey")}</span>
                  </label>
                </>
              ) : null}
            </div>
          </section>
        )}

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

        <section className="ops-tts-section">
          <header className="ops-tts-section__head">
            <h3>{t("opsTtsAi.sectionFallback")}</h3>
            <p>{t("opsTtsAi.sectionFallbackHint")}</p>
          </header>
          <div className="ops-tts-grid">
            <div className="ops-form-field">
              <label htmlFor="tts-ai-fallback">{t("opsTtsAi.fallbackProvider")}</label>
              <select
                id="tts-ai-fallback"
                value={form.fallbackProvider}
                onChange={(e) => {
                  const next = e.target.value;
                  const patch = { ...form, fallbackProvider: next };
                  if (next === "edge" && !EDGE_FALLBACK_VOICE_OPTIONS.some((v) => v.id === form.fallbackVoiceId)) {
                    patch.fallbackVoiceId = EDGE_FALLBACK_VOICE_OPTIONS[0].id;
                  }
                  if (next === "vieneu" && catalogVoices?.length && !catalogVoices.some((v) => v.id === form.fallbackVoiceId)) {
                    patch.fallbackVoiceId = catalogVoices[0]?.id || patch.fallbackVoiceId;
                  }
                  setForm(patch);
                }}
              >
                {TTS_FALLBACK_PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="ops-form-field">
              <label htmlFor="tts-ai-fallback-voice">{t("opsTtsAi.fallbackVoiceId")}</label>
              {form.fallbackProvider === "edge" ? (
                <select
                  id="tts-ai-fallback-voice"
                  value={
                    EDGE_FALLBACK_VOICE_OPTIONS.some((v) => v.id === form.fallbackVoiceId)
                      ? form.fallbackVoiceId
                      : EDGE_FALLBACK_VOICE_OPTIONS[0].id
                  }
                  onChange={(e) => setForm({ ...form, fallbackVoiceId: e.target.value })}
                >
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
                      : catalogVoices[0]?.id || ""
                  }
                  onChange={(e) => setForm({ ...form, fallbackVoiceId: e.target.value })}
                >
                  {catalogVoices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.label || v.id}
                    </option>
                  ))}
                </select>
              ) : form.fallbackProvider === "none" ? (
                <input id="tts-ai-fallback-voice" value="" disabled placeholder="—" />
              ) : (
                <input
                  id="tts-ai-fallback-voice"
                  value={form.fallbackVoiceId}
                  onChange={(e) => setForm({ ...form, fallbackVoiceId: e.target.value })}
                  placeholder="vi-VN-HoaiMyNeural"
                  spellCheck={false}
                />
              )}
            </div>
          </div>
        </section>
      </OpsPanel>
    </main>
  );
}
