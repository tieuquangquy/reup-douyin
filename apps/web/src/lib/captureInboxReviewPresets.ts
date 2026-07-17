import { getDouyinItemMetadataForFilters, getDouyinMetadataCompletenessForItem } from "./captureInboxFilterMetadata";
import { getReupScoreForCaptureItem } from "./captureInboxReupScore";
import type { CapturedItem } from "../types/capture-inbox";

export type DouyinReviewPreset =
  | "none"
  | "high_potential"
  | "ready_to_promote"
  | "high_engagement"
  | "high_share"
  | "short_strong"
  | "needs_cleanup"
  | "low_priority";

export type DouyinReviewPresetId = Exclude<DouyinReviewPreset, "none">;
export type DouyinReviewPresetSortHint = "highest_reup_score" | "lowest_reup_score" | "highest_engagement" | "highest_shares" | "recently_captured";

export type DouyinReviewPresetConfig = {
  id: DouyinReviewPresetId;
  label: string;
  shortLabel: string;
  description: string;
  badge: string;
  priority: number;
  sortHint: DouyinReviewPresetSortHint;
  predicate: (item: CapturedItem) => boolean;
};

export const DOUYIN_REVIEW_PRESETS: DouyinReviewPresetConfig[] = [
  {
    id: "high_potential",
    label: "High potential",
    shortLabel: "High potential",
    description: "High score with strong performance signals.",
    badge: "Score",
    priority: 10,
    sortHint: "highest_reup_score",
    predicate: matchesHighPotentialPreset
  },
  {
    id: "ready_to_promote",
    label: "Strict ready to promote",
    shortLabel: "Strict ready",
    description: "Stricter than inbox Ready: complete metadata, review-ready, score ≥ 50, not yet promoted.",
    badge: "Ready",
    priority: 20,
    sortHint: "highest_reup_score",
    predicate: matchesReadyToPromotePreset
  },
  {
    id: "high_engagement",
    label: "High engagement",
    shortLabel: "Engagement",
    description: "Strong engagement rate or interaction score.",
    badge: "ER",
    priority: 30,
    sortHint: "highest_engagement",
    predicate: matchesHighEngagementPreset
  },
  {
    id: "high_share",
    label: "High share",
    shortLabel: "Shares",
    description: "Videos with strong share signal.",
    badge: "Share",
    priority: 40,
    sortHint: "highest_shares",
    predicate: matchesHighSharePreset
  },
  {
    id: "short_strong",
    label: "Short & strong",
    shortLabel: "Short & strong",
    description: "Good score with review-friendly duration.",
    badge: "Short",
    priority: 50,
    sortHint: "highest_reup_score",
    predicate: matchesShortStrongPreset
  },
  {
    id: "needs_cleanup",
    label: "Needs cleanup",
    shortLabel: "Cleanup",
    description: "Missing metadata or needs re-check.",
    badge: "Fix",
    priority: 60,
    sortHint: "recently_captured",
    predicate: matchesNeedsCleanupPreset
  },
  {
    id: "low_priority",
    label: "Low priority",
    shortLabel: "Low priority",
    description: "Low score or weak signals.",
    badge: "Low",
    priority: 70,
    sortHint: "lowest_reup_score",
    predicate: matchesLowPriorityPreset
  }
];

export function getDouyinReviewPresetConfig(preset: DouyinReviewPreset): DouyinReviewPresetConfig | null {
  if (preset === "none") return null;
  return DOUYIN_REVIEW_PRESETS.find((config) => config.id === preset) ?? null;
}

export function matchesDouyinReviewPreset(item: CapturedItem, preset: DouyinReviewPreset): boolean {
  const config = getDouyinReviewPresetConfig(preset);
  return config ? config.predicate(item) : true;
}

export function getDouyinReviewPresetCounts(items: CapturedItem[]): Record<DouyinReviewPresetId, number> {
  const counts = Object.fromEntries(DOUYIN_REVIEW_PRESETS.map((preset) => [preset.id, 0])) as Record<DouyinReviewPresetId, number>;
  for (const item of items) {
    for (const preset of DOUYIN_REVIEW_PRESETS) {
      if (preset.predicate(item)) counts[preset.id] += 1;
    }
  }
  return counts;
}

export function getMatchingDouyinReviewPresets(item: CapturedItem): DouyinReviewPresetConfig[] {
  return DOUYIN_REVIEW_PRESETS.filter((preset) => preset.predicate(item));
}

function matchesHighPotentialPreset(item: CapturedItem): boolean {
  if (isFailedItem(item) || isDuplicateItem(item) || hasSevereMissingMetadata(item)) return false;
  const metadata = getDouyinItemMetadataForFilters(item);
  const score = getReupScoreForCaptureItem(item).reup_score;
  return score >= 70 || (score >= 60 && (metadata.estimatedViewsMid ?? 0) >= 20000 && (metadata.shareCount ?? 0) >= 20);
}

