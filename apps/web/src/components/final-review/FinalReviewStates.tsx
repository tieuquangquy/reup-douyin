"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { FinalReviewPrepFocus } from "../../lib/finalReviewState";
import {
  formatRenderDuration,
  hasFinalReviewOcrRun,
  isFinalReviewDialogueTranslationApprovalPending,
  isFinalReviewOcrReviewPending,
  resolveFinalReviewOcrCheckpointMetrics,
  resolveFinalReviewPrepBriefing,
  resolveFinalReviewPrepStepProgress
} from "../../lib/finalReviewState";
import type { SourceVideoAssetManifest } from "../../types/final-review";
import { AsyncButton } from "../shared/AsyncButton";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";
import {
  FinalReviewActionStatus,
  type FinalReviewActionStatusState
} from "./FinalReviewActionStatus";

export function FinalReviewLoadingState() {
  const t = useT();
  return (
    <section className="final-review-loading" role="status" aria-busy="true" aria-live="polite">
      <div className="final-review-loading__status">
        <span className="final-review-loading__spinner" aria-hidden="true" />
        <span>{t("finalReviewStates.loading")}</span>
      </div>

      <div className="final-review-loading__journey" aria-hidden="true">
        <span className="final-review-loading__step is-active" />
        <span className="final-review-loading__step" />
        <span className="final-review-loading__step" />
      </div>

      <div className="final-review-loading__split" aria-hidden="true">
        <div className="final-review-loading__hero">
          <span className="final-review-loading__preview" />
          <div className="final-review-loading__copy">
            <span className="final-review-loading__line is-narrow" />
            <span className="final-review-loading__line is-wide" />
            <span className="final-review-loading__line is-mid" />
            <span className="final-review-loading__field" />
            <span className="final-review-loading__field is-tall" />
          </div>
        </div>
        <aside className="final-review-loading__side">
          <span className="final-review-loading__line is-narrow" />
          <span className="final-review-loading__line is-wide" />
          <span className="final-review-loading__field" />
          <span className="final-review-loading__line is-mid" />
          <span className="final-review-loading__field" />
        </aside>
      </div>
    </section>
  );
}

