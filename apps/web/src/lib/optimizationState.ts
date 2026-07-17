import type { OptimizationDashboard, OutcomeGroupSummary, RoutingHints } from "../types/optimization";

export function optimizationHeadline(snapshot: OptimizationDashboard): string {
  const strongest = snapshot.outcome_summaries.by_preset[0];
  if (!strongest) return "Not enough outcome data yet";
  return `${strongest.label} is leading with ${strongest.average_outcome_score ?? "-"} average outcome`;
}

export function automationReadinessLabel(hint: RoutingHints): string {
  if (hint.automation_policy.can_auto_assign) return "Safe to auto-assign";
  if (hint.recommended_accounts[0]?.confidence_label === "high") return "High confidence, review guardrails";
  if (hint.recommended_accounts.length > 0) return "Suggestion only";
  return "Manual routing required";
}

export function groupTone(group: OutcomeGroupSummary): "good" | "warn" | "danger" | "muted" {
  if (group.average_outcome_score === null) return "muted";
  if (group.average_outcome_score >= 80) return "good";
  if (group.average_outcome_score >= 60) return "warn";
  return "danger";
}

