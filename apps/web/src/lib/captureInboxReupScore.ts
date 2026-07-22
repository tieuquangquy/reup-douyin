import { getDouyinItemMetadataForFilters } from "./captureInboxFilterMetadata";
import type { CapturedItem } from "../types/capture-inbox";

export type DouyinReupScoreLabel = "Excellent" | "Good" | "Average" | "Low" | "Needs metadata";
export type DouyinReupScoreLevel = "excellent" | "good" | "average" | "low" | "needs_metadata";

export type DouyinReupScoreComponents = {
  /** Max 20 — sweet-spot views, not raw saturation. */
  performance: number;
  /** Max 20 — (likes + comments) / views; capped at 10 when views < 10K. */
  engagement: number;
  /** Max 20 — (shares×1.5 + favorites×2) / views. */
  virality_retention: number;
  /** Max 10 — ideal reup length 12–75s. */
  duration_fit: number;
  /** Max 20 — fresher posts score higher for trend capture. */
  recency: number;
  /** Max 10 — metadata completeness (unchanged). */
  metadata_quality: number;
  /** -30…0 — status / missing-field penalties (unchanged). */
  penalty: number;
  /** +15 when views/followers > 10 (requires follower_count). */
  outlier_bonus: number;
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
  const likeCount = metadata.likeCount;
  const commentCount = metadata.commentCount;
  const shareCount = metadata.shareCount;
  const favoriteCount = metadata.favoriteCount;
  const followerCount = resolveFollowerCount(item);
  const durationSeconds = metadata.durationSeconds;
  const postedAt = metadata.postedAt;
  const missingFields = metadata.missingMetadataFields;
  const metrics = [likeCount, commentCount, shareCount, favoriteCount];
  const hasAnyMetric = metrics.some((value) => typeof value === "number" && value > 0);

  const components: DouyinReupScoreComponents = {
    performance: scorePerformance(views),
    engagement: scoreEngagement(views, likeCount, commentCount),
    virality_retention: scoreViralityRetention(views, shareCount, favoriteCount),
    duration_fit: scoreDurationFit(durationSeconds),
    recency: scoreRecency(postedAt, now),
    metadata_quality: scoreMetadataQuality(missingFields),
    penalty: scorePenalty(item, metadata.hasThumbnail, metadata.hasDuration, metadata.hasPosted, metadata.hasEstimatedViews, hasAnyMetric),
    outlier_bonus: 0
  };

  const baseScore =
    components.performance +
    components.engagement +
    components.virality_retention +
    components.duration_fit +
    components.recency +
    components.metadata_quality +
    components.penalty;

  const outlierBonus = scoreOutlierBonus(views, followerCount);
  components.outlier_bonus = outlierBonus;

  const severeMissing = missingFields.filter((field) => KEY_METADATA_FIELDS.has(field)).length >= 3;
  const almostNoMetadata = !metadata.hasThumbnail && !metadata.hasDuration && !metadata.hasPosted && !metadata.hasEstimatedViews && !hasAnyMetric;
  const score = almostNoMetadata ? 0 : clampScore(baseScore + outlierBonus);
  const { label, level } = labelForScore(score, severeMissing || almostNoMetadata, missingFields);

  return {
    reup_score: score,
    reup_score_label: label,
    reup_score_level: level,
    reup_score_components: components,
    reup_score_reasons: scoreReasons({
      score,
      views,
      likeCount,
      commentCount,
      shareCount,
      favoriteCount,
      followerCount,
      durationSeconds,
      missingFields,
      label,
      hasEstimatedViews: metadata.hasEstimatedViews,
      hasThumbnail: metadata.hasThumbnail,
      hasPosted: metadata.hasPosted,
      outlierBonus
    })
  };
}

/** Single operator authority: always compute from current metadata (ignore stale persisted reup_score). */
export function getReupScoreForCaptureItem(item: CapturedItem, options: ScoreOptions = {}): DouyinReupScore {
  return calculateDouyinReupScore(item, options);
}

/** Performance (max 20): reward the 100K–3M reup sweet spot; penalize saturation. */
function scorePerformance(views: number | null): number {
  if (views === null || views <= 0) return 0;
  if (views >= 100_000 && views <= 3_000_000) return 20;
  if (views >= 10_000 && views < 100_000) return 15;
  if (views > 3_000_000 && views <= 10_000_000) return 10;
  if (views > 10_000_000) return 5;
  if (views < 10_000) return 2;
  return 0;
}

/** Engagement (max 20): likes + comments only — filters inflated share-driven rates. */
function scoreEngagement(views: number | null, likeCount: number | null, commentCount: number | null): number {
  if (views === null || views <= 0) return 0;
  const rate = ((likeCount ?? 0) + (commentCount ?? 0)) / views;
  let points = 2;
  if (rate >= 0.08) points = 20;
  else if (rate >= 0.05) points = 15;
  else if (rate >= 0.03) points = 10;
  else if (rate >= 0.015) points = 5;
  if (views < 10_000) return Math.min(10, points);
  return points;
}

