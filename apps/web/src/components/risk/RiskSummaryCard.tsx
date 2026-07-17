"use client";

import { useT } from "../../lib/i18n";
import { gateMessage, riskBadgeClass } from "../../lib/riskState";
import { humanizeStatus } from "../../lib/statusLabels";
import type { OperatorRiskDecisionType, RiskFlag, RiskSummary } from "../../types/risk";

export function RiskSummaryCard({
  summary,
  loading,
  onScan,
  onFlagAction,
  onDecision
}: {
  summary: RiskSummary | null;
  loading: boolean;
  onScan: () => void;
  onFlagAction: (flag: RiskFlag, action: "acknowledge" | "resolve" | "waive") => void;
  onDecision: (decision: OperatorRiskDecisionType) => void;
}) {
  const t = useT();
  const highest = summary?.gate.highest_severity ?? null;
  const flags = summary?.flags ?? [];

  return (
    <section className="risk-panel">
      <div className="panel-heading">
        <h2>{t("riskSummary.title")}</h2>
        <span className={`pill ${riskBadgeClass(highest)}`}>{humanizeStatus(highest ?? "not scanned")}</span>
      </div>
      <p className="muted">{gateMessage(summary?.gate ?? null)}</p>
      <button onClick={onScan} disabled={loading}>{loading ? t("riskSummary.scanning") : t("riskSummary.runRiskScan")}</button>
      {flags.length === 0 ? (
        <p className="muted">{t("riskSummary.noWarnings")}</p>
      ) : (
        <div className="risk-flag-list">
          {flags.map((flag) => (
            <article key={flag.id} className={`risk-flag ${riskBadgeClass(flag.severity)}`}>
              <div>
                <strong>{flag.title ?? flag.flag_type}</strong>
                <span>{humanizeStatus(flag.severity)} / {humanizeStatus(flag.status)}</span>
              </div>
              <p>{flag.description}</p>
              {flag.evidence_summary ? <small>{flag.evidence_summary}</small> : null}
              <div className="risk-actions">
                <button onClick={() => onFlagAction(flag, "acknowledge")} disabled={loading || flag.status !== "OPEN"}>{t("riskSummary.acknowledge")}</button>
                <button onClick={() => onFlagAction(flag, "resolve")} disabled={loading}>{t("riskSummary.resolve")}</button>
                <button onClick={() => onFlagAction(flag, "waive")} disabled={loading}>{t("riskSummary.waive")}</button>
              </div>
            </article>
          ))}
        </div>
      )}
      <div className="risk-decision-row">
        <button onClick={() => onDecision("CONTINUE")} disabled={loading}>{t("riskSummary.continue")}</button>
        <button onClick={() => onDecision("NEEDS_FIX")} disabled={loading}>{t("riskSummary.needsFix")}</button>
        <button onClick={() => onDecision("REJECT")} disabled={loading}>{t("riskSummary.reject")}</button>
        <button onClick={() => onDecision("ACCEPT_WITH_WARNING")} disabled={loading}>{t("riskSummary.acceptWithWarning")}</button>
      </div>
      {summary?.latest_decision ? (
        <p className="muted">{t("riskSummary.latestDecision")}: {humanizeStatus(summary.latest_decision.decision_type)} at {new Date(summary.latest_decision.decided_at).toLocaleString()}</p>
      ) : null}
    </section>
  );
}
