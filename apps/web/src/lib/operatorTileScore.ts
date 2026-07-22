import { getDouyinMetadataCompletenessForItem } from "./captureInboxFilterMetadata";
import { getReupScoreForCaptureItem } from "./captureInboxReupScore";
import { formatReupScoreBadgeValue, reupScoreBadgeLevelForCaptureItem, reupScoreBadgeTier, type ReupScoreBadgeLevel } from "./reupScoreBadge";
import type { CapturedItem } from "../types/capture-inbox";

export type OperatorTileScoreBadge = {
  score: number | null;
  level: ReupScoreBadgeLevel;
  valueLabel: string;
  tierLabel: string;
  title: string;
};

/** Single chokepoint for tile score badges across Capture Inbox, Review Board, and Reup Queue. */
export function getOperatorTileScoreBadge(item: CapturedItem): OperatorTileScoreBadge {
  const operatorScore = getReupScoreForCaptureItem(item).reup_score;
  const score = Number.isFinite(operatorScore) ? operatorScore : null;
  const level = reupScoreBadgeLevelForCaptureItem(score, getDouyinMetadataCompletenessForItem(item));
  const valueLabel = formatReupScoreBadgeValue(score);
  const tierLabel = reupScoreBadgeTier(score);
  return {
    score,
    level,
    valueLabel,
    tierLabel,
    title: score === null ? "Needs metadata before scoring" : `Operator Reup Score ${valueLabel}${tierLabel ? ` · ${tierLabel}` : ""}`
  };
}
