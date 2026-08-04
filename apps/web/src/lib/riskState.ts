import type { RiskFlag, RiskFlagStatus, RiskGateSummary, RiskSeverity } from "../types/risk";

const SEVERITY_ORDER: Record<RiskSeverity, number> = {
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4,
  BLOCKING: 4
};

export function isActiveRiskFlag(status: RiskFlagStatus): boolean {
  return status === "OPEN" || status === "ACKNOWLEDGED";
}

export function activeRiskFlags(flags: RiskFlag[]): RiskFlag[] {
  return flags.filter((flag) => isActiveRiskFlag(flag.status));
}

/** Snake-case pipeline warning codes (e.g. subtitle_lines_wrapped_for_burn). */
export function looksLikeWarningCode(value: string): boolean {
  return /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/i.test(value.trim());
}

export function humanizeWarningCode(code: string): string {
  const trimmed = code.trim();
  if (!trimmed) return trimmed;
  const spaced = trimmed.replace(/_/g, " ").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function resolveRiskWarningLabel(evidence: string, t: (key: string) => string): string {
  const code = evidence.trim();
  if (!code) return code;
  const key = `riskWarnings.${code}`;
  const translated = t(key);
  if (translated !== key) return translated;
  if (looksLikeWarningCode(code)) return humanizeWarningCode(code);
  return code;
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
