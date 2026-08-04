"use client";

import { useEffect, useState } from "react";
import { fetchPublishControlQueue, fetchRoutingRules } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import type { PublishControlQueue, RoutingRule } from "../../types/publish-control";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { StatusBadge } from "../app-shell/StatusBadge";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { OpsMetricCard, OpsPanel, OpsState, statusTone } from "./OpsShared";

export function OpsRoutingRulesPage() {
  const t = useT();
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const request = useLatestRequest();

  async function load(mode: LatestRequestMode = queue ? "refresh" : "initial") {
    await request.run(
      async () => Promise.all([fetchRoutingRules(), fetchPublishControlQueue()]),
      ([rulesPayload, queuePayload]) => {
        setRules(rulesPayload.rules);
        setQueue(queuePayload);
      },
      mode
    ).catch(() => undefined);
  }

  useEffect(() => {
    void load("initial");
  }, [t]);

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load("refresh")} />
  );
  const hasData = Boolean(queue);
  const boundaryStatus = request.initialLoading && !hasData ? "loading" : request.error && !hasData ? "error" : "success";

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsRoutingRules.description")} title={t("opsRoutingRules.title")}>
      <AsyncContentBoundary
        refreshing={request.refreshing}
        status={boundaryStatus}
        skeletonVariant="dashboard"
        loadingLabel={t("opsRoutingRules.loadingDetail")}
        errorState={<OpsState title={t("opsRoutingRules.unavailableTitle")} detail={request.error?.message ?? t("opsRoutingRules.unavailableTitle")} retry={() => void load("initial")} />}
      >
      <main className="ops-page">
        <div className="actions-row">
          <a href="/ops/publish-control">{t("opsAccounts.openPublishControl")}</a>
        </div>
        {hasData && request.error ? <div className="inline-error">{request.error.message}</div> : null}

        <section className="health-overview-grid">
          <OpsMetricCard label={t("opsRoutingRules.rules")} value={String(rules.length)} detail={t("opsRoutingRules.configuredRules")} />
          <OpsMetricCard label={t("opsRoutingRules.activeRules")} value={String(rules.filter((item) => item.status === "ACTIVE").length)} detail={t("opsRoutingRules.eligibleForMatching")} tone="good" />
          <OpsMetricCard label={t("opsRoutingRules.unassigned")} value={String(queue?.unassigned_drafts.length ?? 0)} detail={t("opsRoutingRules.draftsNeedAssignment")} tone={(queue?.unassigned_drafts.length ?? 0) > 0 ? "warn" : "good"} />
          <OpsMetricCard label={t("opsRoutingRules.needsAttention")} value={String(queue?.needs_attention.length ?? 0)} detail={t("opsRoutingRules.blockedOrWarningItems")} tone={(queue?.needs_attention.length ?? 0) > 0 ? "warn" : "good"} />
        </section>

        <section className="ops-grid">
          <OpsPanel title={t("opsRoutingRules.ruleSummary")}>
            <table className="health-table">
              <thead>
                <tr><th>{t("opsRoutingRules.rule")}</th><th>{t("opsRoutingRules.status")}</th><th>{t("opsRoutingRules.priority")}</th><th>{t("opsRoutingRules.match")}</th><th>{t("opsRoutingRules.action")}</th><th>{t("opsRoutingRules.fallback")}</th></tr>
              </thead>
              <tbody>
                {rules.length === 0 ? <tr><td colSpan={6}>{t("opsRoutingRules.noRoutingRulesConfigured")}</td></tr> : null}
                {rules.map((rule) => (
                  <tr key={rule.id}>
                    <td>{rule.rule_name}</td>
                    <td><StatusBadge label={rule.status} tone={statusTone(rule.status)} /></td>
                    <td>{rule.priority}</td>
                    <td><code>{JSON.stringify(rule.match_json ?? {})}</code></td>
                    <td><code>{JSON.stringify(rule.action_json ?? {})}</code></td>
                    <td>{rule.fallback_behavior ?? "manual"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </OpsPanel>

          <OpsPanel title={t("opsRoutingRules.queueCoverage")}>
            <ul className="compact-list">
              <li><strong>{queue?.unassigned_drafts.length ?? 0}</strong><span> {t("opsRoutingRules.unassignedDrafts")}</span></li>
              <li><strong>{queue?.assigned_drafts.length ?? 0}</strong><span> {t("opsRoutingRules.assignedDrafts")}</span></li>
              <li><strong>{queue?.scheduled_drafts.length ?? 0}</strong><span> {t("opsRoutingRules.scheduledDrafts")}</span></li>
              <li><strong>{queue?.needs_attention.length ?? 0}</strong><span> {t("opsRoutingRules.needsAttention")}</span></li>
            </ul>
          </OpsPanel>
        </section>
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
