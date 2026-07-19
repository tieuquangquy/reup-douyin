"use client";

import { useT } from "../../lib/i18n";
import { activeRiskFlags, riskBadgeClass } from "../../lib/riskState";
import { humanizeStatus } from "../../lib/statusLabels";
import type { OperatorRiskDecisionType, RiskFlag, RiskGateSummary, RiskSummary } from "../../types/risk";

function flagTooltip(flag: RiskFlag): string {
  const parts = [flag.description, flag.evidence_summary].filter(
    (part): part is string => Boolean(part && part.trim())
  );
  return parts.join(" — ");
}

function gateLabel(
  gate: RiskGateSummary | null,
  t: (key: string) => string
): string {
  if (!gate) return t("riskSummary.gateNotScanned");
  if (!gate.can_continue) {
    const reasons = gate.blocking_reasons.filter(Boolean).join(", ");
    return reasons
      ? t("riskSummary.gateBlocked").replace("{reasons}", reasons)
      : t("riskSummary.gateBlockedGeneric");
  }
  if (gate.requires_operator_decision) return t("riskSummary.gateNeedsDecision");
  return t("riskSummary.gateClear");
}

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
  const gate = summary?.gate ?? null;
  const highest = gate?.highest_severity ?? null;
  const flags = summary?.flags ?? [];
  const openCount = activeRiskFlags(flags).length;

  return (
    <section className="risk-panel fr-risk" aria-label={t("riskSummary.title")}>
      <div className="fr-risk__head">
        <div className="fr-risk__title-row">
          <h2>{t("riskSummary.title")}</h2>
          <span className={`pill ${riskBadgeClass(highest)}`}>
            {highest ? humanizeStatus(highest) : t("riskSummary.notScanned")}
            {flags.length > 0 ? ` · ${openCount}` : ""}
          </span>
        </div>
        <p className="fr-risk__hint">{t("riskSummary.hintShort")}</p>
        <p className="fr-risk__gate">{gateLabel(gate, t)}</p>
        <button type="button" className="primary fr-risk__scan" onClick={onScan} disabled={loading}>
          {loading ? t("riskSummary.scanning") : t("riskSummary.runRiskScan")}
        </button>
      </div>

      {flags.length === 0 ? (
        <p className="fr-risk__empty">{t("riskSummary.noWarnings")}</p>
      ) : (
        <ul className="fr-risk__list">
          {flags.map((flag) => (
            <li
              key={flag.id}
              className={`fr-risk__row ${riskBadgeClass(flag.severity)}`}
              title={flagTooltip(flag)}
            >
              <div className="fr-risk__row-main">
                <strong>{flag.title ?? flag.flag_type}</strong>
                <span className="fr-risk__meta">
                  {humanizeStatus(flag.severity)} · {humanizeStatus(flag.status)}
                </span>
              </div>
              <div className="fr-risk__row-actions">
                <button
                  type="button"
                  onClick={() => onFlagAction(flag, "acknowledge")}
                  disabled={loading || flag.status !== "OPEN"}
                  title={t("riskSummary.acknowledge")}
                >
                  {t("riskSummary.acknowledge")}
                </button>
                <button
                  type="button"
                  onClick={() => onFlagAction(flag, "resolve")}
                  disabled={loading}
                  title={t("riskSummary.resolve")}
                >
                  {t("riskSummary.resolve")}
                </button>
                <button
                  type="button"
                  onClick={() => onFlagAction(flag, "waive")}
                  disabled={loading}
                  title={t("riskSummary.waive")}
                >
                  {t("riskSummary.waive")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="fr-risk__decisions" role="group" aria-label={t("riskSummary.decisionLabel")}>
        <button type="button" onClick={() => onDecision("CONTINUE")} disabled={loading}>
          {t("riskSummary.continue")}
        </button>
        <button type="button" onClick={() => onDecision("NEEDS_FIX")} disabled={loading}>
          {t("riskSummary.needsFix")}
        </button>
        <button type="button" onClick={() => onDecision("REJECT")} disabled={loading}>
          {t("riskSummary.reject")}
        </button>
        <button type="button" onClick={() => onDecision("ACCEPT_WITH_WARNING")} disabled={loading}>
          {t("riskSummary.acceptWithWarning")}
        </button>
      </div>

      {summary?.latest_decision ? (
        <p className="fr-risk__latest">
          {t("riskSummary.latestDecision")}: {humanizeStatus(summary.latest_decision.decision_type)}
        </p>
      ) : null}
    </section>
  );
}
