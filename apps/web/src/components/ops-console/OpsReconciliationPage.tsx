"use client";

import { useEffect, useState } from "react";
import { fetchPublishAttemptList, refreshPublishAttemptStatus } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PublishAttempt } from "../../types/publish-draft";
import { StatusBadge } from "../app-shell/StatusBadge";
import { OpsMetricCard, OpsPageHeader, OpsPanel, OpsState, formatDateTime, statusTone } from "./OpsShared";

export function OpsReconciliationPage() {
  const t = useT();
  const [attempts, setAttempts] = useState<PublishAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [needed, reconciling] = await Promise.all([
        fetchPublishAttemptList("NEEDS_RECONCILIATION", 100),
        fetchPublishAttemptList("RECONCILING", 100)
      ]);
      setAttempts([...needed, ...reconciling]);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsReconciliation.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  async function refresh(attempt: PublishAttempt) {
    setSavingId(attempt.id);
    setError(null);
    try {
      await refreshPublishAttemptStatus(attempt.id);
      setMessage(t("opsReconciliation.publishStatusRefreshed"));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsReconciliation.failedToRefresh"));
    } finally {
      setSavingId(null);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  if (loading && attempts.length === 0) return <OpsState title={t("opsReconciliation.loadingTitle")} detail={t("opsReconciliation.loadingDetail")} />;
  if (error && attempts.length === 0) return <OpsState title={t("opsReconciliation.unavailableTitle")} detail={error} retry={() => void load()} />;

  return (
    <main className="ops-page">
      <OpsPageHeader title={t("opsReconciliation.title")} description={t("opsReconciliation.description")} actions={<button type="button" onClick={() => void load()}>{t("opsReconciliation.refreshQueue")}</button>} />
      {error ? <div className="inline-error">{error}</div> : null}
      {message ? <div className="publish-ready-banner">{message}</div> : null}

      <section className="health-overview-grid">
        <OpsMetricCard label={t("opsReconciliation.needsReconcile")} value={String(attempts.filter((item) => item.status === "NEEDS_RECONCILIATION").length)} detail={t("opsReconciliation.manualRefreshAdvised")} tone={attempts.length > 0 ? "warn" : "good"} />
        <OpsMetricCard label={t("opsReconciliation.reconciling")} value={String(attempts.filter((item) => item.status === "RECONCILING").length)} detail={t("opsReconciliation.inProgress")} />
        <OpsMetricCard label={t("opsReconciliation.externalUnknown")} value={String(attempts.filter((item) => !item.external_status || item.external_status === "UNKNOWN").length)} detail={t("opsReconciliation.platformUnclear")} tone="warn" />
      </section>

      <section className="ops-grid">
        <OpsPanel title={t("opsReconciliation.attemptsNeedingReconciliation")}>
          <table className="health-table">
            <thead>
              <tr><th>{t("opsReconciliation.attempt")}</th><th>{t("opsReconciliation.draft")}</th><th>{t("opsReconciliation.internal")}</th><th>{t("opsReconciliation.external")}</th><th>{t("opsReconciliation.externalId")}</th><th>{t("opsReconciliation.lastChecked")}</th><th>{t("opsReconciliation.action")}</th></tr>
            </thead>
            <tbody>
              {attempts.length === 0 ? <tr><td colSpan={7}>{t("opsReconciliation.noReconciliationBacklog")}</td></tr> : null}
              {attempts.map((attempt) => (
                <tr key={attempt.id}>
                  <td>{attempt.id.slice(0, 8)}</td>
                  <td><a href={`/publishing/drafts/${attempt.publish_draft_id}`}>{attempt.publish_draft_id.slice(0, 8)}</a></td>
                  <td><StatusBadge label={attempt.status} tone={statusTone(attempt.status)} /></td>
                  <td>{attempt.external_status ?? "UNKNOWN"}</td>
                  <td>{attempt.external_publish_id ?? attempt.external_media_id ?? t("opsReconciliation.noTimestamp")}</td>
                  <td>{formatDateTime(attempt.last_status_checked_at) ?? t("opsReconciliation.noTimestamp")}</td>
                  <td><button type="button" disabled={savingId === attempt.id} onClick={() => void refresh(attempt)}>{savingId === attempt.id ? t("opsReconciliation.refreshing") : t("opsReconciliation.refreshStatus")}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </OpsPanel>
      </section>
    </main>
  );
}
