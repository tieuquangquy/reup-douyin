"use client";

import { useT } from "../../lib/i18n";

export type TranscriptJobBusyKind = "tts" | "translate" | "reanalyze";

type Props = {
  kind: TranscriptJobBusyKind;
  jobId?: string | null;
  progressPercent?: number | null;
  cancelling?: boolean;
  onCancel?: () => void;
};

function BusyIcon() {
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

function CancelIcon() {
  return (
    <svg className="transcript-job-busy__cancel-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M6.2 6.2 13.8 13.8M13.8 6.2 6.2 13.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function TranscriptJobBusyBanner({
  kind,
  jobId,
  progressPercent,
  cancelling = false,
  onCancel
}: Props) {
  const t = useT();
  const title =
    kind === "tts"
      ? t("transcriptEditorJobBusy.titleTts")
      : kind === "translate"
        ? t("transcriptEditorJobBusy.titleTranslate")
        : t("transcriptEditorJobBusy.titleReanalyze");
  const shortId = jobId && jobId.length > 8 ? `${jobId.slice(0, 8)}…` : jobId;
  const hasPercent = typeof progressPercent === "number" && Number.isFinite(progressPercent);
  const clamped = hasPercent ? Math.max(0, Math.min(100, Math.round(progressPercent))) : null;
  const determinate = clamped !== null && clamped > 0;

  return (
    <div className="transcript-job-busy" role="status" aria-live="polite">
      <span className="transcript-job-busy__icon" aria-hidden="true">
        <BusyIcon />
      </span>
      <div className="transcript-job-busy__body">
        <div className="transcript-job-busy__title-row">
          <strong>{title}</strong>
          {clamped !== null ? (
            <span className="transcript-job-busy__percent" aria-label={`${clamped}%`}>
              {clamped}%
            </span>
          ) : null}
          {shortId ? <span className="transcript-job-busy__meta">{shortId}</span> : null}
        </div>
        <span className="transcript-job-busy__hint">{t("transcriptEditorJobBusy.hint")}</span>
        <div
          className={`transcript-job-busy__progress${determinate ? " is-determinate" : " is-indeterminate"}`}
          aria-hidden="true"
        >
          <span
            className="transcript-job-busy__progress-bar"
            style={determinate ? { width: `${clamped}%`, transform: "none" } : undefined}
          />
        </div>
      </div>
      {onCancel ? (
        <button
          type="button"
          className="transcript-job-busy__cancel"
          onClick={onCancel}
          disabled={cancelling}
        >
          <CancelIcon />
          <span>
            {cancelling ? t("transcriptEditorJobBusy.cancelling") : t("transcriptEditorJobBusy.cancel")}
          </span>
        </button>
      ) : null}
    </div>
  );
}
