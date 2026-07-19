"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchPublishAttemptList } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PublishAttempt } from "../../types/publish-draft";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { StatusBadge } from "../app-shell/StatusBadge";
import { OpsMetricCard, OpsPanel, OpsState, formatDateTime, statusTone } from "./OpsShared";

export function OpsPublishAttemptsPage() {
  const t = useT();
  const [attempts, setAttempts] = useState<PublishAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setAttempts(await fetchPublishAttemptList(undefined, 100));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsPublishAttempts.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const counts = useMemo(() => {
    return attempts.reduce<Record<string, number>>((acc, attempt) => {
      acc[attempt.status] = (acc[attempt.status] ?? 0) + 1;
      return acc;
    }, {});
  }, [attempts]);

  const refreshAction = (
    <TopbarRefreshButton busy={loading && attempts.length > 0} disabled={loading && attempts.length === 0} onClick={() => void load()} />
  );

  if (loading && attempts.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsPublishAttempts.description")} title={t("opsPublishAttempts.title")}>
        <OpsState title={t("opsPublishAttempts.loadingTitle")} detail={t("opsPublishAttempts.loadingDetail")} />
      </OpsConsoleShell>
    );
  }

  if (error && attempts.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsPublishAttempts.description")} title={t("opsPublishAttempts.title")}>
        <OpsState title={t("opsPublishAttempts.unavailableTitle")} detail={error} retry={() => void load()} />
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsPublishAttempts.description")} title={t("opsPublishAttempts.title")}>
      <main className="ops-page">
        {error ? <div className="inline-error">{error}</div> : null}

        <section className="health-overview-grid">
          <OpsMetricCard label={t("opsPublishAttempts.attempts")} value={String(attempts.length)} detail={t("opsPublishAttempts.latest100")} />
          <OpsMetricCard label={t("opsPublishAttempts.succeeded")} value={String(counts.SUCCEEDED ?? 0)} detail={t("opsPublishAttempts.internalSuccess")} tone="good" />
          <OpsMetricCard label={t("opsPublishAttempts.failed")} value={String(counts.FAILED ?? 0)} detail={t("opsPublishAttempts.internalFailure")} tone={(counts.FAILED ?? 0) > 0 ? "danger" : "good"} />
          <OpsMetricCard label={t("opsPublishAttempts.needsReconcile")} value={String(counts.NEEDS_RECONCILIATION ?? 0)} detail={t("opsPublishAttempts.uncertainExternal")} tone={(counts.NEEDS_RECONCILIATION ?? 0) > 0 ? "warn" : "good"} />
        </section>

        <section className="ops-grid">
          <OpsPanel title={t("opsPublishAttempts.latestAttempts")}>
            <table className="health-table">
              <thead>
                <tr><th>{t("opsPublishAttempts.attempt")}</th><th>{t("opsPublishAttempts.draft")}</th><th>{t("opsPublishAttempts.status")}</th><th>{t("opsPublishAttempts.external")}</th><th>{t("opsPublishAttempts.account")}</th><th>{t("opsPublishAttempts.permalink")}</th><th>{t("opsJobs.error")}</th><th>{t("opsPublishAttempts.checked")}</th></tr>
              </thead>
              <tbody>
                {attempts.length === 0 ? <tr><td colSpan={8}>{t("opsPublishAttempts.noPublishAttemptsYet")}</td></tr> : null}
                {attempts.map((attempt) => (
                  <tr key={attempt.id}>
                    <td>#{attempt.attempt_number} {attempt.id.slice(0, 8)}</td>
                    <td><a href={`/publishing/drafts/${attempt.publish_draft_id}`}>{attempt.publish_draft_id.slice(0, 8)}</a></td>
                    <td><StatusBadge label={attempt.status} tone={statusTone(attempt.status)} /></td>
                    <td>{attempt.external_status ?? "UNKNOWN"}</td>
                    <td>{attempt.platform_account_id.slice(0, 8)}</td>
                    <td>{attempt.external_permalink ? <a href={attempt.external_permalink} target="_blank" rel="noreferrer">{t("ops.open")}</a> : "-"}</td>
                    <td>{attempt.error_code ?? attempt.error_message ?? "-"}</td>
                    <td>{formatDateTime(attempt.last_status_checked_at ?? attempt.updated_at)}</td>
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
