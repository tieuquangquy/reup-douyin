export type RiskTargetType = "SOURCE_VIDEO" | "RENDER_OUTPUT" | "PUBLISH_DRAFT";
export type RiskSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | "BLOCKING";
export type RiskFlagStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED" | "WAIVED" | "REJECTED";
export type OperatorRiskDecisionType = "CONTINUE" | "NEEDS_FIX" | "REJECT" | "ACCEPT_WITH_WARNING";

export type RiskFlag = {
  id: string;
  source_video_id: string;
  target_type: RiskTargetType;
  target_id: string | null;
  flag_type: string;
  severity: RiskSeverity;
  status: RiskFlagStatus;
  title: string | null;
  description: string | null;
  evidence_summary: string | null;
  scan_source: string | null;
  detected_at: string | null;
  resolution_note: string | null;
};

export type RiskGateSummary = {
  can_continue: boolean;
  requires_operator_decision: boolean;
  blocking_reasons: string[];
  highest_severity: RiskSeverity | null;
  open_counts_by_severity: Record<string, number>;
  accepted_with_warning: boolean;
};

export type OperatorRiskDecision = {
  id: string;
  target_type: RiskTargetType;
  target_id: string;
  decision_type: OperatorRiskDecisionType;
  note: string | null;
  decided_by: string | null;
  decided_at: string;
};

export type RiskSummary = {
  target_type: RiskTargetType;
  target_id: string;
  flags: RiskFlag[];
  gate: RiskGateSummary;
  latest_decision: OperatorRiskDecision | null;
};
