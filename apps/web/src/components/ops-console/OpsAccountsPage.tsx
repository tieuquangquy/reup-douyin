"use client";

import { useEffect, useState } from "react";
import { fetchAllPlatformAccounts, fetchPublishControlQueue } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PlatformAccount } from "../../types/publish-draft";
import type { PublishControlQueue } from "../../types/publish-control";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { StatusBadge } from "../app-shell/StatusBadge";
import { OpsMetricCard, OpsPanel, OpsState, formatDateTime, statusTone } from "./OpsShared";

export function OpsAccountsPage() {
  const t = useT();
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [accountPayload, queuePayload] = await Promise.all([fetchAllPlatformAccounts(), fetchPublishControlQueue()]);
      setAccounts(accountPayload);
      setQueue(queuePayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsAccounts.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const refreshAction = (
    <TopbarRefreshButton busy={loading && accounts.length > 0} disabled={loading && accounts.length === 0} onClick={() => void load()} />
  );

  if (loading && accounts.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}>
        <OpsState title={t("opsAccounts.loadingTitle")} detail={t("opsAccounts.loadingDetail")} />
      </OpsConsoleShell>
    );
  }

  if (error && accounts.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}>
        <OpsState title={t("opsAccounts.unavailableTitle")} detail={error} retry={() => void load()} />
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}>
      <main className="ops-page">
        <div className="actions-row">
          <a href="/ops/publish-control">{t("opsAccounts.openPublishControl")}</a>
        </div>
        {error ? <div className="inline-error">{error}</div> : null}

        <section className="health-overview-grid">
          <OpsMetricCard label={t("opsAccounts.accounts")} value={String(accounts.length)} detail={t("opsAccounts.configuredRecords")} />
          <OpsMetricCard label={t("opsAccounts.active")} value={String(accounts.filter((item) => item.status === "ACTIVE").length)} detail={t("opsAccounts.readyForRouting")} tone="good" />
          <OpsMetricCard label={t("opsAccounts.onHold")} value={String(accounts.filter((item) => item.is_on_hold).length)} detail={t("opsAccounts.manualHoldFlag")} tone={accounts.some((item) => item.is_on_hold) ? "warn" : "good"} />
          <OpsMetricCard label={t("opsAccounts.unhealthy")} value={String(queue?.accounts.filter((item) => item.health_status === "UNHEALTHY").length ?? 0)} detail={t("opsAccounts.healthModelOutput")} tone={(queue?.accounts.some((item) => item.health_status === "UNHEALTHY") ?? false) ? "danger" : "good"} />
        </section>

        <section className="ops-grid">
          <OpsPanel title={t("opsAccounts.platformAccounts")}>
            <table className="health-table">
              <thead>
                <tr><th>{t("opsAccounts.account")}</th><th>{t("opsAccounts.platform")}</th><th>{t("opsAccounts.status")}</th><th>{t("opsAccounts.pageId")}</th><th>{t("opsAccounts.priority")}</th><th>{t("opsAccounts.hold")}</th><th>{t("opsAccounts.updated")}</th></tr>
              </thead>
              <tbody>
                {accounts.length === 0 ? <tr><td colSpan={7}>{t("opsAccounts.noPlatformAccountsConfigured")}</td></tr> : null}
                {accounts.map((account) => (
                  <tr key={account.id}>
                    <td>{account.display_name}</td>
                    <td>{account.platform}</td>
                    <td><StatusBadge label={account.status} tone={statusTone(account.status)} /></td>
                    <td>{account.external_account_id}</td>
                    <td>{account.priority}</td>
                    <td>{account.is_on_hold ? t("opsAccounts.yes") : t("opsAccounts.no")}</td>
                    <td>{formatDateTime(account.updated_at)}</td>
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
