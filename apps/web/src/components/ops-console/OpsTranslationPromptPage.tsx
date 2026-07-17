"use client";

import { useEffect, useState } from "react";
import { fetchTranslationPrompt, saveTranslationPrompt } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { OpsPanel, OpsState } from "./OpsShared";
import { OpsTranslationSettingsTabs } from "./OpsTranslationSettingsTabs";

export function OpsTranslationPromptPage() {
  const t = useT();
  const [prompt, setPrompt] = useState("");
  const [source, setSource] = useState<string>("empty");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    setSavedMessage(null);
    try {
      const data = await fetchTranslationPrompt();
      setPrompt(data.prompt);
      setSource(data.source);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTranslationPrompt.loadError"));
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

  async function onSave() {
    setSaving(true);
    setError(null);
    setSavedMessage(null);
    try {
      const data = await saveTranslationPrompt(prompt);
      setPrompt(data.prompt);
      setSource(data.source);
      setSavedMessage(t("opsTranslationPrompt.saved"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsTranslationPrompt.saveError"));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <OpsState title={t("ops.loadingTitle")} detail={t("opsTranslationPrompt.loadingDetail")} />;
  }

  return (
    <main className="ops-page ops-page--settings">
      <OpsTranslationSettingsTabs />

      {error ? <div className="inline-error">{error}</div> : null}

      <OpsPanel
        title={t("opsTranslationPrompt.panelTitle")}
        actions={
          <div className="ops-header-actions">
            {savedMessage ? <span className="ops-connection-status is-ok">{t("opsTranslationPrompt.saved")}</span> : null}
            <button type="button" onClick={() => void load()} disabled={saving}>
              {t("common.refresh")}
            </button>
            <button type="button" className="primary" onClick={() => void onSave()} disabled={saving}>
              {saving ? t("opsTranslationPrompt.saving") : t("opsTranslationPrompt.save")}
            </button>
          </div>
        }
      >
        <p className="ops-muted">
          {t("opsTranslationPrompt.hint")}{" "}
          <code>{source === "workspace_db" ? t("opsTranslationPrompt.sourceDb") : t("opsTranslationPrompt.sourceEmpty")}</code>
        </p>

        {savedMessage ? (
          <div className="ops-field-alert is-success" role="status">
            <strong>{t("opsTranslationPrompt.saved")}</strong>
            <span>{t("opsTranslationPrompt.savedHint")}</span>
          </div>
        ) : null}

        <textarea
          className="ops-prompt-textarea"
          rows={18}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder={t("opsTranslationPrompt.placeholder")}
          spellCheck={false}
        />
        <p className="ops-muted">{t("opsTranslationPrompt.clearHint")}</p>
      </OpsPanel>
    </main>
  );
}
