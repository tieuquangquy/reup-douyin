"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { FinalReviewPrepFocus } from "../../lib/finalReviewState";
import { AsyncButton } from "../shared/AsyncButton";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";

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
  startRenderPending = false,
  prepFocus = "ocr",
  onStartRender
}: {
  sourceVideoId: string;
  actionBusy?: boolean;
  startRenderPending?: boolean;
  prepFocus?: FinalReviewPrepFocus;
  onStartRender?: () => void;
}) {
  const t = useT();
  const steps = [
    { key: "ocr" as const, label: t("finalReviewStates.emptyStep1") },
    { key: "render" as const, label: t("finalReviewStates.emptyStep2") },
    { key: "compare" as const, label: t("finalReviewStates.emptyStep3") }
  ];
  const renderIsPrimary = prepFocus === "render";

  return (
    <div className="final-review-empty final-review-prep-panel">
      <span className="final-review-prep-panel__eyebrow">{t("finalReviewStates.emptyEyebrow")}</span>
      <h2 className="final-review-prep-panel__title">{t("finalReviewStates.empty")}</h2>
      <p className="final-review-prep-panel__body">{t("finalReviewStates.emptyBody")}</p>
      <ol className="final-review-empty__step-rail" aria-label={t("finalReviewStates.emptyStepsLabel")}>
        {steps.map((step, index) => {
          const active =
            (step.key === "ocr" && prepFocus === "ocr") || (step.key === "render" && prepFocus === "render");
          const done = step.key === "ocr" && prepFocus === "render";
          return (
            <li
              className={`final-review-empty__step${active ? " is-active" : ""}${done ? " is-done" : ""}`}
              key={step.key}
              aria-current={active ? "step" : undefined}
            >
              <span aria-hidden="true" className="final-review-empty__step-index">
                {done ? "✓" : index + 1}
              </span>
              <span className="final-review-empty__step-label">{step.label}</span>
            </li>
          );
        })}
      </ol>
      <div className="final-review-empty__actions">
        {onStartRender ? (
          <AsyncButton
            className={
              renderIsPrimary
                ? "primary final-review-empty__primary"
                : "final-review-empty__primary final-review-empty__primary--quiet"
            }
            disabled={actionBusy}
            leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="process" />}
            pending={startRenderPending}
            pendingLabel={t("finalReviewStates.startingRender")}
            onClick={onStartRender}
            title={renderIsPrimary ? undefined : t("finalReviewStates.startRenderAfterOcrHint")}
          >
            {t("finalReviewStates.startRender")}
          </AsyncButton>
        ) : null}
        <nav className="final-review-empty__secondary" aria-label={t("finalReviewHeader.navLabel")}>
          <Link className="fr-tool" href={`/production/transcript-editor/${sourceVideoId}`}>
            <WorkItemActionIcon className="fr-tool__icon" kind="transcript" />
            {t("finalReviewHeader.transcriptEditor")}
          </Link>
          <Link className="fr-tool fr-tool--quiet" href="/selection/review-board">
            <WorkItemActionIcon className="fr-tool__icon" kind="details" />
            {t("finalReviewStates.backToReviewBoard")}
          </Link>
        </nav>
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
