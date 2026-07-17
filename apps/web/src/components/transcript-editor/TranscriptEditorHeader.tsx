"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { AudioAnalysisSummaryResponse, TranscriptEditorState, TranslationPreset } from "../../types/transcript-editor";

type Props = {
  state: TranscriptEditorState;
  summary?: AudioAnalysisSummaryResponse | null;
  dirtyCount: number;
  blockingCount: number;
  saving: boolean;
  reanalyzing: boolean;
  translating: boolean;
  synthesizingTts: boolean;
  analyzeJobId: string | null;
  onSave: () => void;
  onDiscard: () => void;
  onTranslateLiteral: (preset: TranslationPreset) => void;
  onReanalyze: (preset: TranslationPreset) => void;
  onGenerateTts: () => void;
};

export function TranscriptEditorHeader({
  state,
  dirtyCount,
  blockingCount,
  saving,
  reanalyzing,
  translating,
  synthesizingTts,
  analyzeJobId,
  onSave,
  onDiscard,
  onTranslateLiteral,
  onReanalyze,
  onGenerateTts
}: Props) {
  const t = useT();
  const busy = saving || reanalyzing || translating || synthesizingTts;
  const jobStatusLabel = reanalyzing
    ? t("transcriptEditorHeader.reanalyzing")
    : translating
      ? t("transcriptEditorHeader.translating")
      : synthesizingTts
        ? t("transcriptEditorHeader.generatingTts")
        : null;

  function runTranslate(preset: TranslationPreset, confirmKey: "translateLiteralConfirm" | "translateNaturalConfirm") {
    if (window.confirm(t(`transcriptEditorHeader.${confirmKey}`))) {
      onTranslateLiteral(preset);
    }
  }

  return (
    <header className="transcript-header transcript-header--command">
      <div className="transcript-header__identity">
        <Link className="transcript-header__back" href="/selection/review-board">
          {t("transcriptEditorHeader.backToReviewBoard")}
        </Link>
        {jobStatusLabel ? (
          <p className="transcript-reanalyze-status">
            {jobStatusLabel}
            {analyzeJobId ? (
              <>
                {" · "}
                <a href={`/ops/jobs?job_id=${analyzeJobId}`}>{t("transcriptEditorHeader.openJob")}</a>
              </>
            ) : null}
          </p>
        ) : (
          <p className="transcript-header__bench-kicker">{t("transcriptEditorBench.workspaceKicker")}</p>
        )}
      </div>

      <div className="editor-command" role="toolbar" aria-label={t("transcriptEditorHeader.toolbarLabel")}>
        <div className="editor-command__core">
          <button
            type="button"
            className="editor-command__save"
            onClick={onSave}
            disabled={dirtyCount === 0 || busy || blockingCount > 0}
          >
            {saving ? t("transcriptEditorHeader.saving") : t("transcriptEditorHeader.saveDraft")}
            {dirtyCount > 0 ? <span className="editor-command__dot" aria-hidden /> : null}
          </button>

          <details className={`editor-command__translate${busy ? " is-busy" : ""}`}>
            <summary aria-disabled={busy}>
              {translating ? t("transcriptEditorHeader.translating") : t("transcriptEditorHeader.translateMenu")}
            </summary>
            <div className="editor-command__menu" role="menu">
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => runTranslate("literal_safe", "translateLiteralConfirm")}
              >
                <strong>{t("transcriptEditorHeader.translateLiteralShort")}</strong>
                <span>{t("transcriptEditorHeader.translateLiteral")}</span>
              </button>
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => runTranslate("natural_viral", "translateNaturalConfirm")}
              >
                <strong>{t("transcriptEditorHeader.translateNaturalShort")}</strong>
                <span>{t("transcriptEditorHeader.translateNatural")}</span>
              </button>
            </div>
          </details>

          <button
            type="button"
            className="editor-command__tts"
            disabled={busy}
            onClick={() => {
              if (window.confirm(t("transcriptEditorHeader.generateTtsConfirm"))) {
                onGenerateTts();
              }
            }}
          >
            {synthesizingTts ? t("transcriptEditorHeader.generatingTtsShort") : t("transcriptEditorHeader.generateTts")}
          </button>
        </div>

        <nav className="editor-command__rail" aria-label={t("transcriptEditorHeader.secondaryNav")}>
          <Link href={`/production/final-review/${state.sourceVideoId}`}>{t("transcriptEditorHeader.finalReviewShort")}</Link>
          <button
            type="button"
            disabled={busy}
            title={t("transcriptEditorHeader.reanalyzeAudio")}
            onClick={() => {
              if (window.confirm(t("transcriptEditorHeader.reanalyzeConfirm"))) {
                onReanalyze("literal_safe");
              }
            }}
          >
            {reanalyzing ? t("transcriptEditorHeader.reanalyzingShort") : t("transcriptEditorHeader.reanalyzeShort")}
          </button>
          <a href="/ops/translation-ai" title={t("transcriptEditorHeader.editTranslationSettings")}>
            {t("transcriptEditorHeader.settingsShort")}
          </a>
          <a href="/ops/tts-ai" title={t("transcriptEditorHeader.editTtsSettings")}>
            {t("transcriptEditorHeader.ttsSettingsShort")}
          </a>
        </nav>

        <button type="button" className="editor-command__discard" onClick={onDiscard} disabled={dirtyCount === 0 || busy}>
          {t("transcriptEditorHeader.discard")}
        </button>
      </div>
    </header>
  );
}
