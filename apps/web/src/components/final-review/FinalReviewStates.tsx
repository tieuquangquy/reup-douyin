"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";

export function FinalReviewLoadingState() {
  const t = useT();
  return (
    <main className="final-review">
      <div className="state-panel">
        <h2>{t("finalReviewStates.loading")}</h2>
        <p>{t("finalReviewStates.loadingBody")}</p>
      </div>
    </main>
  );
}

export function FinalReviewEmptyState({
  sourceVideoId,
  actionBusy = false,
  onStartRender
}: {
  sourceVideoId: string;
  actionBusy?: boolean;
  onStartRender?: () => void;
}) {
  const t = useT();
  return (
    <div className="state-panel final-review-empty">
      <h2>{t("finalReviewStates.empty")}</h2>
      <p>{t("finalReviewStates.emptyBody")}</p>
      <p className="final-review-empty__steps">{t("finalReviewStates.emptySteps")}</p>
      <div className="action-stack final-review-empty__actions">
        {onStartRender ? (
          <button type="button" className="primary" onClick={onStartRender} disabled={actionBusy}>
            {actionBusy ? t("finalReviewStates.startingRender") : t("finalReviewStates.startRender")}
          </button>
        ) : null}
        <Link href={`/production/transcript-editor/${sourceVideoId}`}>{t("finalReviewHeader.transcriptEditor")}</Link>
        <Link href="/selection/review-board">{t("finalReviewStates.backToReviewBoard")}</Link>
      </div>
    </div>
  );
}

export function FinalReviewErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const t = useT();
  return (
    <main className="final-review">
      <div className="state-panel">
        <h2>{t("finalReviewStates.error")}</h2>
        <p>{message}</p>
        <button className="primary" onClick={onRetry}>
          {t("finalReviewStates.retry")}
        </button>
      </div>
    </main>
  );
}
