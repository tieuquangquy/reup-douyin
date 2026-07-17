"use client";

import type { ScoreBreakdown } from "../../types/review-board";

const COMPONENT_KEYS = [
  "engagement_quality",
  "freshness",
  "views_normalized",
  "like_rate",
  "comment_share_quality",
  "duration_fit",
  "speech_bonus",
  "text_complexity_penalty",
  "watermark_penalty",
  "copyright_risk_penalty"
] as const;

type Props = {
  breakdown: ScoreBreakdown | null;
  t: (key: string) => string;
};

export function ScoreBreakdownPanel({ breakdown, t }: Props) {
  if (!breakdown) {
    return <p className="card-meta">{t("reviewBoardPage.noScoreBreakdown")}</p>;
  }

  const labels: Record<string, string> = {
    engagement_quality: t("reviewBoardPage.engagement"),
    freshness: t("reviewBoardPage.freshness"),
    views_normalized: t("reviewBoardPage.metricViews"),
    like_rate: t("reviewBoardPage.likeRate"),
    comment_share_quality: t("reviewBoardPage.commentsShares"),
    duration_fit: t("reviewBoardPage.durationFit"),
    speech_bonus: t("reviewBoardPage.speech"),
    text_complexity_penalty: t("reviewBoardPage.textComplexity"),
    watermark_penalty: t("reviewBoardPage.watermarkWarning"),
    copyright_risk_penalty: t("reviewBoardPage.copyrightRisk")
  };

  return (
    <div className="breakdown">
      {COMPONENT_KEYS.map((key) => {
        const component = breakdown[key];
        if (!component) return null;
        return (
          <div className="breakdown-row" key={key}>
            <span>{labels[key]}</span>
            <div className="bar">
              <span style={{ width: `${Math.max(0, Math.min(100, component.normalized_subscore))}%` }} />
            </div>
            <strong>{component.weighted_contribution.toFixed(1)}</strong>
          </div>
        );
      })}
    </div>
  );
}
