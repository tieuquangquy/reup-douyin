"use client";

import { useT } from "../../lib/i18n";
import type {
  FinalReviewReadiness,
  FinalReviewReadinessBlocker,
  FinalReviewReadinessChip
} from "../../lib/finalReviewState";

const BLOCKER_KEYS: Record<FinalReviewReadinessBlocker, string> = {
  checklist: "finalReviewStates.readinessBlockerChecklist",
  approve: "finalReviewStates.readinessBlockerApprove",
  risk: "finalReviewStates.readinessBlockerRisk",
  risk_decision: "finalReviewStates.readinessBlockerRiskDecision"
};

const CHIP_LABEL_KEYS: Record<FinalReviewReadinessChip["id"], string> = {
  checklist: "finalReviewStates.readinessChipChecklist",
  warnings: "finalReviewStates.readinessChipWarnings",
  risk: "finalReviewStates.readinessChipRisk",
  approved: "finalReviewStates.readinessChipApproved",
  publish_ready: "finalReviewStates.readinessChipPublishReady"
};

export function FinalReviewReadinessStrip({ readiness }: { readiness: FinalReviewReadiness }) {
  const t = useT();
  const missing =
    readiness.blockers.length > 0
      ? readiness.blockers.map((id) => t(BLOCKER_KEYS[id])).join(" · ")
      : null;
  const toneClass = readiness.publishReady
    ? " is-ready"
    : readiness.blockers.length > 0
      ? " is-blocked"
      : "";
  const releaseState = readiness.publishReady
    ? "ready"
    : readiness.blockers.length > 0
      ? "blocked"
      : "pending";
  const releaseTitle = readiness.publishReady
    ? t("finalReviewStates.readinessReleaseReady")
    : readiness.blockers.length > 0
      ? t("finalReviewStates.readinessReleaseBlocked").replace("{count}", String(readiness.blockers.length))
      : t("finalReviewStates.readinessReleaseMark");
  const gateChips = readiness.chips.filter(
    (chip) => chip.id === "checklist" || chip.id === "warnings" || chip.id === "risk"
  );
  const isEvidenceMissing = (chip: FinalReviewReadinessChip) =>
    chip.id === "checklist" && readiness.publishReady && !readiness.checklistOk;

  return (
    <section
      className={`final-review-readiness final-review-readiness--rail final-review-readiness--panel${toneClass}`}
      aria-label={t("finalReviewStates.readinessTitle")}
    >
      <div className={`final-review-readiness__head final-review-readiness__release is-${releaseState}`}>
        <span className="final-review-readiness__release-icon" aria-hidden="true">
          <ReleaseReadinessIcon state={releaseState} />
        </span>
        <div className="final-review-readiness__release-copy">
          <h2 className="final-review-readiness__title">{releaseTitle}</h2>
          {readiness.publishReady ? (
            <p className="final-review-readiness__status is-ready">{t("finalReviewStates.readinessAllClear")}</p>
          ) : missing ? (
            <p className="final-review-readiness__status is-blocked">
              <span className="final-review-readiness__missing-prefix">
                {t("finalReviewStates.readinessMissingPrefix")}
              </span>{" "}
              {missing}
            </p>
          ) : (
            <p className="final-review-readiness__status">{t("finalReviewStates.readinessAlmost")}</p>
          )}
        </div>
      </div>
      <ul className="final-review-readiness__metrics final-review-readiness__gates">
        {gateChips.map((chip) => {
          const evidenceMissing = isEvidenceMissing(chip);
          const gateTone = evidenceMissing ? "muted" : chip.tone;
          return (
            <li
              key={chip.id}
              className={`final-review-readiness__metric is-${gateTone}${chip.done ? " is-done" : ""}${evidenceMissing ? " is-evidence" : ""}`}
            >
              <span className="final-review-readiness__metric-dot" aria-hidden="true" />
              <span className="final-review-readiness__metric-copy">
                <span className="final-review-readiness__metric-label">
                  {t(evidenceMissing ? "finalReviewStates.readinessChipChecklistEvidence" : CHIP_LABEL_KEYS[chip.id])}
                </span>
                <strong className="final-review-readiness__metric-value">
                  {evidenceMissing
                    ? t("finalReviewStates.readinessChecklistLocal")
                        .replace("{count}", String(readiness.checklistCount))
                        .replace("{total}", String(readiness.checklistTotal))
                    : chipValue(chip, readiness, t)}
                </strong>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ReleaseReadinessIcon({ state }: { state: "ready" | "blocked" | "pending" }) {
  if (state === "ready") {
    return (
      <svg viewBox="0 0 24 24">
        <path d="m7.2 12.1 3.1 3.1 6.7-7" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      </svg>
    );
  }
  if (state === "blocked") {
    return (
      <svg viewBox="0 0 24 24">
        <path d="M12 4.3 20 19H4L12 4.3Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
        <path d="M12 9v4.5M12 16.5h.01" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24">
      <circle cx="12" cy="12" fill="none" r="7.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8v4.3l2.8 1.7" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function chipValue(
  chip: FinalReviewReadinessChip,
  readiness: FinalReviewReadiness,
  t: (key: string) => string
): string {
  switch (chip.id) {
    case "checklist":
      return `${readiness.checklistCount}/${readiness.checklistTotal}`;
    case "warnings":
      return readiness.warningCount === 0
        ? t("finalReviewStates.readinessWarningsNone")
        : String(readiness.warningCount);
    case "risk":
      if (!readiness.riskScanned) return t("finalReviewStates.readinessRiskIdle");
      if (!readiness.riskOk) return t("finalReviewStates.readinessRiskBlocked");
      if (readiness.riskNeedsDecision) return t("finalReviewStates.readinessRiskDecision");
      return t("finalReviewStates.readinessRiskOk");
    case "approved":
      return readiness.approved
        ? t("finalReviewStates.readinessApprovedYes")
        : t("finalReviewStates.readinessApprovedNo");
    case "publish_ready":
      return readiness.publishReady
        ? t("finalReviewStates.readinessPublishYes")
        : t("finalReviewStates.readinessPublishNo");
  }
}
