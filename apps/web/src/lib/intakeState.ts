import type { IntakeDiscoverRequest, IntakeFormValues, IntakeValidationErrors, RecentIntakeSetup } from "../types/intake";

export const DEFAULT_INTAKE_FORM: IntakeFormValues = {
  profileUrl: "",
  dateFrom: "",
  dateTo: "",
  minViews: "10000",
  maxViews: "",
  minLikes: "500",
  maxLikes: "",
  minComments: "",
  maxComments: "",
  minShares: "",
  maxShares: "",
  minDurationSeconds: "",
  maxDurationSeconds: "",
  minEngagementRate: "",
  maxEngagementRate: "",
  hasSpeech: "any",
  maxTextDensity: "",
  excludeHeavyWatermark: true,
  excludeHighProcessingComplexity: true,
  excludeHighCopyrightRisk: true,
  forceLiveRefresh: false,
  douyinAccountConnectionId: "",
  presetName: "viral_discovery"
};

export function validateIntakeForm(values: IntakeFormValues): IntakeValidationErrors {
  const errors: IntakeValidationErrors = {};

  if (!values.profileUrl.trim()) {
    errors.profileUrl = "Profile URL is required.";
  } else if (!isValidDouyinProfileUrl(values.profileUrl)) {
    errors.profileUrl = "Enter a valid Douyin profile URL.";
  }

  const minViews = parseOptionalInteger(values.minViews);
  const maxViews = parseOptionalInteger(values.maxViews);
  const minLikes = parseOptionalInteger(values.minLikes);
  const maxLikes = parseOptionalInteger(values.maxLikes);
  const minComments = parseOptionalInteger(values.minComments);
  const maxComments = parseOptionalInteger(values.maxComments);
  const minShares = parseOptionalInteger(values.minShares);
  const maxShares = parseOptionalInteger(values.maxShares);
  const minDuration = parseOptionalNumber(values.minDurationSeconds);
  const maxDuration = parseOptionalNumber(values.maxDurationSeconds);
  const minEngagementRate = parseOptionalNumber(values.minEngagementRate);
  const maxEngagementRate = parseOptionalNumber(values.maxEngagementRate);

  if (minViews === "invalid") errors.minViews = "Min views must be a non-negative whole number.";
  if (maxViews === "invalid") errors.maxViews = "Max views must be a non-negative whole number.";
  if (minLikes === "invalid") errors.minLikes = "Min likes must be a non-negative whole number.";
  if (maxLikes === "invalid") errors.maxLikes = "Max likes must be a non-negative whole number.";
  if (minComments === "invalid") errors.minComments = "Min comments must be a non-negative whole number.";
  if (maxComments === "invalid") errors.maxComments = "Max comments must be a non-negative whole number.";
  if (minShares === "invalid") errors.minShares = "Min shares must be a non-negative whole number.";
  if (maxShares === "invalid") errors.maxShares = "Max shares must be a non-negative whole number.";
  if (minDuration === "invalid") errors.minDurationSeconds = "Min duration must be a non-negative number of seconds.";
  if (maxDuration === "invalid") errors.maxDurationSeconds = "Max duration must be a non-negative number of seconds.";
  if (minEngagementRate === "invalid") errors.minEngagementRate = "Min engagement rate must be a percentage from 0 to 100.";
  if (maxEngagementRate === "invalid") errors.maxEngagementRate = "Max engagement rate must be a percentage from 0 to 100.";

  if (typeof minViews === "number" && typeof maxViews === "number" && minViews > maxViews) {
    errors.maxViews = "Max views must be greater than or equal to min views.";
  }
  if (typeof minLikes === "number" && typeof maxLikes === "number" && minLikes > maxLikes) {
    errors.maxLikes = "Max likes must be greater than or equal to min likes.";
  }
  if (typeof minComments === "number" && typeof maxComments === "number" && minComments > maxComments) {
    errors.maxComments = "Max comments must be greater than or equal to min comments.";
  }
  if (typeof minShares === "number" && typeof maxShares === "number" && minShares > maxShares) {
    errors.maxShares = "Max shares must be greater than or equal to min shares.";
  }
  if (typeof minDuration === "number" && typeof maxDuration === "number" && minDuration > maxDuration) {
    errors.maxDurationSeconds = "Max duration must be greater than or equal to min duration.";
  }
  if (typeof minEngagementRate === "number" && typeof maxEngagementRate === "number" && minEngagementRate > maxEngagementRate) {
    errors.maxEngagementRate = "Max engagement rate must be greater than or equal to min engagement rate.";
  }
  if (typeof minEngagementRate === "number" && minEngagementRate > 100) {
    errors.minEngagementRate = "Min engagement rate must be a percentage from 0 to 100.";
  }
  if (typeof maxEngagementRate === "number" && maxEngagementRate > 100) {
    errors.maxEngagementRate = "Max engagement rate must be a percentage from 0 to 100.";
  }
  if (values.dateFrom && values.dateTo && values.dateFrom > values.dateTo) {
    errors.dateTo = "To date must be after from date.";
  }

  return errors;
}

