"use client";

import { useEffect } from "react";
import { parseFinalReviewActionStatus, shouldAutoDismissFinalReviewActionStatus } from "../../lib/finalReviewState";
import { useT } from "../../lib/i18n";

export type FinalReviewActionStatusPhase = "queued" | "running" | "success" | "warning" | "error";

export type FinalReviewActionStatusState = {
  phase: FinalReviewActionStatusPhase;
  message: string;
};

/** Success/warning strips auto-hide after this read window; errors stay until dismissed. */
export const FINAL_REVIEW_STATUS_AUTO_DISMISS_MS = 6000;

type Props = {
  phase: FinalReviewActionStatusPhase;
  message: string;
  onDismiss?: () => void;
  /** Pause watching (UI); toggles to Resume when `watchPaused`. */
  onPause?: () => void;
  onResume?: () => void;
  /** Cancel the durable OCR job. */
  onCancel?: () => void;
  watchPaused?: boolean;
  pausePending?: boolean;
  cancelPending?: boolean;
};

function StatusIcon({ phase }: { phase: FinalReviewActionStatusPhase }) {
  if (phase === "success") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M5 10.2 8.2 13.4 15 6.6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (phase === "warning") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M10 4.5 16 15H4L10 4.5Zm0 3v3.5M10 13.5h.01"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (phase === "error") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.7" />
        <path d="M10 6.5v5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="10" cy="14" r="0.9" fill="currentColor" />
      </svg>
    );
  }
  if (phase === "running") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <circle
          cx="10"
          cy="10"
          r="7"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeDasharray="28 16"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 6.2v4.2l2.4 1.4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <rect x="6.5" y="5" width="2.2" height="10" rx="1" fill="currentColor" />
      <rect x="11.3" y="5" width="2.2" height="10" rx="1" fill="currentColor" />
    </svg>
  );
}

function ResumeIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M7.4 5.2a.85.85 0 0 1 1.3-.72l7.2 4.3a.85.85 0 0 1 0 1.44l-7.2 4.3a.85.85 0 0 1-1.3-.72V5.2Z" fill="currentColor" />
    </svg>
  );
}

function CancelIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M6.6 6.6 13.4 13.4M13.4 6.6 6.6 13.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function FinalReviewActionStatus({
  phase,
  message,
  onDismiss,
  onPause,
  onResume,
  onCancel,
  watchPaused = false,
  pausePending = false,
  cancelPending = false
}: Props) {
  const t = useT();
  const live = phase === "error" ? "assertive" : "polite";
  const role = phase === "error" ? "alert" : "status";
  const inFlight = phase === "queued" || phase === "running" || watchPaused;
  const showControls = inFlight && (Boolean(onPause) || Boolean(onResume) || Boolean(onCancel));
  const showProgress = phase === "running" && !watchPaused;
  const statusMessage = parseFinalReviewActionStatus(phase, message);
  const canDismiss =
    Boolean(onDismiss) && (phase === "success" || phase === "warning" || phase === "error") && !watchPaused;
  const autoDismiss = canDismiss && shouldAutoDismissFinalReviewActionStatus(phase);

  useEffect(() => {
    if (!autoDismiss || !onDismiss) return;
    const timer = window.setTimeout(onDismiss, FINAL_REVIEW_STATUS_AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [autoDismiss, onDismiss, phase, message]);

  return (
    <div
      className={`fr-action-status is-${phase}${watchPaused ? " is-watch-paused" : ""}`}
      role={role}
      aria-live={live}
      aria-busy={phase === "running" || phase === "queued" ? true : undefined}
    >
      <span className="fr-action-status__icon" aria-hidden="true">
        <StatusIcon phase={watchPaused ? "warning" : phase} />
      </span>
      <div className="fr-action-status__body">
        <div className="fr-action-status__copy">
          <p className="fr-action-status__message">
            {statusMessage.title ? (
              <strong className="fr-action-status__message-title">{statusMessage.title}</strong>
            ) : null}
            <span className="fr-action-status__message-detail">{statusMessage.detail}</span>
          </p>
          {statusMessage.flags.length ? (
            <ul className="fr-action-status__flags">
              {statusMessage.flags.map((flag) => (
                <li key={flag} className="fr-action-status__flag">
                  {flag}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        {showProgress ? (
          <div className="fr-action-status__progress is-indeterminate" aria-hidden="true">
            <span className="fr-action-status__progress-bar" />
          </div>
        ) : null}
      </div>
      {showControls ? (
        <div className="fr-action-status__controls">
          {watchPaused
            ? onResume ? (
                <button
                  type="button"
                  className="fr-action-status__pause is-resume"
                  aria-label={pausePending ? t("finalReviewVisual.resumingOcr") : t("finalReviewVisual.resumeOcr")}
                  title={pausePending ? t("finalReviewVisual.resumingOcr") : t("finalReviewVisual.resumeOcr")}
                  disabled={pausePending || cancelPending}
                  onClick={onResume}
                >
                  <ResumeIcon />
                </button>
              ) : null
            : onPause ? (
                <button
                  type="button"
                  className="fr-action-status__pause"
                  aria-label={pausePending ? t("finalReviewVisual.pausingOcr") : t("finalReviewVisual.pauseOcr")}
                  title={pausePending ? t("finalReviewVisual.pausingOcr") : t("finalReviewVisual.pauseOcr")}
                  disabled={pausePending || cancelPending}
                  onClick={onPause}
                >
                  <PauseIcon />
                </button>
              ) : null}
          {onCancel ? (
            <button
              type="button"
              className="fr-action-status__cancel"
              aria-label={cancelPending ? t("finalReviewVisual.cancellingOcr") : t("finalReviewVisual.cancelOcr")}
              title={cancelPending ? t("finalReviewVisual.cancellingOcr") : t("finalReviewVisual.cancelOcr")}
              disabled={cancelPending || pausePending}
              onClick={onCancel}
            >
              <CancelIcon />
            </button>
          ) : null}
        </div>
      ) : null}
      {canDismiss ? (
        <button
          type="button"
          className="fr-action-status__dismiss"
          aria-label={t("common.close")}
          title={t("common.close")}
          onClick={onDismiss}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M6.5 6.5 13.5 13.5M13.5 6.5 6.5 13.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
          </svg>
        </button>
      ) : null}
    </div>
  );
}
