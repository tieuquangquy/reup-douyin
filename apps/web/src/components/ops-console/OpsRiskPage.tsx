"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchRiskFlags } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { RiskFlag } from "../../types/risk";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { StatusBadge } from "../app-shell/StatusBadge";
import { OpsMetricCard, OpsPanel, OpsState, formatDateTime, statusTone } from "./OpsShared";

export function OpsRiskPage() {
  const t = useT();
  const [flags, setFlags] = useState<RiskFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [open, acknowledged, waived, resolved] = await Promise.all([
        fetchRiskFlags("OPEN"),
        fetchRiskFlags("ACKNOWLEDGED"),
        fetchRiskFlags("WAIVED"),
        fetchRiskFlags("RESOLVED")
      ]);
      setFlags([...open, ...acknowledged, ...waived, ...resolved]);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsRisk.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const counts = useMemo(() => {
    return flags.reduce<Record<string, number>>((acc, flag) => {
      acc[flag.status] = (acc[flag.status] ?? 0) + 1;
      acc[flag.severity] = (acc[flag.severity] ?? 0) + 1;
      return acc;
    }, {});
  }, [flags]);

  const refreshAction = (
    <TopbarRefreshButton busy={loading && flags.length > 0} disabled={loading && flags.length === 0} onClick={() => void load()} />
  );

  if (loading && flags.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsRisk.description")} title={t("opsRisk.title")}>
        <OpsState title={t("opsRisk.loadingTitle")} detail={t("opsRisk.loadingDetail")} />
      </OpsConsoleShell>
    );
  }

  if (error && flags.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsRisk.description")} title={t("opsRisk.title")}>
        <OpsState title={t("opsRisk.unavailableTitle")} detail={error} retry={() => void load()} />
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsRisk.description")} title={t("opsRisk.title")}>
      <main className="ops-page">
        {error ? <div className="inline-error">{error}</div> : null}

        <section className="health-overview-grid">
          <OpsMetricCard label={t("opsRisk.open")} value={String(counts.OPEN ?? 0)} detail={t("opsRisk.needsOperatorAttention")} tone={(counts.OPEN ?? 0) > 0 ? "warn" : "good"} />
          <OpsMetricCard label={t("opsRisk.blockingCritical")} value={String((counts.BLOCKING ?? 0) + (counts.CRITICAL ?? 0))} detail={t("opsRisk.highestRiskSeverities")} tone={(counts.BLOCKING ?? 0) + (counts.CRITICAL ?? 0) > 0 ? "danger" : "good"} />
          <OpsMetricCard label={t("opsRisk.acknowledged")} value={String(counts.ACKNOWLEDGED ?? 0)} detail={t("opsRisk.seenNotResolved")} />
          <OpsMetricCard label={t("opsRisk.waived")} value={String(counts.WAIVED ?? 0)} detail={t("opsRisk.operatorOverrideRecorded")} tone={(counts.WAIVED ?? 0) > 0 ? "warn" : "muted"} />
          <OpsMetricCard label={t("opsRisk.resolved")} value={String(counts.RESOLVED ?? 0)} detail={t("opsRisk.closedWarnings")} tone="good" />
        </section>

        <section className="ops-grid">
          <OpsPanel title={t("opsRisk.riskFlags")}>
            <table className="health-table">
              <thead>
                <tr><th>{t("opsRisk.flag")}</th><th>{t("opsRisk.target")}</th><th>{t("opsRisk.severity")}</th><th>{t("opsRisk.status")}</th><th>{t("opsRisk.evidence")}</th><th>{t("opsRisk.detected")}</th></tr>
              </thead>
              <tbody>
                {flags.length === 0 ? <tr><td colSpan={6}>{t("opsRisk.noRiskFlagsFound")}</td></tr> : null}
                {flags.map((flag) => (
                  <tr key={flag.id}>
                    <td>{flag.title ?? flag.flag_type}</td>
                    <td>{flag.target_type} {flag.target_id ? flag.target_id.slice(0, 8) : "-"}</td>
                    <td><StatusBadge label={flag.severity} tone={statusTone(flag.severity)} /></td>
                    <td><StatusBadge label={flag.status} tone={statusTone(flag.status)} /></td>
                    <td>{flag.evidence_summary ?? flag.description ?? "-"}</td>
                    <td>{formatDateTime(flag.detected_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </OpsPanel>
        </section>
      </main>
    </OpsConsoleShell>
  );
}