/** Virality & retention (max 20): shares and saves signal reup potential. */
function scoreViralityRetention(views: number | null, shareCount: number | null, favoriteCount: number | null): number {
  if (views === null || views <= 0) return 0;
  const viralRate = ((shareCount ?? 0) * 1.5 + (favoriteCount ?? 0) * 2.0) / views;
  if (viralRate >= 0.03) return 20;
  if (viralRate >= 0.015) return 15;
  if (viralRate >= 0.005) return 10;
  return 5;
}

/** Duration fit (max 10): short-form reup window. */
function scoreDurationFit(duration: number | null): number {
  if (duration === null) return 0;
  if (duration >= 12 && duration <= 75) return 10;
  if (duration >= 6 && duration <= 120) return 7;
  return 3;
}

/** Recency (max 20): trend freshness. */
function scoreRecency(postedAt: string | null, now: Date): number {
  if (!postedAt) return 0;
  const ageMs = now.getTime() - new Date(postedAt).getTime();
  if (!Number.isFinite(ageMs) || ageMs < 0) return 0;
  const ageHours = ageMs / 3_600_000;
  if (ageHours <= 48) return 20;
  const ageDays = ageHours / 24;
  if (ageDays <= 7) return 15;
  if (ageDays <= 30) return 10;
  return 5;
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

/** Outlier bonus (+15): small account, outsized reach — strong reup signal. */
function scoreOutlierBonus(views: number | null, followerCount: number | null): number {
  if (views === null || views <= 0) return 0;
  if (followerCount === null || followerCount <= 0) return 0;
  return views / followerCount > 10 ? 15 : 0;
}

function resolveFollowerCount(item: CapturedItem): number | null {
  const direct = item.follower_count;
  if (typeof direct === "number" && Number.isFinite(direct) && direct > 0) return direct;
  return readNestedNumber(item.metadata_json, ["follower_count", "author.follower_count", "profile.follower_count"])
    ?? readNestedNumber(item.enrichment_json, ["follower_count", "author.follower_count", "profile.follower_count"]);
}

function readNestedNumber(source: Record<string, unknown> | null | undefined, paths: string[]): number | null {
  if (!source) return null;
  for (const path of paths) {
    const value = readPath(source, path);
    if (typeof value === "number" && Number.isFinite(value) && value > 0) return value;
  }
  return null;
}

function readPath(source: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((current, segment) => {
    if (!current || typeof current !== "object") return undefined;
    return (current as Record<string, unknown>)[segment];
  }, source);
}

function labelForScore(score: number, severeMissing: boolean, missingFields: string[]): { label: DouyinReupScoreLabel; level: DouyinReupScoreLevel } {
  const missingKeyFields = missingFields.some((field) => KEY_METADATA_FIELDS.has(field));
  if (score === 0 || severeMissing || (missingKeyFields && score < 40)) return { label: "Needs metadata", level: "needs_metadata" };
  if (score >= 80) return { label: "Excellent", level: "excellent" };
  if (score >= 60) return { label: "Good", level: "good" };
  if (score >= 40) return { label: "Average", level: "average" };
  return { label: "Low", level: "low" };
}

function scoreReasons(args: {
  score: number;
  views: number | null;
  likeCount: number | null;
  commentCount: number | null;
  shareCount: number | null;
  favoriteCount: number | null;
  followerCount: number | null;
  durationSeconds: number | null;
  missingFields: string[];
  label: DouyinReupScoreLabel;
  hasEstimatedViews: boolean;
  hasThumbnail: boolean;
  hasPosted: boolean;
  outlierBonus: number;
}): string[] {
  const reasons: string[] = [];
  const engagementRate =
    args.views && args.views > 0 ? ((args.likeCount ?? 0) + (args.commentCount ?? 0)) / args.views : null;

  if (args.label === "Needs metadata") reasons.push("Needs metadata");
  if (args.views !== null && args.views >= 100_000 && args.views <= 3_000_000) reasons.push("Sweet-spot view range");
  if (args.views !== null && args.views > 10_000_000) reasons.push("Saturated mega-views");
  if (engagementRate !== null && engagementRate >= 0.03 && (args.views ?? 0) >= 10_000) reasons.push("Good engagement rate");
  if (args.shareCount !== null && args.favoriteCount !== null && args.views && args.views > 0) {
    const viralRate = ((args.shareCount ?? 0) * 1.5 + (args.favoriteCount ?? 0) * 2.0) / args.views;
    if (viralRate >= 0.015) reasons.push("Strong share/save signal");
  }
  if (args.durationSeconds !== null && args.durationSeconds >= 12 && args.durationSeconds <= 75) reasons.push("Duration fits review range");
  if (args.outlierBonus > 0) reasons.push("Outlier reach vs followers");
  if (!args.hasPosted || args.missingFields.includes("posted")) reasons.push("Missing posted date");
  if (!args.hasThumbnail || args.missingFields.includes("thumbnail")) reasons.push("Missing thumbnail");
  if (!args.hasEstimatedViews || args.missingFields.includes("views")) reasons.push("Needs estimated views");
  if (args.followerCount === null && args.views !== null && args.views >= 100_000) reasons.push("Follower count unavailable");
  return Array.from(new Set(reasons)).slice(0, 4);
}

function clampScore(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}
