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
  onSave: () => void;
  onDiscard: () => void;
  onTranslateLiteral: (preset: TranslationPreset) => void;
  onReanalyze: (preset: TranslationPreset) => void;
  onGenerateTts: () => void;
};

type CommandIconKind = "save" | "translate" | "tts" | "final" | "reasr" | "discard";

function CommandIcon({ kind }: { kind: CommandIconKind }) {
  if (kind === "save") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 4.5h9.2L15.5 6.3V15.5H4.5V4.5z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinejoin="round"
        />
        <path
          d="M7 4.5v3.8h5.2V4.5M7 15.5v-4.2h6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "translate") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 5.5h7.5M8.2 5.5 6 14.5M10.2 14.5 8.2 5.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M12.2 9.2h3.6M14 9.2c0 2.4-1.4 4.6-3.2 5.8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "tts") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 8.2v3.6M7.2 6.2v7.6M9.9 4.8v10.4M12.6 6.8v6.4M15.3 8.2v3.6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "final") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M5 10.2 8.2 13.4 15 6.6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "reasr") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M15.5 10a5.5 5.5 0 1 1-1.6-3.9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
        <path
          d="M15.5 4.8v3.6h-3.6"
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
    <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M5 6.2h10M7.2 6.2V5.2A1.2 1.2 0 0 1 8.4 4h3.2A1.2 1.2 0 0 1 12.8 5.2v1M6.4 6.2l.6 8.4A1.2 1.2 0 0 0 8.2 16h3.6a1.2 1.2 0 0 0 1.2-1.4l.6-8.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function TranscriptEditorHeader({
  state,
  dirtyCount,
  blockingCount,
  saving,
  reanalyzing,
  translating,
  synthesizingTts,
  onSave,
  onDiscard,
  onTranslateLiteral,
  onReanalyze,
  onGenerateTts
}: Props) {
  const t = useT();
  const busy = saving || reanalyzing || translating || synthesizingTts;

  function runTranslate() {
    if (window.confirm(t("transcriptEditorHeader.translateLiteralConfirm"))) {
      onTranslateLiteral("literal_safe");
    }
  }

  return (
    <header className="transcript-header transcript-header--command">
      <div className="transcript-header__identity">
        <Link className="transcript-header__back" href="/selection/review-board">
          {t("transcriptEditorHeader.backToReviewBoard")}
        </Link>
        <p className="transcript-header__bench-kicker">{t("transcriptEditorBench.workspaceKicker")}</p>
      </div>

      <div className="editor-command" role="toolbar" aria-label={t("transcriptEditorHeader.toolbarLabel")}>
        <div className="editor-command__core">
          <button
            type="button"
            className={`editor-command__save${saving ? " is-busy" : ""}`}
            onClick={onSave}
            disabled={dirtyCount === 0 || busy || blockingCount > 0}
          >
            <CommandIcon kind="save" />
            <span>{saving ? t("transcriptEditorHeader.saving") : t("transcriptEditorHeader.saveDraft")}</span>
            {dirtyCount > 0 ? <span className="editor-command__dot" aria-hidden /> : null}
          </button>

          <button
            type="button"
            className={`editor-command__translate${translating ? " is-busy" : ""}`}
            disabled={busy}
            onClick={runTranslate}
          >
            <CommandIcon kind="translate" />
            <span>
              {translating ? t("transcriptEditorHeader.translating") : t("transcriptEditorHeader.translateMenu")}
            </span>
          </button>

          <button
            type="button"
            className={`editor-command__tts${synthesizingTts ? " is-busy" : ""}`}
            disabled={busy}
            onClick={() => {
              if (window.confirm(t("transcriptEditorHeader.generateTtsConfirm"))) {
                onGenerateTts();
              }
            }}
          >
            <CommandIcon kind="tts" />
            <span>
              {synthesizingTts
                ? t("transcriptEditorHeader.generatingTtsShort")
                : t("transcriptEditorHeader.generateTts")}
            </span>
          </button>
        </div>

        <nav className="editor-command__rail" aria-label={t("transcriptEditorHeader.secondaryNav")}>
          <Link href={`/production/final-review/${state.sourceVideoId}`}>
            <CommandIcon kind="final" />
            <span>{t("transcriptEditorHeader.finalReviewShort")}</span>
          </Link>
          <button
            type="button"
            className={reanalyzing ? "is-busy" : undefined}
            disabled={busy}
            title={t("transcriptEditorHeader.reanalyzeAudio")}
            onClick={() => {
              if (window.confirm(t("transcriptEditorHeader.reanalyzeConfirm"))) {
                onReanalyze("literal_safe");
              }
            }}
          >
            <CommandIcon kind="reasr" />
            <span>
              {reanalyzing
                ? t("transcriptEditorHeader.reanalyzingShort")
                : t("transcriptEditorHeader.reanalyzeShort")}
            </span>
          </button>
        </nav>

        <button type="button" className="editor-command__discard" onClick={onDiscard} disabled={dirtyCount === 0 || busy}>
          <CommandIcon kind="discard" />
          <span>{t("transcriptEditorHeader.discard")}</span>
        </button>
      </div>
    </header>
  );
}
