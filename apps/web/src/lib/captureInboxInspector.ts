import {
  resolveCommentCount,
  resolveDuration,
  resolveMediaAssetStatus,
  resolvePosted,
  resolvePreviewStatus,
  resolveShareCount,
  resolveSourceLinkStatus,
  resolveViewCount
} from "./captureInboxCanonical";
import { getDouyinMetadataCompletenessForItem } from "./captureInboxFilterMetadata";
import type { CapturedItem } from "../types/capture-inbox";

export function itemNeedsInspectorHydration(item: CapturedItem): boolean {
  return item.raw_payload_json === undefined;
}

export function formatInspectorSourceLabel(value: string | null | undefined): string {
  if (!value) return "Not captured";
  if (value === "dom_zero_sentinel") return "DOM zero sentinel";
  return value.replaceAll("_", " ");
}

export function formatMetadataGroupStatus(status: string | null | undefined): string {
  if (status === "captured") return "Captured";
  if (status === "missing") return "Missing";
  if (status === "failed") return "Failed";
  if (status === "pending") return "Pending";
  return "Not captured";
}

function metadataGroupStatusWithReason(
  status: string | null | undefined,
  reason: string | null,
  derivedStatus?: string | null
): string {
  const label = formatMetadataGroupStatus(derivedStatus ?? status);
  return reason ? `${label} — ${reason}` : label;
}

function inspectorSourceLabel(recorded: string | null | undefined, captured: boolean): string {
  if (recorded) return formatInspectorSourceLabel(recorded);
  if (captured) return "Captured (source not recorded)";
  return "Not captured";
}

function formatMetadataStatusLabel(status: CapturedItem["metadata_status"]): string {
  if (!status) return "Unknown";
  return status.replaceAll("_", " ");
}

function formatCoreMetadataComplete(item: CapturedItem): string {
  const computed = getDouyinMetadataCompletenessForItem(item);
  if (computed.hasAllCoreMetadata) return "Yes";
  if (computed.missingFields.length) return `No (${computed.missingFields.join(", ")})`;
  if (item.has_all_core_metadata === false) return "No";
  if (item.has_all_core_metadata === true) return "Yes";
  return "Unknown";
}

function formatMissingFields(item: CapturedItem): string {
  const computed = getDouyinMetadataCompletenessForItem(item);
  if (computed.missingFields.length) return computed.missingFields.join(", ");
  if (item.missing_metadata_fields?.length) return item.missing_metadata_fields.join(", ");
  return "None";
}

function deriveTimeGroupStatus(item: CapturedItem): string | null {
  if (item.time_status && item.time_status !== "pending") return item.time_status;
  const completeness = getDouyinMetadataCompletenessForItem(item);
  if (completeness.hasPosted && completeness.hasDuration) return "captured";
  if (completeness.hasPosted || completeness.hasDuration) return "missing";
  return null;
}

function derivePerformanceGroupStatus(item: CapturedItem): string | null {
  if (item.performance_status && item.performance_status !== "pending") return item.performance_status;
  const completeness = getDouyinMetadataCompletenessForItem(item);
  if (completeness.hasEstimatedViews && completeness.hasCoreMetrics) return "captured";
  if (completeness.hasLikes || completeness.hasComments || completeness.hasShares || completeness.hasEstimatedViews) {
    return "missing";
  }
  return null;
}

function deriveProcessingFitGroupStatus(item: CapturedItem): string | null {
  if (item.processing_fit_status && item.processing_fit_status !== "pending") return item.processing_fit_status;
  const hasSignals =
    item.has_speech !== null && item.has_speech !== undefined
    || item.text_density != null
    || item.has_heavy_watermark !== null && item.has_heavy_watermark !== undefined
    || item.processing_complexity != null
    || item.copyright_risk != null;
  return hasSignals ? "captured" : null;
}

function formatTriStateBoolean(value: boolean | null | undefined): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "Unknown";
}

function formatSemanticLevel(value: "low" | "medium" | "high" | "blocking" | "true" | null | undefined): string {
  return value ?? "Unknown";
}

function formatReasons(value: unknown[] | null): string {
  if (!value?.length) return "Not analyzed yet";
  return value.map((entry) => String(entry)).join(", ");
}

function formatRawEvidenceSummary(value: CapturedItem["raw_evidence_summary"]): string {
  if (!value) return "No evidence summary captured.";
  const tokens: string[] = [];
  if (value.has_network_aweme) tokens.push("network aweme");
  if (value.has_detail_aweme) tokens.push("detail aweme");
  if (value.has_dom_snapshot) tokens.push("dom snapshot");
  return tokens.length ? tokens.join(", ") : "No evidence flags set.";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Not captured";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatCount(value: number | null | undefined): string {
  return typeof value === "number" ? value.toLocaleString() : "Not captured";
}

