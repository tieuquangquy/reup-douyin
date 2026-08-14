"use client";

import { useT } from "../../lib/i18n";
import { AsyncButton } from "../shared/AsyncButton";

type Props = {
  reviewSegmentIndexes: number[];
  approving: boolean;
  disabled: boolean;
  onApprove: () => void;
};

function ApproveSourceIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M5 10.2 8.2 13.4 15 6.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function TranscriptSourceReviewNotice({
  reviewSegmentIndexes,
  approving,
  disabled,
  onApprove
}: Props) {
  const t = useT();
  const hasSegments = reviewSegmentIndexes.length > 0;

  return (
    <section className="transcript-source-review is-compact" role="status" aria-live="polite">
      <div className="transcript-source-review__icon" aria-hidden="true">
        <svg viewBox="0 0 20 20">
          <circle cx="10" cy="10" r="7.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M10 6.5v4.2" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          <circle cx="10" cy="13.6" r="0.9" fill="currentColor" />
        </svg>
      </div>

      <div className="transcript-source-review__body">
        <div className="transcript-source-review__title-row">
          <h2 className="transcript-source-review__title">{t("transcriptEditorPage.sourceApprovalTitle")}</h2>
          {hasSegments ? (
            <div className="transcript-source-review__chips" aria-label={t("transcriptEditorPage.sourceApprovalSegments")}>
              {reviewSegmentIndexes.map((index) => (
                <span className="transcript-source-review__chip" key={index}>
                  #{index}
                </span>
              ))}
            </div>
          ) : null}
        </div>
        <p className="transcript-source-review__copy">{t("transcriptEditorPage.sourceApprovalRequired")}</p>
      </div>

      <AsyncButton
        className="transcript-source-review__cta"
        pending={approving}
        pendingLabel={t("transcriptEditorPage.approvingSource")}
        leadingIcon={<ApproveSourceIcon />}
        onClick={onApprove}
        disabled={disabled}
      >
        {t("transcriptEditorPage.approveSource")}
      </AsyncButton>
    </section>
  );
}
