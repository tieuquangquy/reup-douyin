"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { ChecklistState, RenderOutput } from "../../types/final-review";
import { checklistComplete, getRenderWarnings, isApproved, isPublishReady } from "../../lib/finalReviewState";
import { AsyncButton } from "../shared/AsyncButton";

const CHECKLIST_TOTAL = 6;

export function FinalReviewActions({
  render,
  checklist,
  actionBusy,
  approvePending,
  publishReadyPending,
  actionMessage,
  onApprove,
  onPublishReady
}: {
  render: RenderOutput;
  checklist: ChecklistState;
  actionBusy: boolean;
  approvePending: boolean;
  publishReadyPending: boolean;
  actionMessage: string | null;
  onApprove: () => void;
  onPublishReady: () => void;
}) {
  const t = useT();
  const warnings = getRenderWarnings(render);
  const approved = isApproved(render);
  const publishReady = isPublishReady(render);
  const readyForPublish = checklistComplete(checklist) && approved;
  const checkedCount = Object.values(checklist).filter(Boolean).length;

  return (
    <footer className="fr-decision-bar" aria-label={t("finalReviewActions.title")}>
      <div className="fr-decision-bar__copy">
        <p className="fr-decision-bar__progress">
          <strong>
            {checkedCount}/{CHECKLIST_TOTAL}
          </strong>{" "}
          {t("finalReviewActions.checklistProgress")}
        </p>
        <p className="fr-decision-bar__hint">{t("finalReviewActions.approveExportHint")}</p>
        {warnings.length > 0 ? <p className="warning-line">{t("finalReviewActions.warningsHint")}</p> : null}
        {actionMessage ? <p className="action-message">{actionMessage}</p> : null}
      </div>
      <div className="fr-decision-bar__actions">
        <AsyncButton pending={approvePending} onClick={onApprove} disabled={actionBusy || approved}>
          {t("finalReviewActions.approveExport")}
        </AsyncButton>
        <AsyncButton
          className="primary"
          pending={publishReadyPending}
          onClick={onPublishReady}
          disabled={actionBusy || publishReady || !readyForPublish}
        >
          {t("finalReviewActions.markPublishReady")}
        </AsyncButton>
        {publishReady ? (
          <Link className="fr-decision-bar__link" href={`/source-videos/${render.source_video_id}/publish`}>
            {t("finalReviewActions.preparePublishDraft")}
          </Link>
        ) : null}
      </div>
    </footer>
  );
}