export function FinalReviewPrepBriefing({
  sourceVideoId,
  manifest,
  ocrSummary = null,
  ocrBusy = false,
  startRenderPending = false,
  prepFocus
}: {
  sourceVideoId: string;
  manifest: SourceVideoAssetManifest | null;
  ocrSummary?: Parameters<typeof resolveFinalReviewPrepBriefing>[0]["ocrSummary"];
  ocrBusy?: boolean;
  startRenderPending?: boolean;
  prepFocus: FinalReviewPrepFocus;
}) {
  const t = useT();
  const briefing = resolveFinalReviewPrepBriefing({
    sourceVideoId,
    manifest,
    ocrSummary,
    ocrBusy,
    startRenderPending,
    prepFocus
  });
  const ocrLabel =
    briefing.ocrStatus === "running"
      ? t("finalReviewStates.prepOcrRunning")
      : briefing.ocrStatus === "review"
        ? t("finalReviewStates.prepOcrReview")
      : briefing.ocrStatus === "ready"
        ? t("finalReviewStates.prepOcrReady")
        : briefing.ocrStatus === "partial"
          ? t("finalReviewStates.prepOcrPartial")
          : t("finalReviewStates.prepOcrIdle");
  const renderLabel =
    briefing.renderStatus === "running"
      ? t("finalReviewStates.prepRenderRunning")
      : t("finalReviewStates.prepRenderNone");
  const durationLabel =
    briefing.durationSeconds == null ? "—" : formatRenderDuration(briefing.durationSeconds);
  const activity =
    briefing.ocrStatus === "running"
      ? t("finalReviewStates.prepJobOcrRunning")
      : briefing.renderStatus === "running"
        ? t("finalReviewStates.prepJobRenderRunning")
        : null;

  return (
    <section className="final-review-prep-briefing" aria-label={t("finalReviewStates.prepBriefingLabel")}>
      <div className={`final-review-prep-briefing__shell is-phase-${briefing.phase}`}>
        <div className="final-review-prep-briefing__lead">
          <p
            className={`final-review-prep-briefing__phase-badge is-phase-${briefing.phase}`}
            title={
              briefing.phase === "render"
                ? t("finalReviewStates.prepPhaseRender")
                : t("finalReviewStates.prepPhaseClean")
            }
          >
            {briefing.phase === "render"
              ? t("finalReviewStates.prepPhaseBadgeRender")
              : t("finalReviewStates.prepPhaseBadgeClean")}
          </p>
          <p className="final-review-prep-briefing__goal">{t("finalReviewStates.prepOutcomeGoal")}</p>
        </div>
        <ul className="final-review-prep-briefing__tiles">
          <li className="final-review-prep-briefing__tile is-source">
            <span className="final-review-prep-briefing__tile-label">
              {t("finalReviewStates.prepContextSource")}
            </span>
            <strong
              className="final-review-prep-briefing__tile-value"
              title={briefing.caption ?? sourceVideoId}
            >
              {briefing.caption ? truncatePrepCaption(briefing.caption, 36) : briefing.sourceLabel}
            </strong>
          </li>
          <li className="final-review-prep-briefing__tile is-duration">
            <span className="final-review-prep-briefing__tile-label">
              {t("finalReviewStates.prepContextDuration")}
            </span>
            <strong className="final-review-prep-briefing__tile-value">{durationLabel}</strong>
          </li>
          <li className={`final-review-prep-briefing__tile is-ocr is-ocr-${briefing.ocrStatus}`}>
            <span className="final-review-prep-briefing__tile-label">
              <span className="final-review-prep-briefing__status-dot" aria-hidden="true" />
              {t("finalReviewStates.prepContextOcr")}
            </span>
            <strong className="final-review-prep-briefing__tile-value">{ocrLabel}</strong>
          </li>
          <li className={`final-review-prep-briefing__tile is-render is-render-${briefing.renderStatus}`}>
            <span className="final-review-prep-briefing__tile-label">
              <span className="final-review-prep-briefing__status-dot" aria-hidden="true" />
              {t("finalReviewStates.prepContextRender")}
            </span>
            <strong className="final-review-prep-briefing__tile-value">{renderLabel}</strong>
          </li>
        </ul>
        {activity ? (
          <p className="final-review-prep-briefing__activity" role="status">
            <span>{activity}</span>
            <Link className="final-review-prep-briefing__jobs" href="/ops/jobs">
              {t("finalReviewStates.prepOpenJobs")}
            </Link>
          </p>
        ) : (
          <p className="final-review-prep-briefing__hint">{t("finalReviewStates.emptyPrepHint")}</p>
        )}
      </div>
    </section>
  );
}

function truncatePrepCaption(caption: string, max = 42): string {
  if (caption.length <= max) return caption;
  return `${caption.slice(0, max - 1)}…`;
}

