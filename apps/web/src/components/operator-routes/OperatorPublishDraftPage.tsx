"use client";

import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PublishDraftPage } from "../publish-draft/PublishDraftPage";

export function OperatorPublishDraftPage({
  sourceVideoId,
  initialDraftId
}: {
  sourceVideoId: string;
  initialDraftId?: string;
}) {
  const t = useT();
  return (
    <OperatorStudioShell
      actions={
        <>
          <a href={`/production/final-review/${sourceVideoId}`}>{t("nav.finalReview")}</a>
          <a href="/publishing/drafts">{t("nav.publishDrafts")}</a>
        </>
      }
      description={t("operatorRoutes.publishDraftDesc")}
      title={t("operatorRoutes.publishDraftTitle")}
    >
      <PublishDraftPage initialDraftId={initialDraftId} sourceVideoId={sourceVideoId} />
    </OperatorStudioShell>
  );
}
