"use client";

import { useEffect, useState } from "react";
import { fetchCaptionPrompt, saveCaptionPrompt } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { OpsPanel, OpsState } from "./OpsShared";
import { OpsCaptionSettingsTabs } from "./OpsCaptionSettingsTabs";

export function OpsCaptionPromptPage() {
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
      const data = await fetchCaptionPrompt();
      setPrompt(data.prompt);
      setSource(data.source);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsCaptionPrompt.loadError"));
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
      const data = await saveCaptionPrompt(prompt);
      setPrompt(data.prompt);
      setSource(data.source);
      setSavedMessage(t("opsCaptionPrompt.saved"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsCaptionPrompt.saveError"));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <OpsState title={t("ops.loadingTitle")} detail={t("opsCaptionPrompt.loadingDetail")} />;
  }

  return (
    <main className="ops-page ops-page--settings">
      <OpsCaptionSettingsTabs />

      {error ? <div className="inline-error">{error}</div> : null}

      <OpsPanel
        title={t("opsCaptionPrompt.panelTitle")}
        actions={
          <div className="ops-header-actions">
            {savedMessage ? <span className="ops-connection-status is-ok">{t("opsCaptionPrompt.saved")}</span> : null}
            <button type="button" onClick={() => void load()} disabled={saving}>
              {t("common.refresh")}
            </button>
            <button type="button" className="primary" onClick={() => void onSave()} disabled={saving}>
              {saving ? t("opsCaptionPrompt.saving") : t("opsCaptionPrompt.save")}
            </button>
          </div>
        }
      >
        <p className="ops-muted">
          {t("opsCaptionPrompt.hint")}{" "}
          <code>{source === "workspace_db" ? t("opsCaptionPrompt.sourceDb") : t("opsCaptionPrompt.sourceEmpty")}</code>
        </p>

        {savedMessage ? (
          <div className="ops-field-alert is-success" role="status">
            <strong>{t("opsCaptionPrompt.saved")}</strong>
            <span>{t("opsCaptionPrompt.savedHint")}</span>
          </div>
        ) : null}

        <textarea
          className="ops-prompt-textarea"
          rows={18}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder={t("opsCaptionPrompt.placeholder")}
          spellCheck={false}
        />
        <p className="ops-muted">{t("opsCaptionPrompt.clearHint")}</p>
      </OpsPanel>
    </main>
  );
}
