"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { AudioAnalysisSummaryResponse } from "../../types/transcript-editor";

export function TranscriptLoadingState() {
  const t = useT();
  return (
    <section className="transcript-loading" role="status" aria-busy="true" aria-live="polite">
      <div className="transcript-loading__status">
        <span className="transcript-loading__spinner" aria-hidden="true" />
        <span>{t("transcriptEditorStates.loading")}</span>
      </div>

      <div className="transcript-loading__header" aria-hidden="true">
        <span className="transcript-loading__pill is-back" />
        <div className="transcript-loading__pipeline">
          <span className="transcript-loading__step" />
          <span className="transcript-loading__step" />
          <span className="transcript-loading__step" />
          <span className="transcript-loading__step is-active" />
        </div>
        <span className="transcript-loading__toolbar" />
      </div>

      <div className="transcript-loading__bench" aria-hidden="true">
        <aside className="transcript-loading__side">
          <span className="transcript-loading__media" />
          <div className="transcript-loading__beats">
            <span className="transcript-loading__beat" />
            <span className="transcript-loading__beat" />
            <span className="transcript-loading__beat" />
            <span className="transcript-loading__beat" />
            <span className="transcript-loading__beat" />
            <span className="transcript-loading__beat" />
          </div>
        </aside>
        <div className="transcript-loading__focus">
          <span className="transcript-loading__line is-narrow" />
          <span className="transcript-loading__line is-wide" />
          <span className="transcript-loading__field" />
          <span className="transcript-loading__line is-mid" />
          <span className="transcript-loading__field is-tall" />
          <span className="transcript-loading__line is-wide" />
          <span className="transcript-loading__field is-tall" />
        </div>
      </div>
    </section>
  );
}

export function TranscriptEmptyState() {
  const t = useT();
  return (
    <section className="state-panel">
      <h2>{t("transcriptEditorStates.empty")}</h2>
      <p>{t("transcriptEditorStates.emptyBody")}</p>
    </section>
  );
}

/** Analyze already ran; no spoken DialogueBeats (caption is not dialogue). */
export function TranscriptNoDialogueState() {
  const t = useT();
  return (
    <section className="state-panel">
      <h2>{t("transcriptEditorStates.noDialogue")}</h2>
      <p>{t("transcriptEditorStates.noDialogueBody")}</p>
      <Link className="primary-link" href="/selection/reup-queue">
        {t("transcriptEditorStates.backToReupQueue")}
      </Link>
    </section>
  );
}

export function TranscriptErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const t = useT();
  return (
    <section className="state-panel">
      <h2>{t("transcriptEditorStates.error")}</h2>
      <p>{message}</p>
      <button onClick={onRetry}>{t("transcriptEditorStates.retry")}</button>
    </section>
  );
}

export function isNoDialogueAnalysisSummary(summary: AudioAnalysisSummaryResponse | null): boolean {
  if (!summary) return false;
  if (summary.dialogue_phase === "no_dialogue") return true;
  if (summary.has_speech === false && summary.transcript_count === 0) return true;
  if (summary.transcript_count === 0 && Boolean(summary.analysis_version)) return true;
  return false;
}
