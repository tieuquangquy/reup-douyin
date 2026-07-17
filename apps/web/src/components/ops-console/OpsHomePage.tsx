"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchOperationalMetrics, fetchPublishControlQueue, fetchPublishHealthDashboard } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PublishControlQueue } from "../../types/publish-control";
import type { PublishHealthDashboard } from "../../types/analytics";
import type { OperationalMetrics } from "../../types/operations";
import { OpsMetricCard, OpsPageHeader, OpsPanel, OpsState, formatDateTime, sumRecord } from "./OpsShared";

type OpsHomeState = {
  metrics: OperationalMetrics;
  publishHealth: PublishHealthDashboard;
  queue: PublishControlQueue;
};

export function OpsHomePage() {
  const t = useT();
  const [state, setState] = useState<OpsHomeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [metrics, publishHealth, queue] = await Promise.all([
        fetchOperationalMetrics(),
        fetchPublishHealthDashboard("last_7_days"),
        fetchPublishControlQueue()
      ]);
      setState({ metrics, publishHealth, queue });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("operatorHome.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const totalJobs = useMemo(() => {
    if (!state) return 0;
    return Object.values(state.metrics.job_counts_by_type_status).reduce((total, counts) => total + sumRecord(counts), 0);
  }, [state]);

  if (loading && !state) return <OpsState title={t("ops.loadingTitle")} detail={t("ops.loadingDetail")} />;
  if (error && !state) return <OpsState title={t("ops.unavailableTitle")} detail={error} retry={() => void load()} />;

  return (
    <main className="ops-page">
      <OpsPageHeader
        title={t("ops.title")}
        description={t("ops.description")}
        actions={<button type="button" onClick={() => void load()}>{t("common.refresh")}</button>}
      />

      {error ? <div className="inline-error">{error}</div> : null}

      {state ? (
        <>
          <section className="health-overview-grid">
            <OpsMetricCard
              label={t("ops.jobs")}
              value={String(totalJobs)}
              detail={`${state.metrics.queue_backlog.running} ${t("ops.actionItems.running")}, ${state.metrics.retryable_jobs} ${t("ops.actionItems.retryable")}`}
              tone={state.metrics.retryable_jobs > 0 ? "warn" : "good"}
            />
            <OpsMetricCard
              label={t("ops.publishSuccess")}
              value={`${state.publishHealth.overview.success_rate_percent}%`}
              detail={`${state.publishHealth.overview.succeeded_attempts}/${state.publishHealth.overview.total_attempts} ${t("ops.actionItems.needsReconciliation").replace("publish attempts", "attempts")}`}
              tone={state.publishHealth.overview.failed_attempts > 0 ? "warn" : "good"}
            />
            <OpsMetricCard
              label={t("ops.reconciliation")}
              value={String(state.publishHealth.overview.needs_reconciliation_attempts)}
              detail={t("ops.metrics.reconciliationDetail")}
              tone={state.publishHealth.overview.needs_reconciliation_attempts > 0 ? "warn" : "good"}
            />
            <OpsMetricCard
              label={t("ops.accounts")}
              value={String(state.queue.accounts.length)}
              detail={`${state.queue.accounts.filter((account) => account.health_status !== "HEALTHY").length} ${t("ops.actionItems.retryable").replace("retryable jobs", "degraded/held")}`}
              tone={state.queue.accounts.some((account) => account.health_status === "UNHEALTHY" || account.health_status === "HELD") ? "warn" : "good"}
            />
            <OpsMetricCard
              label={t("ops.assets")}
              value={String(state.metrics.asset_reuse_by_type.length)}
              detail={t("ops.metrics.assetsDetail")}
            />
            <OpsMetricCard
              label={t("ops.risk")}
              value={String(sumRecord(state.metrics.open_risk_counts_by_severity))}
              detail={t("ops.metrics.riskDetail")}
              tone={sumRecord(state.metrics.open_risk_counts_by_severity) > 0 ? "warn" : "good"}
            />
          </section>

          <section className="ops-grid">
            <OpsPanel title={t("ops.healthSection")}>
              <div className="studio-card-list">
                <OpsLink href="/ops/health" title={t("nav.systemHealth")} detail={t("nav.systemHealthDesc")} />
                <OpsLink href="/ops/jobs" title={t("ops.jobs")} detail={t("nav.jobMonitorDesc")} />
                <OpsLink href="/ops/assets" title={t("ops.assets")} detail={t("nav.assetStateDesc")} />
                <OpsLink href="/ops/publish-attempts" title={t("nav.publishAttempts")} detail={t("nav.publishAttemptsDesc")} />
                <OpsLink href="/ops/reconciliation" title={t("ops.reconciliation")} detail={t("nav.reconciliationDesc")} />
                <OpsLink href="/ops/accounts" title={t("ops.accounts")} detail={t("nav.accountsDesc")} />
                <OpsLink href="/ops/routing-rules" title={t("nav.routingRules")} detail={t("nav.routingRulesDesc")} />
                <OpsLink href="/ops/risk" title={t("ops.risk")} detail={t("nav.riskGatesDesc")} />
                <OpsLink
                  href="/ops/translation-ai"
                  title={t("nav.translationSettings")}
                  detail={t("nav.translationSettingsDesc")}
                />
                <OpsLink
                  href="/ops/caption-ai"
                  title={t("nav.captionAiSettings")}
                  detail={t("nav.captionAiSettingsDesc")}
                />
                <OpsLink
                  href="/ops/tts-ai"
                  title={t("nav.ttsSettings")}
                  detail={t("nav.ttsSettingsDesc")}
                />
                <OpsLink href="/ops/tools" title={t("nav.tools")} detail={t("nav.toolsDesc")} />
              </div>
            </OpsPanel>

            <OpsPanel title={t("ops.fetchHealthSection")}>
              <ul className="compact-list">
                <li><strong>{state.metrics.douyin_fetch_health.window_runs}</strong><span> {t("ops.fetchHealthWindowRuns")}</span></li>
                <li><strong>{state.metrics.douyin_fetch_health.blocked_runs}</strong><span> {t("ops.fetchHealthBlockedRuns")}</span></li>
                <li><strong>{state.metrics.douyin_fetch_health.parse_warning_runs}</strong><span> {t("ops.fetchHealthParseWarnings")}</span></li>
                <li><strong>{state.metrics.douyin_fetch_health.failed_runs}</strong><span> {t("ops.fetchHealthFailedRuns")}</span></li>
                <li><strong>{state.metrics.douyin_fetch_health.blocked_ratio_percent}%</strong><span> {t("ops.fetchHealthBlockedRatio")}</span></li>
              </ul>
              <dl className="metadata-list">
                <div>
                  <dt>{t("ops.fetchHealthTopBlockedReasons")}</dt>
                  <dd>
                    {state.metrics.douyin_fetch_health.top_blocked_reasons.length > 0
                      ? state.metrics.douyin_fetch_health.top_blocked_reasons
                          .map((item) => `${item.reason} (${item.count})`)
                          .join(", ")
                      : t("ops.fetchHealthNoBlockedReasons")}
                  </dd>
                </div>
                <div>
                  <dt>{t("ops.fetchHealthAccountsCovered")}</dt>
                  <dd>{state.metrics.douyin_fetch_health.by_account.length}</dd>
                </div>
              </dl>
            </OpsPanel>

            <OpsPanel title={t("ops.actionQueue")}>
              <ul className="compact-list">
                <li><strong>{state.metrics.queue_backlog.running}</strong><span> {t("ops.actionItems.running")}</span></li>
                <li><strong>{state.metrics.retryable_jobs}</strong><span> {t("ops.actionItems.retryable")}</span></li>
                <li><strong>{state.publishHealth.overview.needs_reconciliation_attempts}</strong><span> {t("ops.actionItems.needsReconciliation")}</span></li>
                <li><strong>{state.queue.unassigned_drafts.length}</strong><span> {t("ops.actionItems.unassignedDrafts")}</span></li>
                <li><strong>{state.queue.needs_attention.length}</strong><span> {t("ops.actionItems.needsRouting")}</span></li>
              </ul>
            </OpsPanel>

            <OpsPanel title={t("ops.lastGenerated")}>
              <dl className="metadata-list">
                <div><dt>{t("ops.opsMetrics")}</dt><dd>{formatDateTime(state.metrics.generated_at)}</dd></div>
                <div><dt>{t("ops.publishHealth")}</dt><dd>{formatDateTime(state.publishHealth.generated_at)}</dd></div>
                <div><dt>{t("ops.controlQueue")}</dt><dd>{formatDateTime(state.queue.generated_at)}</dd></div>
              </dl>
            </OpsPanel>
          </section>
        </>
      ) : null}
    </main>
  );
}

function OpsLink({ href, title, detail }: { href: string; title: string; detail: string }) {
  return (
    <a className="studio-card" href={href}>
      <span>
        <strong>{title}</strong>
        <small>{detail}</small>
      </span>
    </a>
  );
}
