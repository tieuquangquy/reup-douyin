"use client";

import { useT } from "../../lib/i18n";
import { activeRiskFlags, isActiveRiskFlag } from "../../lib/riskState";
import { humanizeStatus } from "../../lib/statusLabels";
import type { OperatorRiskDecisionType, RiskFlag, RiskSummary } from "../../types/risk";
import { AsyncButton } from "../shared/AsyncButton";

function ScanIcon() {
  return (
    <svg className="publish-draft-desk__bay-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M10 3.4 16.2 6v4.1c0 3.6-2.4 5.8-6.2 6.9-3.8-1.1-6.2-3.3-6.2-6.9V6L10 3.4Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.6"
      />
      <path d="M7.4 10.1 9.1 11.8l3.5-3.7" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  );
}

export function PublishDraftGate({
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
  const flags = summary?.flags ?? [];
  const openCount = activeRiskFlags(flags).length;
  const label = !gate
    ? t("riskSummary.notScanned")
    : !gate.can_continue
      ? t("riskSummary.gateBlockedGeneric")
      : gate.requires_operator_decision
        ? t("riskSummary.gateNeedsDecision")
        : t("riskSummary.gateClear");
  const tone = !gate ? "" : !gate.can_continue || gate.requires_operator_decision ? " is-warn" : " is-ready";

  return (
    <>
      <div className="publish-draft-desk__scan">
        <h3 className="visually-hidden">{t("publishDraftPage.scanRisk")}</h3>
        <div className="publish-draft-desk__cta-row publish-draft-desk__scan-head">
          <span className={`publish-draft-desk__chip${tone}`}>{label}{openCount ? ` · ${openCount}` : ""}</span>
          <AsyncButton
            className="publish-draft-desk__action is-risk is-compact"
            pending={loading}
            pendingLabel={t("publishDraftPage.scanningRisk")}
            leadingIcon={<ScanIcon />}
            onClick={onScan}
          >
            {t("publishDraftPage.scanRiskAction")}
          </AsyncButton>
        </div>
        <p className="publish-draft-desk__scan-hint">{t("publishDraftPage.scanRiskHint")}</p>
      </div>
      {gate?.requires_operator_decision ? (
        <div className="publish-draft-desk__gate-choices">
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
      ) : null}
      {flags.length > 0 ? (
        <div className="publish-draft-desk__flag-list">
          <p className="publish-draft-desk__flag-heading">{t("riskSummary.title")}</p>
          <ul className="compact-list">
            {flags.map((flag) => (
              <li key={flag.id}>
                <span>
                  {flag.title?.trim() || flag.flag_type} · {humanizeStatus(flag.status)}
                </span>
                {isActiveRiskFlag(flag.status) ? (
                  <button type="button" disabled={loading} onClick={() => onFlagAction(flag, "waive")}>
                    {t("riskSummary.waive")}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}
