"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { ChecklistState, RenderOutput } from "../../types/final-review";
import { checklistComplete, getRenderWarnings, isApproved, isPublishReady } from "../../lib/finalReviewState";

const CHECKLIST_TOTAL = 6;

export function FinalReviewActions({
  render,
  checklist,
  actionBusy,
  actionMessage,
  onApprove,
  onPublishReady
}: {
  render: RenderOutput;
  checklist: ChecklistState;
  actionBusy: boolean;
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
        <button type="button" onClick={onApprove} disabled={actionBusy || approved}>
          {t("finalReviewActions.approveExport")}
        </button>
        <button
          type="button"
          className="primary"
          onClick={onPublishReady}
          disabled={actionBusy || publishReady || !readyForPublish}
        >
          {t("finalReviewActions.markPublishReady")}
        </button>
        {publishReady ? (
          <Link className="fr-decision-bar__link" href={`/source-videos/${render.source_video_id}/publish`}>
            {t("finalReviewActions.preparePublishDraft")}
          </Link>
        ) : null}
      </div>
    </footer>
  );
}
