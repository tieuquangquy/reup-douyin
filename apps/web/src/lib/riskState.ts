import type { RiskFlag, RiskGateSummary, RiskSeverity } from "../types/risk";

const SEVERITY_ORDER: Record<RiskSeverity, number> = {
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4,
  BLOCKING: 4
};

export function activeRiskFlags(flags: RiskFlag[]): RiskFlag[] {
  return flags.filter((flag) => flag.status === "OPEN" || flag.status === "ACKNOWLEDGED");
}

export function highestRiskSeverity(flags: RiskFlag[]): RiskSeverity | null {
  const active = activeRiskFlags(flags);
  if (!active.length) return null;
  return active.map((flag) => flag.severity).sort((a, b) => SEVERITY_ORDER[b] - SEVERITY_ORDER[a])[0];
}

export function riskBadgeClass(severity: RiskSeverity | null): string {
  if (severity === "CRITICAL" || severity === "BLOCKING") return "danger";
  if (severity === "HIGH" || severity === "MEDIUM") return "warn";
  if (severity === "LOW") return "good";
  return "";
}

export function gateMessage(gate: RiskGateSummary | null): string {
  if (!gate) return "Risk scan has not run yet.";
  if (!gate.can_continue) return `Blocked by: ${gate.blocking_reasons.join(", ")}`;
  if (gate.requires_operator_decision) return "High risk warnings need an operator decision.";
  return "No blocking risk warnings.";
}
