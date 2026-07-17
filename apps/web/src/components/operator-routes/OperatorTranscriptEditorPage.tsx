"use client";

import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TranscriptEditorPage } from "../transcript-editor/TranscriptEditorPage";

export function OperatorTranscriptEditorPage({ sourceVideoId }: { sourceVideoId: string }) {
  const t = useT();
  return (
    <OperatorStudioShell
      actions={
        <>
          <a href="/selection/review-board">{t("nav.reviewBoard")}</a>
          <a href={`/production/final-review/${sourceVideoId}`}>{t("nav.finalReview")}</a>
          <a href="/">{t("common.home")}</a>
        </>
      }
      description={t("operatorRoutes.transcriptEditorDesc")}
      title={t("operatorRoutes.transcriptEditorTitle")}
    >
      <TranscriptEditorPage sourceVideoId={sourceVideoId} />
    </OperatorStudioShell>
  );
}
