import { getDouyinItemMetadataForFilters } from "./captureInboxFilterMetadata";
import type { CapturedItem } from "../types/capture-inbox";

export type DouyinReupScoreLabel = "Excellent" | "Good" | "Average" | "Low" | "Needs metadata";
export type DouyinReupScoreLevel = "excellent" | "good" | "average" | "low" | "needs_metadata";

export type DouyinReupScoreComponents = {
  performance: number;
  engagement: number;
  shareability: number;
  duration_fit: number;
  recency: number;
  metadata_quality: number;
  penalty: number;
};

export type DouyinReupScore = {
  reup_score: number;
  reup_score_label: DouyinReupScoreLabel;
  reup_score_level: DouyinReupScoreLevel;
  reup_score_components: DouyinReupScoreComponents;
  reup_score_reasons: string[];
};

type ScoreOptions = {
  now?: Date;
};

const KEY_METADATA_FIELDS = new Set(["thumbnail", "duration", "posted", "views"]);

export function calculateDouyinReupScore(item: CapturedItem, options: ScoreOptions = {}): DouyinReupScore {
  const metadata = getDouyinItemMetadataForFilters(item);
  const now = options.now ?? new Date();
  const views = metadata.estimatedViewsMid;
  const engagementRate = metadata.engagementRate;
  const engagementScore = metadata.engagementScore;
  const shareCount = metadata.shareCount;
  const durationSeconds = metadata.durationSeconds;
  const postedAt = metadata.postedAt;
  const missingFields = metadata.missingMetadataFields;
  const metrics = [metadata.likeCount, metadata.commentCount, metadata.shareCount, metadata.favoriteCount];
  const hasAnyMetric = metrics.some((value) => typeof value === "number" && value > 0);

  const components: DouyinReupScoreComponents = {
    performance: scorePerformance(views),
    engagement: scoreEngagement(engagementRate, engagementScore),
    shareability: scoreShareability(shareCount),
    duration_fit: scoreDurationFit(durationSeconds),
    recency: scoreRecency(postedAt, now),
    metadata_quality: scoreMetadataQuality(missingFields),
    penalty: scorePenalty(item, metadata.hasThumbnail, metadata.hasDuration, metadata.hasPosted, metadata.hasEstimatedViews, hasAnyMetric)
  };

  const rawScore = components.performance + components.engagement + components.shareability + components.duration_fit + components.recency + components.metadata_quality + components.penalty;
  const severeMissing = missingFields.filter((field) => KEY_METADATA_FIELDS.has(field)).length >= 3;
  const almostNoMetadata = !metadata.hasThumbnail && !metadata.hasDuration && !metadata.hasPosted && !metadata.hasEstimatedViews && !hasAnyMetric;
  const score = almostNoMetadata ? 0 : clampScore(rawScore);
  const { label, level } = labelForScore(score, severeMissing || almostNoMetadata, missingFields);

  return {
    reup_score: score,
    reup_score_label: label,
    reup_score_level: level,
    reup_score_components: components,
    reup_score_reasons: scoreReasons({
      score,
      views,
      engagementRate,
      shareCount,
      durationSeconds,
      missingFields,
      label,
      hasEstimatedViews: metadata.hasEstimatedViews,
      hasThumbnail: metadata.hasThumbnail,
      hasPosted: metadata.hasPosted
    })
  };
}

export function getReupScoreForCaptureItem(item: CapturedItem, options: ScoreOptions = {}): DouyinReupScore {
  return calculateDouyinReupScore(item, options);
}

function scorePerformance(views: number | null): number {
  if (views === null) return 0;
  if (views >= 500000) return 25;
  if (views >= 100000) return 22;
  if (views >= 50000) return 18;
  if (views >= 10000) return 14;
  if (views >= 3000) return 9;
  return 5;
}

function scoreEngagement(rate: number | null, score: number | null): number {
  if (rate !== null) {
    if (rate >= 0.08) return 25;
    if (rate >= 0.05) return 21;
    if (rate >= 0.03) return 17;
    if (rate >= 0.015) return 12;
    if (rate > 0) return 7;
  }
  if (score !== null && score > 0) return Math.min(12, Math.max(4, Math.round(Math.log10(score + 1) * 4)));
  return 0;
}

