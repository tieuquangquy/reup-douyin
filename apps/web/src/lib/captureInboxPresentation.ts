import { type DouyinReupScore, type DouyinReupScoreComponents } from "./captureInboxReupScore";
import type { CapturedItem } from "../types/capture-inbox";
export type ReupScoreBreakdownBar = {
  key: keyof DouyinReupScoreComponents | "penalty";
  label: string;
  value: number;
  max: number;
  tone: "positive" | "penalty";
};

const REUP_SCORE_BAR_MAX: Record<Exclude<keyof DouyinReupScoreComponents, "penalty">, number> = {
  performance: 25,
  engagement: 25,
  shareability: 15,
  duration_fit: 15,
  recency: 10,
  metadata_quality: 10
};

const REUP_SCORE_BAR_LABELS: Record<Exclude<keyof DouyinReupScoreComponents, "penalty">, string> = {
  performance: "Performance",
  engagement: "Engagement",
  shareability: "Shareability",
  duration_fit: "Duration fit",
  recency: "Recency",
  metadata_quality: "Metadata"
};

export function shouldShowCaptureInboxTileMetrics(_item: CapturedItem): boolean {
  // Always show engagement metrics on tiles — hiding them for high-score Ready cards
  // made complete-looking videos appear metadata-empty after hybrid collect.
  return true;
}

export function buildReupScoreBreakdownBars(score: DouyinReupScore): ReupScoreBreakdownBar[] {
  const bars: ReupScoreBreakdownBar[] = (Object.keys(REUP_SCORE_BAR_MAX) as Array<Exclude<keyof DouyinReupScoreComponents, "penalty">>).map((key) => ({
    key,
    label: REUP_SCORE_BAR_LABELS[key],
    value: Math.max(0, score.reup_score_components[key]),
    max: REUP_SCORE_BAR_MAX[key],
    tone: "positive"
  }));

  if (score.reup_score_components.penalty < 0) {
    bars.push({
      key: "penalty",
      label: "Penalty",
      value: Math.abs(score.reup_score_components.penalty),
      max: 30,
      tone: "penalty"
    });
  }

  return bars;
}