function formatEngagementRate(value: number | null | undefined, basis: CapturedItem["engagement_rate_basis"]): string {
  if (typeof value !== "number") return "Not captured";
  const basisLabel = basis && basis !== "none" ? ` (${basis.replaceAll("_", " ")})` : "";
  return `${(value * 100).toFixed(2)}%${basisLabel}`;
}

export function inspectorPerformanceItems(item: CapturedItem): Array<{ label: string; value: string }> {
  return [
    { label: "Favorites", value: formatCount(item.favorite_count) },
    { label: "Favorite text", value: item.favorite_count_text?.trim() || "Not captured" },
    { label: "Engagement score", value: formatCount(item.engagement_score) },
    { label: "Engagement rate", value: formatEngagementRate(item.engagement_rate, item.engagement_rate_basis) },
    { label: "Like text", value: item.like_count_text?.trim() || "Not captured" },
    { label: "Comment text", value: item.comment_count_text?.trim() || "Not captured" },
    { label: "Share text", value: item.share_count_text?.trim() || "Not captured" },
    { label: "Views text", value: item.view_count_text?.trim() || item.estimated_views_display?.trim() || "Not captured" },
    { label: "Duration text", value: item.duration_text?.trim() || item.duration_text_raw?.trim() || "Not captured" },
    { label: "Posted text", value: item.posted_display?.trim() || item.posted_text?.trim() || item.posted_text_raw?.trim() || "Not captured" }
  ];
}

export function inspectorMetadataQualityItems(item: CapturedItem): Array<{ label: string; value: string }> {
  const completeness = getDouyinMetadataCompletenessForItem(item);
  const hasDuration = completeness.hasDuration;
  const hasPosted = completeness.hasPosted;
  const hasViews = completeness.hasEstimatedViews || resolveViewCount(item) !== "Not captured";
  const hasLikes = completeness.hasLikes;
  const hasComments = completeness.hasComments;
  const hasShares = completeness.hasShares;
  const hasEngagement = typeof item.engagement_rate === "number" || typeof item.engagement_score === "number";

  return [
    { label: "Metadata status", value: formatMetadataStatusLabel(item.metadata_status) },
    { label: "Missing fields", value: formatMissingFields(item) },
    { label: "Core metadata complete", value: formatCoreMetadataComplete(item) },
    {
      label: "Time status",
      value: metadataGroupStatusWithReason(item.time_status, item.time_missing_reason ?? null, deriveTimeGroupStatus(item))
    },
    {
      label: "Performance status",
      value: metadataGroupStatusWithReason(
        item.performance_status,
        item.performance_missing_reason ?? null,
        derivePerformanceGroupStatus(item)
      )
    },
    {
      label: "Processing fit status",
      value: metadataGroupStatusWithReason(
        item.processing_fit_status,
        item.processing_fit_missing_reason ?? null,
        deriveProcessingFitGroupStatus(item)
      )
    },
    {
      label: "Source summary",
      value: item.metadata_source_summary?.trim()
        || (hasDuration || hasPosted || hasViews || hasLikes ? "Captured from tile metadata" : "No metadata source evidence captured.")
    },
    { label: "Last hydrated", value: formatDateTime(item.last_metadata_hydrated_at) },
    { label: "Preview", value: resolvePreviewStatus(item) },
    { label: "Source link", value: resolveSourceLinkStatus(item) },
    { label: "Media asset", value: resolveMediaAssetStatus(item) },
    { label: "Duration source", value: inspectorSourceLabel(item.duration_source, hasDuration) },
    { label: "Posted source", value: inspectorSourceLabel(item.posted_source, hasPosted) },
    { label: "Views source", value: inspectorSourceLabel(item.view_count_source, hasViews) },
    { label: "Likes source", value: inspectorSourceLabel(item.like_count_source, hasLikes) },
    { label: "Comments source", value: inspectorSourceLabel(item.comment_count_source, hasComments) },
    { label: "Shares source", value: inspectorSourceLabel(item.share_count_source, hasShares) },
    { label: "Engagement source", value: inspectorSourceLabel(item.engagement_rate_source, hasEngagement) },
    { label: "Speech", value: formatTriStateBoolean(item.has_speech) },
    { label: "Text density", value: formatSemanticLevel(item.text_density) },
    { label: "Heavy watermark", value: formatTriStateBoolean(item.has_heavy_watermark) },
    { label: "Processing complexity", value: formatSemanticLevel(item.processing_complexity) },
    { label: "Copyright risk", value: formatSemanticLevel(item.copyright_risk) },
    { label: "Dedupe", value: item.dedupe_key ?? "Not analyzed yet" },
    { label: "Readiness", value: formatReasons(item.readiness_reasons_json) },
    { label: "Raw evidence", value: formatRawEvidenceSummary(item.raw_evidence_summary) },
    { label: "Resolved duration", value: resolveDuration(item) },
    { label: "Resolved posted", value: resolvePosted(item) },
    { label: "Resolved comments", value: resolveCommentCount(item) },
    { label: "Resolved shares", value: resolveShareCount(item) },
    { label: "Item ID", value: item.id }
  ];
}
