"use client";

import { useT } from "../../lib/i18n";
import {
  activeRiskFlags,
  isActiveRiskFlag,
  looksLikeWarningCode,
  resolveRiskWarningLabel,
  riskBadgeClass
} from "../../lib/riskState";
import { humanizeStatus } from "../../lib/statusLabels";
import type { OperatorRiskDecisionType, RiskFlag, RiskGateSummary, RiskSummary } from "../../types/risk";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";

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

function flagPresentation(flag: RiskFlag, t: (key: string) => string): {
  label: string;
  code: string | null;
  note: string | null;
} {
  const evidence = flag.evidence_summary?.trim() || null;
  if (evidence) {
    const label = resolveRiskWarningLabel(evidence, t);
    const code = looksLikeWarningCode(evidence) && label !== evidence ? evidence : null;
    return { label, code, note: null };
  }
  const description = flag.description?.trim() || null;
  return {
    label: flag.title?.trim() || flag.flag_type,
    code: null,
    note: description
  };
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
          <div className="fr-risk__identity">
            <h2>{t("riskSummary.title")}</h2>
            <span className={`pill ${riskBadgeClass(highest)}`}>
              {highest ? humanizeStatus(highest) : t("riskSummary.notScanned")}
              {flags.length > 0 ? ` · ${openCount}` : ""}
            </span>
          </div>
          <button
            type="button"
            className={`primary fr-risk__scan${loading ? " is-loading" : ""}`}
            onClick={onScan}
            disabled={loading}
            aria-busy={loading || undefined}
            aria-label={loading ? t("riskSummary.scanning") : t("riskSummary.runRiskScan")}
            title={loading ? t("riskSummary.scanning") : t("riskSummary.runRiskScan")}
          >
            <WorkItemActionIcon className="fr-tool__icon" kind="recheck" />
            <span>{t("riskSummary.runRiskScan")}</span>
          </button>
        </div>
        <p className="fr-risk__hint">{t("riskSummary.hintShort")}</p>
        <p className="fr-risk__gate">{gateLabel(gate, t)}</p>
        <div className="fr-risk__decisions" role="group" aria-label={t("riskSummary.decisionLabel")}>
          <button type="button" onClick={() => onDecision("CONTINUE")} disabled={loading}>
            <WorkItemActionIcon className="fr-tool__icon" kind="enter" />
            <span>{t("riskSummary.continue")}</span>
          </button>
          <button type="button" onClick={() => onDecision("NEEDS_FIX")} disabled={loading}>
            <WorkItemActionIcon className="fr-tool__icon" kind="process" />
            <span>{t("riskSummary.needsFix")}</span>
          </button>
          <button type="button" onClick={() => onDecision("REJECT")} disabled={loading}>
            <WorkItemActionIcon className="fr-tool__icon" kind="reject" />
            <span>{t("riskSummary.reject")}</span>
          </button>
          <button type="button" onClick={() => onDecision("ACCEPT_WITH_WARNING")} disabled={loading}>
            <WorkItemActionIcon className="fr-tool__icon" kind="approve" />
            <span>{t("riskSummary.acceptWithWarning")}</span>
          </button>
        </div>
      </div>

      {flags.length === 0 ? (
        <p className="fr-risk__empty">{t("riskSummary.noWarnings")}</p>
      ) : (
        <ul className="fr-risk__list">
          {flags.map((flag) => {
            const actionable = isActiveRiskFlag(flag.status);
            const { label, code, note } = flagPresentation(flag, t);
            return (
              <li
                key={flag.id}
                className={`fr-risk__row ${riskBadgeClass(flag.severity)}${actionable ? "" : " is-closed"}`}
              >
                <div className="fr-risk__row-main">
                  <strong className="fr-risk__label">{label}</strong>
                  <span className="fr-risk__meta">
                    {humanizeStatus(flag.severity)} · {humanizeStatus(flag.status)}
                  </span>
                </div>
                {code ? <code className="fr-risk__code">{code}</code> : null}
                {note ? <p className="fr-risk__detail">{note}</p> : null}
                {actionable ? (
                  <div className="fr-risk__row-actions">
                    <button
                      type="button"
                      onClick={() => onFlagAction(flag, "acknowledge")}
                      disabled={loading || flag.status !== "OPEN"}
                      title={t("riskSummary.acknowledge")}
                    >
                      <WorkItemActionIcon className="fr-tool__icon" kind="details" />
                      <span>{t("riskSummary.acknowledge")}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onFlagAction(flag, "resolve")}
                      disabled={loading}
                      title={t("riskSummary.resolve")}
                    >
                      <WorkItemActionIcon className="fr-tool__icon" kind="approve" />
                      <span>{t("riskSummary.resolve")}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onFlagAction(flag, "waive")}
                      disabled={loading}
                      title={t("riskSummary.waive")}
                    >
                      <WorkItemActionIcon className="fr-tool__icon" kind="dismiss" />
                      <span>{t("riskSummary.waive")}</span>
                    </button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {summary?.latest_decision ? (
        <p className="fr-risk__latest">
          {t("riskSummary.latestDecision")}: {humanizeStatus(summary.latest_decision.decision_type)}
        </p>
      ) : null}
    </section>
  );
}
