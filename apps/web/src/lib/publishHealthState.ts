import type { OperatorFeedbackPayload, PublicationOutcomeItem, PublishHealthDashboard } from "../types/analytics";

export function healthStatusLabel(snapshot: PublishHealthDashboard): string {
  if (snapshot.overview.needs_reconciliation_attempts > 0) return "Needs reconciliation";
  if (snapshot.overview.failed_attempts > snapshot.overview.succeeded_attempts) return "Publish issues";
  if (snapshot.overview.total_attempts === 0) return "No publish attempts";
  return "Healthy";
}

export function needsAttentionCount(snapshot: PublishHealthDashboard): number {
  return (
    snapshot.action_queue.needs_reconciliation.length +
    snapshot.action_queue.drafts_ready.length +
    snapshot.action_queue.blocked_by_risk_count
  );
}

export function buildFeedbackPayload(
  publication: PublicationOutcomeItem,
  form: {
    qualityLabel: string;
    confidence: string;
    rootCause: string;
    note: string;
  }
): OperatorFeedbackPayload {
  return {
    target_type: "PUBLISH_DRAFT",
    target_id: publication.publish_draft_id,
    quality_label: form.qualityLabel as OperatorFeedbackPayload["quality_label"],
    publish_confidence: form.confidence as OperatorFeedbackPayload["publish_confidence"],
    root_cause: form.rootCause ? (form.rootCause as OperatorFeedbackPayload["root_cause"]) : null,
    note: form.note.trim() || null,
    created_by: "local_operator"
  };
}