export function buildIntakeDiscoverRequest(values: IntakeFormValues): IntakeDiscoverRequest {
  const filterConfig: IntakeDiscoverRequest["filter_config"] = {
    sort: "score_desc",
    limit: 50,
    offset: 0
  };

  if (values.dateFrom || values.dateTo) {
    filterConfig.date_mode = "absolute_range";
    if (values.dateFrom) filterConfig.start_date = startOfDayIso(values.dateFrom);
    if (values.dateTo) filterConfig.end_date = endOfDayIso(values.dateTo);
  }

  const minViews = parseOptionalInteger(values.minViews);
  const maxViews = parseOptionalInteger(values.maxViews);
  const minLikes = parseOptionalInteger(values.minLikes);
  const maxLikes = parseOptionalInteger(values.maxLikes);
  const minComments = parseOptionalInteger(values.minComments);
  const maxComments = parseOptionalInteger(values.maxComments);
  const minShares = parseOptionalInteger(values.minShares);
  const maxShares = parseOptionalInteger(values.maxShares);
  const minDuration = parseOptionalNumber(values.minDurationSeconds);
  const maxDuration = parseOptionalNumber(values.maxDurationSeconds);
  const minEngagementRate = parseOptionalNumber(values.minEngagementRate);
  const maxEngagementRate = parseOptionalNumber(values.maxEngagementRate);

  if (typeof minViews === "number") filterConfig.min_views = minViews;
  if (typeof maxViews === "number") filterConfig.max_views = maxViews;
  if (typeof minLikes === "number") filterConfig.min_likes = minLikes;
  if (typeof maxLikes === "number") filterConfig.max_likes = maxLikes;
  if (typeof minComments === "number") filterConfig.min_comments = minComments;
  if (typeof maxComments === "number") filterConfig.max_comments = maxComments;
  if (typeof minShares === "number") filterConfig.min_shares = minShares;
  if (typeof maxShares === "number") filterConfig.max_shares = maxShares;
  if (typeof minDuration === "number") filterConfig.min_duration_seconds = minDuration;
  if (typeof maxDuration === "number") filterConfig.max_duration_seconds = maxDuration;
  if (typeof minEngagementRate === "number") filterConfig.min_engagement_rate = percentToRatio(minEngagementRate);
  if (typeof maxEngagementRate === "number") filterConfig.max_engagement_rate = percentToRatio(maxEngagementRate);
  if (values.hasSpeech === "yes") filterConfig.has_speech = true;
  if (values.hasSpeech === "no") filterConfig.has_speech = false;
  if (values.maxTextDensity) filterConfig.max_text_density = values.maxTextDensity;
  filterConfig.exclude_heavy_watermark = values.excludeHeavyWatermark;
  filterConfig.exclude_high_processing_complexity = values.excludeHighProcessingComplexity;
  filterConfig.exclude_high_copyright_risk = values.excludeHighCopyrightRisk;

  return {
    profile_url: values.profileUrl.trim(),
    preset_name: values.presetName || null,
    filter_config: filterConfig,
    persist: true,
    force_live_refresh: values.forceLiveRefresh,
    douyin_account_connection_id: values.douyinAccountConnectionId || null
  };
}

export function hasIntakeErrors(errors: IntakeValidationErrors): boolean {
  return Object.keys(errors).length > 0;
}

export function isValidDouyinProfileUrl(value: string): boolean {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    return ["http:", "https:"].includes(url.protocol) && (host.includes("douyin.com") || host.includes("iesdouyin.com"));
  } catch {
    return false;
  }
}

export function formatPresetName(value: string): string {
  if (!value) return "No preset";
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function parseRecentIntakeSetup(value: string | null): RecentIntakeSetup | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Partial<RecentIntakeSetup>;
    if (!parsed.profileUrl || !parsed.discoveredAt) return null;
    return {
      profileUrl: parsed.profileUrl,
      presetName: parsed.presetName ?? "",
      discoveredAt: parsed.discoveredAt
    };
  } catch {
    return null;
  }
}

function parseOptionalInteger(value: string): number | "invalid" | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/^\d+$/.test(trimmed)) return "invalid";
  return Number(trimmed);
}

function parseOptionalNumber(value: string): number | "invalid" | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0) return "invalid";
  return parsed;
}

function percentToRatio(value: number): number {
  return Number((value / 100).toFixed(6));
}

function startOfDayIso(value: string): string {
  return new Date(`${value}T00:00:00.000Z`).toISOString();
}

function endOfDayIso(value: string): string {
  return new Date(`${value}T23:59:59.999Z`).toISOString();
}