function matchesReadyToPromotePreset(item: CapturedItem): boolean {
  if (!isReviewReadyItem(item) || isDuplicateItem(item) || isFailedItem(item) || isNeedsActionItem(item) || item.status === "PROMOTED") return false;
  const completeness = getDouyinMetadataCompletenessForItem(item);
  return completeness.hasAllCoreMetadata && getReupScoreForCaptureItem(item).reup_score >= 50;
}

function matchesHighEngagementPreset(item: CapturedItem): boolean {
  if (isFailedItem(item)) return false;
  const metadata = getDouyinItemMetadataForFilters(item);
  if (metadata.likeCount === null || metadata.commentCount === null || metadata.shareCount === null) return false;
  return (metadata.engagementRate ?? 0) >= 3 || (metadata.engagementScore ?? 0) >= 1000 || ((metadata.likeCount ?? 0) >= 1000 && (metadata.commentCount ?? 0) >= 50);
}

function matchesHighSharePreset(item: CapturedItem): boolean {
  const metadata = getDouyinItemMetadataForFilters(item);
  const shareCount = metadata.shareCount ?? 0;
  const score = getReupScoreForCaptureItem(item).reup_score;
  return shareCount >= 50 || (shareCount >= 20 && score >= 60);
}

function matchesShortStrongPreset(item: CapturedItem): boolean {
  if (isFailedItem(item)) return false;
  const metadata = getDouyinItemMetadataForFilters(item);
  const duration = metadata.durationSeconds;
  if (duration === null) return false;
  const score = getReupScoreForCaptureItem(item).reup_score;
  return (duration >= 30 && duration <= 900 && score >= 55) || (duration >= 30 && duration <= 1200 && (metadata.shareCount ?? 0) >= 20 && (metadata.likeCount ?? 0) >= 500);
}

function matchesNeedsCleanupPreset(item: CapturedItem): boolean {
  const metadata = getDouyinItemMetadataForFilters(item);
  const completeness = getDouyinMetadataCompletenessForItem(item, metadata.comparableViews);
  const metadataStatus = item.metadata_status;
  return metadataStatus === "partial" || metadataStatus === "missing" || metadataStatus === "failed" ||
    completeness.missingFields.length > 0 ||
    !completeness.hasAllCoreMetadata ||
    !completeness.hasThumbnail ||
    !completeness.hasPosted ||
    !completeness.hasDuration ||
    !completeness.hasEstimatedViews ||
    !completeness.hasLikes ||
    !completeness.hasComments ||
    !completeness.hasShares ||
    item.intake_evaluation_status === "MISSING_REQUIREMENTS" ||
    item.status === "NEEDS_ENRICHMENT" ||
    item.status === "PREVIEW_MISSING" ||
    item.status === "FAILED";
}

function matchesLowPriorityPreset(item: CapturedItem): boolean {
  const metadata = getDouyinItemMetadataForFilters(item);
  const score = getReupScoreForCaptureItem(item).reup_score;
  return score < 40 || ((metadata.estimatedViewsMid ?? Number.POSITIVE_INFINITY) < 5000 && (metadata.engagementScore ?? Number.POSITIVE_INFINITY) < 200) || ((metadata.likeCount ?? Number.POSITIVE_INFINITY) < 100 && (metadata.shareCount ?? Number.POSITIVE_INFINITY) < 5);
}

function isReviewReadyItem(item: CapturedItem): boolean {
  return item.status === "READY" || item.status === "ENRICHED";
}

function isDuplicateItem(item: CapturedItem): boolean {
  return item.status === "DUPLICATE" || Boolean(item.duplicate_of_item_id);
}

function isFailedItem(item: CapturedItem): boolean {
  return item.status === "FAILED" || item.intake_evaluation_status === "FILTERED_OUT" || item.intake_evaluation_status === "EVALUATION_ERROR" || item.matches_intake === false;
}

function isNeedsActionItem(item: CapturedItem): boolean {
  return item.intake_evaluation_status === "MISSING_REQUIREMENTS" || item.status === "RAW" || item.status === "NEEDS_ENRICHMENT" || item.status === "PREVIEW_MISSING";
}

function hasSevereMissingMetadata(item: CapturedItem): boolean {
  const completeness = getDouyinMetadataCompletenessForItem(item);
  return !completeness.hasThumbnail || !completeness.hasPosted || !completeness.hasDuration || !completeness.hasEstimatedViews || !completeness.hasCoreMetrics;
}