export function FinalReviewPrepJourney({
  prepFocus,
  ocrSummary = null,
  ocrBusy = false,
  visualCleanBusy = false,
  ocrWatchPaused = false,
  approveBusy = false,
  actionBusy = false,
  startRenderPending = false,
  renderWatchPaused = false,
  ocrProgressPercent = null,
  renderProgressPercent = null,
  onAnalyze,
  onStartRender
}: {
  prepFocus: FinalReviewPrepFocus;
  ocrSummary?: Parameters<typeof resolveFinalReviewPrepStepProgress>[0]["ocrSummary"];
  ocrBusy?: boolean;
  visualCleanBusy?: boolean;
  /** UI stopped watching; job may still run — quiet Paused CTA, no spinner. */
  ocrWatchPaused?: boolean;
  approveBusy?: boolean;
  actionBusy?: boolean;
  startRenderPending?: boolean;
  renderWatchPaused?: boolean;
  ocrProgressPercent?: number | null;
  renderProgressPercent?: number | null;
  onAnalyze?: () => void;
  onStartRender?: () => void;
}) {
  const t = useT();
  const progress = resolveFinalReviewPrepStepProgress({
    ocrSummary,
    ocrBusy: ocrBusy || visualCleanBusy,
    startRenderPending,
    ocrProgressPercent,
    renderProgressPercent
  });
  const ocrReviewPending = isFinalReviewOcrReviewPending(ocrSummary);
  const ocrCheckpoint = resolveFinalReviewOcrCheckpointMetrics(ocrSummary);
  const dialogueTranslationPending =
    isFinalReviewDialogueTranslationApprovalPending(ocrSummary);
  const visualCheckpointLabel =
    ocrSummary?.workflow_stage === "WAITING_RESIDUAL_TRIAGE"
      ? t("finalReviewVisual.stageWaitingResidualTriage")
      : ocrSummary?.workflow_stage === "WAITING_RESIDUAL_REVIEW"
        ? t("finalReviewVisual.stageWaitingResidualReview")
        : null;
  const lockedLabel = t("finalReviewStates.emptyStepLocked");
  const waitingApprovalLabel = t("finalReviewStates.journeyWaitingTranslationApproval");
  const waitingOcrReviewLabel = t("finalReviewStates.journeyWaitingOcrReview").replace(
    "{count}",
    String(ocrCheckpoint.manual)
  );
  const steps = [
    {
      key: "ocr" as const,
      progressKey: "clean" as const,
      label: t("finalReviewStates.emptyStepShort1"),
      desc: dialogueTranslationPending
        ? waitingApprovalLabel
        : ocrReviewPending
          ? waitingOcrReviewLabel
        : t("finalReviewStates.emptyStepDesc1"),
      cta: ocrWatchPaused
        ? t("finalReviewVisual.analyzePausedShort")
        : ocrReviewPending
          ? t("finalReviewVisual.reviewOcrBelow")
        : visualCheckpointLabel
          ? visualCheckpointLabel
        : hasFinalReviewOcrRun(ocrSummary)
          ? t("finalReviewStates.emptyStepCta1Again")
          : t("finalReviewStates.emptyStepCta1"),
      icon: ocrReviewPending ? "details" as const : "recheck" as const,
      pending: (ocrBusy || visualCleanBusy) && !ocrWatchPaused && !ocrReviewPending && !dialogueTranslationPending,
      pendingLabel: t(
        visualCleanBusy
          ? "finalReviewVisual.visualCleanInProgress"
          : "finalReviewVisual.analyzing"
      ),
      locked: false,
      hideCta: dialogueTranslationPending || Boolean(visualCheckpointLabel),
      statusLabel: dialogueTranslationPending
        ? waitingApprovalLabel
        : ocrReviewPending
          ? waitingOcrReviewLabel
          : visualCheckpointLabel,
      attention: dialogueTranslationPending || ocrReviewPending || Boolean(visualCheckpointLabel),
      disabled: approveBusy || !onAnalyze || ocrWatchPaused || dialogueTranslationPending,
      onClick: onAnalyze,
      primary: prepFocus === "ocr" && !ocrWatchPaused && !dialogueTranslationPending,
      title: ocrWatchPaused
        ? t("finalReviewVisual.ocrWatchPaused")
        : dialogueTranslationPending
          ? waitingApprovalLabel
          : undefined as string | undefined
    },
    {
      key: "render" as const,
      progressKey: "render" as const,
      label: t("finalReviewStates.emptyStepShort2"),
      desc: t("finalReviewStates.emptyStepDesc2"),
      cta: renderWatchPaused
        ? t("finalReviewStates.renderPausedShort")
        : t("finalReviewStates.emptyStepCta2"),
      icon: "process" as const,
      pending: startRenderPending && !renderWatchPaused,
      pendingLabel: t("finalReviewStates.startingRender"),
      locked: prepFocus === "ocr",
      hideCta: false,
      statusLabel: null as string | null,
      attention: false,
      disabled:
        prepFocus === "ocr" ||
        actionBusy ||
        ocrBusy ||
        visualCleanBusy ||
        approveBusy ||
        !onStartRender ||
        renderWatchPaused,
      onClick: onStartRender,
      primary: prepFocus === "render" && !renderWatchPaused,
      title:
        prepFocus === "ocr"
          ? t("finalReviewStates.emptyStepLockedHintRender")
          : renderWatchPaused
            ? t("finalReviewStates.renderWatchPaused")
            : undefined
    },
    {
      key: "compare" as const,
      progressKey: "compare" as const,
      label: t("finalReviewStates.emptyStepShort3"),
      desc: t("finalReviewStates.emptyStepDesc3"),
      cta: t("finalReviewStates.emptyStepCta3"),
      icon: "details" as const,
      pending: false,
      pendingLabel: undefined,
      locked: true,
      hideCta: false,
      statusLabel: null as string | null,
      attention: false,
      disabled: true,
      onClick: undefined,
      primary: false,
      title: t("finalReviewStates.emptyStepLockedHintCompare")
    }
  ];

  return (
    <ol
      className="final-review-empty__step-rail final-review-prep-journey final-review-prep-steps"
      aria-label={t("finalReviewStates.emptyStepsLabel")}
    >
      {steps.map((step, index) => {
        const active =
          (step.key === "ocr" && prepFocus === "ocr") || (step.key === "render" && prepFocus === "render");
        const done = step.key === "ocr" && prepFocus === "render";
        const locked = step.locked && !done;
        const pct = progress[step.progressKey];
        const showOcrCheckpoint = step.key === "ocr" && ocrReviewPending;
        const prefix = t("finalReviewStates.emptyStepLabelPrefix").replace("{n}", String(index + 1));
        const ctaLabel = locked ? lockedLabel : step.cta;
        return (
          <li
            className={`final-review-prep-steps__item${active ? " is-active" : ""}${done ? " is-done" : ""}${locked ? " is-locked" : ""}${step.attention ? " is-attention" : ""}`}
            key={step.key}
            aria-current={active ? "step" : undefined}
          >
            <span aria-hidden="true" className="final-review-prep-steps__marker">
              {done ? "✓" : locked ? (
                <svg className="final-review-prep-steps__lock-icon" viewBox="0 0 16 16" width="12" height="12">
                  <path
                    d="M5.2 7.1V5.4a2.8 2.8 0 0 1 5.6 0v1.7M4.4 7.1h7.2v5.6H4.4z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : (
                index + 1
              )}
            </span>
            <div className={`final-review-prep-steps__card${locked ? " is-locked" : ""}${step.attention ? " is-attention" : ""}`}>
              <span aria-hidden="true" className="final-review-prep-steps__icon">
                <WorkItemActionIcon className="final-review-prep-steps__icon-svg" kind={step.icon} />
              </span>
              <div className="final-review-prep-steps__body">
                <div className="final-review-prep-steps__heading">
                  <h3 className="final-review-prep-steps__title">
                    <span className="final-review-prep-steps__prefix">{prefix}</span> {step.label}
                  </h3>
                  {showOcrCheckpoint ? null : <p className="final-review-prep-steps__desc">{step.desc}</p>}
                </div>
                {showOcrCheckpoint ? (
                  <div className="final-review-prep-steps__checkpoint" role="status">
                    <span className="is-done">{t("finalReviewStates.journeyAnalysisDone")}</span>
                    <span className="is-review">
                      {t("finalReviewStates.journeyReviewCount").replace(
                        "{count}",
                        String(ocrCheckpoint.manual)
                      )}
                    </span>
                  </div>
                ) : (
                  <div className="final-review-prep-steps__progress" aria-hidden="true">
                    <div className="final-review-prep-steps__bar">
                      <span className="final-review-prep-steps__bar-fill" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="final-review-prep-steps__pct">{pct}%</span>
                  </div>
                )}
              </div>
              {step.hideCta ? (
                <span className="final-review-prep-steps__waiting" role="status" title={step.statusLabel ?? undefined}>
                  <svg className="final-review-prep-steps__waiting-icon" viewBox="0 0 16 16" aria-hidden="true">
                    <circle cx="8" cy="8" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M8 5.2v3.1l2 1.2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>{step.statusLabel}</span>
                </span>
              ) : (
              <AsyncButton
                className={`final-review-prep-steps__cta${step.primary && !locked ? " primary" : " is-quiet"}${locked ? " is-locked" : ""}`}
                disabled={step.disabled || locked}
                leadingIcon={
                  locked ? (
                    <svg className="fr-tool__icon" viewBox="0 0 16 16" aria-hidden="true">
                      <path
                        d="M5.2 7.1V5.4a2.8 2.8 0 0 1 5.6 0v1.7M4.4 7.1h7.2v5.6H4.4z"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinejoin="round"
                      />
                    </svg>
                  ) : (ocrWatchPaused && step.key === "ocr") || (renderWatchPaused && step.key === "render") ? (
                    <svg className="fr-tool__icon" viewBox="0 0 16 16" aria-hidden="true">
                      <rect x="4.6" y="3.8" width="2.4" height="8.4" rx="0.9" fill="currentColor" />
                      <rect x="9" y="3.8" width="2.4" height="8.4" rx="0.9" fill="currentColor" />
                    </svg>
                  ) : (
                    <WorkItemActionIcon className="fr-tool__icon" kind={step.icon} />
                  )
                }
                pending={step.pending}
                pendingLabel={step.pendingLabel}
                onClick={step.onClick}
                title={step.title}
                aria-label={locked ? `${lockedLabel}: ${step.label}` : undefined}
              >
                {ctaLabel}
              </AsyncButton>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function FinalReviewEmptyState({
  sourceVideoId,
  actionBusy = false,
  startRenderPending = false,
  prepFocus = "ocr",
  presentation = "side",
  actionStatus = null,
  hideTranscriptLink = false,
  onStartRender,
  onDismissStatus,
  onPause,
  onResume,
  onCancel,
  watchPaused = false,
  pausePending = false,
  cancelPending = false
}: {
  sourceVideoId: string;
  actionBusy?: boolean;
  startRenderPending?: boolean;
  prepFocus?: FinalReviewPrepFocus;
  presentation?: "hero" | "side" | "bar";
  actionStatus?: FinalReviewActionStatusState | null;
  /** When the visual gate already owns Transcript Editor, hide the duplicate side-card link. */
  hideTranscriptLink?: boolean;
  onStartRender?: () => void;
  onDismissStatus?: () => void;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  watchPaused?: boolean;
  pausePending?: boolean;
  cancelPending?: boolean;
}) {
  const t = useT();
  const isSide = presentation === "side";
  const isBar = presentation === "bar";
  const useCompactActions = isSide || isBar;
  const renderLocked = prepFocus === "ocr";
  const renderIsPrimary = (prepFocus === "render" && !isSide) || isBar;
  const heroBodyKey =
    prepFocus === "render" || isBar ? "finalReviewStates.emptyBodyReady" : "finalReviewStates.emptyBody";
  const hideStartRenderCta =
    watchPaused || actionStatus?.phase === "queued" || actionStatus?.phase === "running";

  const startRenderButton =
    onStartRender && !renderLocked && !hideStartRenderCta ? (
      <AsyncButton
        className={
          renderIsPrimary
            ? `primary final-review-empty__primary${useCompactActions ? " final-review-empty__primary--compact" : ""}`
            : `final-review-empty__primary final-review-empty__primary--quiet${
                useCompactActions ? " final-review-empty__primary--compact" : ""
              }`
        }
        disabled={actionBusy}
        leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="process" />}
        pending={startRenderPending}
        pendingLabel={t("finalReviewStates.startingRender")}
        onClick={onStartRender}
        title={
          useCompactActions
            ? t("finalReviewStates.startRender")
            : renderIsPrimary
              ? undefined
              : t("finalReviewStates.startRenderAfterOcrHint")
        }
      >
        {t(useCompactActions ? "finalReviewStates.startRenderShort" : "finalReviewStates.startRender")}
      </AsyncButton>
    ) : null;

  const barNav = (
    <nav
      className="final-review-empty__secondary final-review-empty__secondary--inline final-review-empty__bar-nav"
      aria-label={t("finalReviewHeader.navLabel")}
    >
      {hideTranscriptLink ? null : (
        <Link
          className="fr-tool final-review-empty__nav-pill"
          href={`/production/transcript-editor/${sourceVideoId}`}
          title={t("finalReviewHeader.transcriptEditor")}
        >
          <WorkItemActionIcon className="fr-tool__icon" kind="transcript" />
          {t("finalReviewHeader.transcriptEditor")}
        </Link>
      )}
      <Link
        className="fr-tool final-review-empty__nav-pill"
        href="/selection/review-board"
        title={t("finalReviewStates.backToReviewBoard")}
      >
        <WorkItemActionIcon className="fr-tool__icon" kind="details" />
        {t("finalReviewStates.boardShort")}
      </Link>
    </nav>
  );

  const actions = (
    <div
      className={`final-review-empty__actions${
        isSide ? " final-review-empty__actions--side" : ""
      }`}
    >
      {startRenderButton}
      <nav
        className={`final-review-empty__secondary${isSide ? " final-review-empty__secondary--side" : ""}`}
        aria-label={t("finalReviewHeader.navLabel")}
      >
        {hideTranscriptLink ? null : (
          <Link className="fr-tool" href={`/production/transcript-editor/${sourceVideoId}`}>
            <WorkItemActionIcon className="fr-tool__icon" kind="transcript" />
            {t("finalReviewHeader.transcriptEditorFull")}
          </Link>
        )}
        <Link className="fr-tool" href="/selection/review-board">
          <WorkItemActionIcon className="fr-tool__icon" kind="details" />
          {t("finalReviewStates.backToReviewBoard")}
        </Link>
      </nav>
    </div>
  );

  if (isBar) {
    return (
      <div
        className={`final-review-empty final-review-prep-panel final-review-empty--bar${
          actionStatus ? ` has-status is-status-${actionStatus.phase}` : ""
        }`}
      >
        <div className="final-review-empty__bar-top">
          <div className="final-review-empty__bar-identity">
            <span className="final-review-empty__bar-icon" aria-hidden="true">
              <WorkItemActionIcon className="final-review-empty__bar-icon-svg" kind="auto-render" />
            </span>
            <div className="final-review-empty__bar-heading">
              <span className="final-review-prep-panel__eyebrow">{t("finalReviewStates.emptyEyebrow")}</span>
              <h2 className="final-review-prep-panel__title">{t("finalReviewStates.empty")}</h2>
              <p className="final-review-prep-panel__body">{t(heroBodyKey)}</p>
            </div>
          </div>
          <div className="final-review-empty__bar-actions">
            {startRenderButton}
            {barNav}
          </div>
        </div>
        {actionStatus ? (
          <div className="final-review-empty__bar-status">
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
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className={`final-review-empty final-review-prep-panel${
        isSide ? " final-review-empty--side" : " final-review-empty--hero"
      }${isSide && renderLocked ? " final-review-empty--locked" : ""}`}
      aria-disabled={isSide && renderLocked ? true : undefined}
    >
      <div className="final-review-empty__side-copy">
        <div className="final-review-empty__side-heading">
          <span className="final-review-prep-panel__eyebrow">
            {isSide ? t("finalReviewStates.emptyUpNext") : t("finalReviewStates.emptyEyebrow")}
          </span>
          {isSide && renderLocked ? (
            <span className="final-review-empty__lock-badge">
              <svg className="final-review-empty__lock-badge-icon" viewBox="0 0 16 16" aria-hidden="true">
                <path
                  d="M5.2 7.1V5.4a2.8 2.8 0 0 1 5.6 0v1.7M4.4 7.1h7.2v5.6H4.4z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                />
              </svg>
              {t("finalReviewStates.emptyStepLocked")}
            </span>
          ) : null}
        </div>
        <h2 className="final-review-prep-panel__title">
          {isSide ? t("finalReviewStates.emptySideTitle") : t("finalReviewStates.empty")}
        </h2>
        {isSide && renderLocked ? (
          <p className="final-review-empty__lock-note" title={t("finalReviewStates.emptyBodySideLocked")}>
            <svg className="final-review-empty__lock-note-icon" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
              <path
                d="M5.2 7.1V5.4a2.8 2.8 0 0 1 5.6 0v1.7M4.4 7.1h7.2v5.6H4.4z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
            </svg>
            <span>{t("finalReviewStates.emptyBodySideLocked")}</span>
          </p>
        ) : (
          <p className="final-review-prep-panel__body">
            {isSide ? t("finalReviewStates.emptyBodySideShort") : t(heroBodyKey)}
          </p>
        )}
        {isSide && !renderLocked ? (
          <p className="final-review-empty__side-cue">{t("finalReviewStates.emptySideCue")}</p>
        ) : null}
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
      {actions}
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
