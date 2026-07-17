"use client";

import type { Candidate } from "../../types/review-board";

type Props = {
  candidate: Candidate;
  t: (key: string) => string;
};

export function CandidateRiskFlags({ candidate, t }: Props) {
  const warnings = candidate.warnings_json ?? [];
  const hasRisk = warnings.some((warning) => warning.toLowerCase().includes("risk"));
  const hasWatermark = warnings.some((warning) => warning.toLowerCase().includes("watermark"));

  return (
    <div className="signal-row">
      <span className={hasRisk ? "pill danger" : "pill good"}>{hasRisk ? t("reviewBoardPage.riskFlag") : t("reviewBoardPage.riskClear")}</span>
      <span className={hasWatermark ? "pill warn" : "pill good"}>{hasWatermark ? t("reviewBoardPage.watermarkWarning") : t("reviewBoardPage.watermarkOk")}</span>
    </div>
  );
}
