"use client";

import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { FinalReviewPage } from "../final-review/FinalReviewPage";

export function OperatorFinalReviewPage({ sourceVideoId }: { sourceVideoId: string }) {
  const t = useT();
  return (
    <OperatorStudioShell
      actions={
        <>
          <a href={`/production/transcript-editor/${sourceVideoId}`}>{t("nav.transcriptEditor")}</a>
          <a href={`/source-videos/${sourceVideoId}/publish`}>{t("nav.publishDraft")}</a>
          <a href="/publishing/drafts">{t("nav.publishDrafts")}</a>
        </>
      }
      description={t("operatorRoutes.finalReviewDesc")}
      title={t("operatorRoutes.finalReviewTitle")}
    >
      <FinalReviewPage sourceVideoId={sourceVideoId} />
    </OperatorStudioShell>
  );
}