function scoreShareability(shares: number | null): number {
  if (shares === null) return 0;
  if (shares >= 5000) return 15;
  if (shares >= 1000) return 13;
  if (shares >= 250) return 10;
  if (shares >= 50) return 7;
  if (shares > 0) return 4;
  return 1;
}

function scoreDurationFit(duration: number | null): number {
  if (duration === null) return 0;
  if (duration >= 12 && duration <= 75) return 15;
  if (duration >= 6 && duration <= 120) return 11;
  if (duration >= 3 && duration <= 180) return 7;
  return 3;
}

function scoreRecency(postedAt: string | null, now: Date): number {
  if (!postedAt) return 0;
  const ageDays = Math.max(0, (now.getTime() - new Date(postedAt).getTime()) / 86400000);
  if (!Number.isFinite(ageDays)) return 0;
  if (ageDays <= 7) return 10;
  if (ageDays <= 30) return 8;
  if (ageDays <= 90) return 6;
  if (ageDays <= 180) return 4;
  return 2;
}

function scoreMetadataQuality(missingFields: string[]): number {
  return Math.max(0, 10 - missingFields.length * 2);
}

function scorePenalty(item: CapturedItem, hasThumbnail: boolean, hasDuration: boolean, hasPosted: boolean, hasEstimatedViews: boolean, hasAnyMetric: boolean): number {
  let penalty = 0;
  if (!hasThumbnail) penalty -= 8;
  if (!hasDuration) penalty -= 5;
  if (!hasPosted) penalty -= 4;
  if (!hasAnyMetric) penalty -= 10;
  if (item.status === "DUPLICATE" || item.duplicate_of_item_id || item.existing_source_video_id) penalty -= 20;
  if (item.status === "FAILED") penalty -= 20;
  if (item.metadata_status === "failed") penalty -= 20;
  if (item.status === "RAW" || item.status === "NEEDS_ENRICHMENT" || item.status === "PREVIEW_MISSING") penalty -= 8;
  if (!hasEstimatedViews) penalty -= 5;
  return Math.max(-30, penalty);
}

function labelForScore(score: number, severeMissing: boolean, missingFields: string[]): { label: DouyinReupScoreLabel; level: DouyinReupScoreLevel } {
  const missingKeyFields = missingFields.some((field) => KEY_METADATA_FIELDS.has(field));
  if (score === 0 || severeMissing || (missingKeyFields && score < 40)) return { label: "Needs metadata", level: "needs_metadata" };
  if (score >= 80) return { label: "Excellent", level: "excellent" };
  if (score >= 60) return { label: "Good", level: "good" };
  if (score >= 40) return { label: "Average", level: "average" };
  return { label: "Low", level: "low" };
}

function scoreReasons(args: { score: number; views: number | null; engagementRate: number | null; shareCount: number | null; durationSeconds: number | null; missingFields: string[]; label: DouyinReupScoreLabel; hasEstimatedViews: boolean; hasThumbnail: boolean; hasPosted: boolean }): string[] {
  const reasons: string[] = [];
  if (args.label === "Needs metadata") reasons.push("Needs metadata");
  if (args.views !== null && args.views >= 50000) reasons.push("Strong estimated views");
  if (args.engagementRate !== null && args.engagementRate >= 0.03) reasons.push("Good engagement rate");
  if (args.shareCount !== null && args.shareCount >= 50) reasons.push("High share count");
  if (args.durationSeconds !== null && args.durationSeconds >= 12 && args.durationSeconds <= 75) reasons.push("Duration fits review range");
  if (!args.hasPosted || args.missingFields.includes("posted")) reasons.push("Missing posted date");
  if (!args.hasThumbnail || args.missingFields.includes("thumbnail")) reasons.push("Missing thumbnail");
  if (!args.hasEstimatedViews || args.missingFields.includes("views")) reasons.push("Needs estimated views");
  if (args.shareCount !== null && args.shareCount < 10) reasons.push("Low share count");
  return Array.from(new Set(reasons)).slice(0, 4);
}

function clampScore(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}
