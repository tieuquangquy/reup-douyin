"use client";

import { formatExactEngagementMetric } from "../../lib/captureInboxCanonical";
import type { Candidate } from "../../types/review-board";

type Props = {
  candidate: Candidate;
  t: (key: string) => string;
};

export function CandidateMetricsRow({ candidate, t }: Props) {
  const metrics = candidate.score_breakdown_json?.engagement_quality?.raw_input ?? {};
  return (
    <div className="metrics-row">
      <span className="pill">{t("reviewBoardPage.metricViews")} {formatViews(numberValue(metrics.views))}</span>
      <span className="pill">{t("reviewBoardPage.metricLikes")} {formatExactEngagementMetric(numberValue(metrics.likes), null, "--")}</span>
      <span className="pill">{t("reviewBoardPage.metricComments")} {formatExactEngagementMetric(numberValue(metrics.comments), null, "--")}</span>
      <span className="pill">{t("reviewBoardPage.metricShares")} {formatExactEngagementMetric(numberValue(metrics.shares), null, "--")}</span>
    </div>
  );
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function formatViews(value: number | null): string {
  if (value == null) return "--";
  return new Intl.NumberFormat("en", { notation: value >= 10000 ? "compact" : "standard" }).format(value);
}
