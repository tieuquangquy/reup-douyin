const STATUS_LABELS: Record<string, string> = {
  ACKNOWLEDGED: "Acknowledged",
  ACTIVE: "Active",
  APPROVED: "Approved",
  AWAITING_PLATFORM_CONFIRMATION: "Awaiting platform confirmation",
  BLOCKING: "Blocking",
  CANCELLED: "Cancelled",
  COMPLETED: "Completed",
  CRITICAL: "Critical",
  DEGRADED: "Degraded",
  DRAFT: "Draft",
  FAILED: "Failed",
  HEALTHY: "Healthy",
  HELD: "Held",
  IN_REVIEW: "In review",
  INVALID: "Invalid",
  NEEDS_ATTENTION: "Needs attention",
  NEEDS_FIX: "Needs fix",
  NEEDS_RECONCILIATION: "Needs reconciliation",
  NEEDS_REVIEW: "Needs review",
  NEW: "New",
  OPEN: "Open",
  PAUSED: "Paused",
  PUBLISHED: "Published",
  PUBLISHING: "Publishing",
  READY: "Draft ready",
  RECONCILED: "Reconciled",
  RECONCILING: "Reconciling",
  REJECTED: "Rejected",
  RESOLVED: "Resolved",
  RETRYABLE: "Retryable",
  RUNNING: "Running",
  SCHEDULED: "Scheduled",
  SHORTLISTED: "Shortlisted",
  SUCCEEDED: "Succeeded",
  UNHEALTHY: "Unhealthy",
  UPLOADING: "Uploading",
  WAIVED: "Waived"
};

export function humanizeStatus(value: string | null | undefined): string {
  if (!value) return "Unknown";
  const direct = STATUS_LABELS[value];
  if (direct) return direct;
  if (!/^[A-Z0-9_]+$/.test(value)) return value;
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^\w/, (match) => match.toUpperCase());
}

