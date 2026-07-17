import assert from "node:assert/strict";
import { activeRiskFlags, gateMessage, highestRiskSeverity, riskBadgeClass } from "../lib/riskState";
import type { RiskFlag, RiskGateSummary } from "../types/risk";

const flags: RiskFlag[] = [
  makeFlag("1", "LOW", "RESOLVED"),
  makeFlag("2", "HIGH", "OPEN"),
  makeFlag("3", "CRITICAL", "ACKNOWLEDGED")
];

assert.equal(activeRiskFlags(flags).length, 2);
assert.equal(highestRiskSeverity(flags), "CRITICAL");
assert.equal(riskBadgeClass("CRITICAL"), "danger");
assert.equal(riskBadgeClass("HIGH"), "warn");

const gate: RiskGateSummary = {
  can_continue: false,
  requires_operator_decision: true,
  blocking_reasons: ["Critical warning"],
  highest_severity: "CRITICAL",
  open_counts_by_severity: { CRITICAL: 1 },
  accepted_with_warning: false
};
assert.equal(gateMessage(gate), "Blocked by: Critical warning");

console.log("risk state tests passed");

function makeFlag(id: string, severity: RiskFlag["severity"], status: RiskFlag["status"]): RiskFlag {
  return {
    id,
    source_video_id: "video-1",
    target_type: "PUBLISH_DRAFT",
    target_id: "draft-1",
    flag_type: "MANUAL_REVIEW_REQUIRED",
    severity,
    status,
    title: "Risk",
    description: "Risk description",
    evidence_summary: "Evidence",
    scan_source: "test",
    detected_at: "2026-04-17T00:00:00Z",
    resolution_note: null
  };
}
