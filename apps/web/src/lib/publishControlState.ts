import type { AccountHealthSummary, PublishQueueItem } from "../types/publish-control";

export function healthTone(health: AccountHealthSummary["health_status"]): "good" | "warn" | "danger" | "muted" {
  if (health === "HEALTHY") return "good";
  if (health === "DEGRADED") return "warn";
  if (health === "UNHEALTHY") return "danger";
  return "muted";
}

export function queueAttentionCount(items: PublishQueueItem[]): number {
  return items.filter((item) => item.warnings.length > 0 || item.assignment_status === "OVERRIDDEN").length;
}

export function defaultAssignmentReason(item: PublishQueueItem): string {
  if (item.recommendation_reasons.length > 0) {
    return item.recommendation_reasons[0];
  }
  return item.recommended_account_name ? `Recommended account: ${item.recommended_account_name}` : "Manual routing";
}

