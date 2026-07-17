"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { AudioAnalysisSummaryResponse } from "../../types/transcript-editor";

export function TranscriptLoadingState() {
  const t = useT();
  return <section className="state-panel skeleton">{t("transcriptEditorStates.loading")}</section>;
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
