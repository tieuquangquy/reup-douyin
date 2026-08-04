"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { ChecklistState, RenderOutput } from "../../types/final-review";
import { checklistComplete, getRenderWarnings, isApproved, isPublishReady } from "../../lib/finalReviewState";
import { AsyncButton } from "../shared/AsyncButton";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";
import {
  FinalReviewActionStatus,
  type FinalReviewActionStatusState
} from "./FinalReviewActionStatus";

const CHECKLIST_TOTAL = 6;

export function FinalReviewActions({
  render,
  checklist,
  actionBusy,
  approvePending,
  publishReadyPending,
  actionStatus,
  onApprove,
  onPublishReady,
  onDismissStatus,
  onPause,
  onResume,
  onCancel,
  watchPaused = false,
  pausePending = false,
  cancelPending = false
}: {
  render: RenderOutput;
  checklist: ChecklistState;
  actionBusy: boolean;
  approvePending: boolean;
  publishReadyPending: boolean;
  actionStatus: FinalReviewActionStatusState | null;
  onApprove: () => void;
  onPublishReady: () => void;
  onDismissStatus?: () => void;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  watchPaused?: boolean;
  pausePending?: boolean;
  cancelPending?: boolean;
}) {
  const t = useT();
  const warnings = getRenderWarnings(render);
  const approved = isApproved(render);
  const publishReady = isPublishReady(render);
  const readyForPublish = checklistComplete(checklist) && approved;
  const checkedCount = Object.values(checklist).filter(Boolean).length;
  const publishTitle =
    warnings.length > 0
      ? `${t("finalReviewActions.approveExportHint")} ${t("finalReviewActions.warningsHint")}`
      : t("finalReviewActions.approveExportHint");

  return (
    <footer className="fr-decision-bar fr-decision-bar--compact" aria-label={t("finalReviewActions.title")}>
      <div className="fr-decision-bar__copy">
        <div className="fr-decision-bar__meta">
          <p className="fr-decision-bar__progress">
            <strong>
              {checkedCount}/{CHECKLIST_TOTAL}
            </strong>{" "}
            {t("finalReviewActions.checklistProgress")}
          </p>
          {warnings.length > 0 ? (
            <span className="fr-decision-bar__warn" title={t("finalReviewActions.warningsHint")}>
              {t("finalReviewStates.readinessChipWarnings")} {warnings.length}
            </span>
          ) : null}
        </div>
        {actionStatus ? (
          <FinalReviewActionStatus
            phase={actionStatus.phase}
            message={actionStatus.message}
            onDismiss={onDismissStatus}
            onPause={onPause}
            onResume={onResume}
            onCancel={onCancel}
            watchPaused={watchPaused}
            pausePending={pausePending}
            cancelPending={cancelPending}
          />
        ) : null}
      </div>
      <div className="fr-decision-bar__actions">
        <AsyncButton
          pending={approvePending}
          onClick={onApprove}
          disabled={actionBusy || approved}
          title={t("finalReviewActions.approveExportHint")}
          leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="approve" />}
        >
          {t("finalReviewActions.approveExport")}
        </AsyncButton>
        <AsyncButton
          className="primary"
          pending={publishReadyPending}
          onClick={onPublishReady}
          disabled={actionBusy || publishReady || !readyForPublish}
          title={publishTitle}
          leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="promote" />}
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
