export type ReupScoreBadgeLevel = "excellent" | "good" | "average" | "low" | "needs_metadata";

export function formatReupScoreBadgeValue(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? Math.round(value).toString() : "Unscored";
}

export function reupScoreBadgeLevel(value: number | null | undefined): ReupScoreBadgeLevel {
  if (value == null || !Number.isFinite(value)) return "needs_metadata";
  if (value >= 80) return "excellent";
  if (value >= 60) return "good";
  if (value >= 40) return "average";
  return "low";
}

export function reupScoreBadgeTier(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "";
  if (value >= 80) return "Excellent";
  if (value >= 60) return "Strong";
  if (value >= 40) return "Medium";
  return "Low";
}

export function reupScoreBadgeLevelForCaptureItem(
  score: number | null | undefined,
  metadata: { hasAllCoreMetadata: boolean }
): ReupScoreBadgeLevel {
  if (typeof score !== "number" || !Number.isFinite(score) || score <= 0 || !metadata.hasAllCoreMetadata) {
    return "needs_metadata";
  }
  return reupScoreBadgeLevel(score);
}
