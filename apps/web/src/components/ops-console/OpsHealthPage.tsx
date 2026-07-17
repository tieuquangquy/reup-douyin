"use client";

import { useEffect, useState } from "react";
import { fetchOperationalMetrics, fetchPublishHealthDashboard } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PublishHealthDashboard } from "../../types/analytics";
import type { OperationalMetrics } from "../../types/operations";
import { OpsMetricCard, OpsPageHeader, OpsPanel, OpsState, formatDateTime, sumRecord } from "./OpsShared";

export function OpsHealthPage() {
  const t = useT();
  const [metrics, setMetrics] = useState<OperationalMetrics | null>(null);
  const [publishHealth, setPublishHealth] = useState<PublishHealthDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [metricsPayload, healthPayload] = await Promise.all([
        fetchOperationalMetrics(),
        fetchPublishHealthDashboard("last_7_days")
      ]);
      setMetrics(metricsPayload);
      setPublishHealth(healthPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsHealth.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  if (loading && !metrics) return <OpsState title={t("opsHealth.loadingTitle")} detail={t("opsHealth.loadingDetail")} />;
  if (error && !metrics) return <OpsState title={t("opsHealth.unavailableTitle")} detail={error} retry={() => void load()} />;

  return (
    <main className="ops-page">
      <OpsPageHeader title={t("opsHealth.title")} description={t("opsHealth.description")} actions={<button type="button" onClick={() => void load()}>{t("common.refresh")}</button>} />
      {error ? <div className="inline-error">{error}</div> : null}
      {metrics ? (
        <>
          <section className="health-overview-grid">
            <OpsMetricCard label={t("opsHealth.api")} value={t("opsHealth.reachable")} detail={t("opsHealth.loadedOpsMetrics")} tone="good" />
            <OpsMetricCard label={t("opsHealth.db")} value={t("opsHealth.reachable")} detail={t("opsHealth.metricsQueryCompleted")} tone="good" />
            <OpsMetricCard label={t("opsHealth.worker")} value={metrics.queue_backlog.running > 0 ? t("opsHealth.active") : t("opsHealth.noActiveJobs")} detail={`${metrics.queue_backlog.running} ${t("opsHealth.runningJobs")}`} tone={metrics.queue_backlog.running > 0 ? "good" : "muted"} />
            <OpsMetricCard label={t("opsHealth.redis")} value={t("opsHealth.notExposed")} detail={t("opsHealth.noDedicatedRedisEndpoint")} />
            <OpsMetricCard label={t("opsHealth.storage")} value={`${metrics.asset_reuse_by_type.length} types`} detail={t("opsHealth.assetRecordsVisible")} tone="good" />
            <OpsMetricCard label={t("opsHealth.risk")} value={String(sumRecord(metrics.open_risk_counts_by_severity))} detail={t("opsHealth.openWarnings")} tone={sumRecord(metrics.open_risk_counts_by_severity) > 0 ? "warn" : "good"} />
          </section>

          <section className="ops-grid">
            <OpsPanel title={t("opsHealth.queueBacklog")}>
              <dl className="metadata-list">
                <div><dt>{t("opsHealth.queued")}</dt><dd>{metrics.queue_backlog.queued}</dd></div>
                <div><dt>{t("opsHealth.running")}</dt><dd>{metrics.queue_backlog.running}</dd></div>
                <div><dt>{t("opsHealth.retryable")}</dt><dd>{metrics.queue_backlog.retryable}</dd></div>
                <div><dt>{t("opsHealth.totalRetryAttempts")}</dt><dd>{metrics.total_retry_attempts}</dd></div>
              </dl>
            </OpsPanel>
            <OpsPanel title={t("opsHealth.pipelineOutputs")}>
              <dl className="metadata-list">
                <div><dt>{t("opsHealth.renders")}</dt><dd>{JSON.stringify(metrics.render_counts_by_status)}</dd></div>
                <div><dt>{t("opsHealth.publishDrafts")}</dt><dd>{JSON.stringify(metrics.publish_draft_counts_by_status)}</dd></div>
                <div><dt>{t("opsHealth.publishGenerated")}</dt><dd>{publishHealth ? formatDateTime(publishHealth.generated_at) : "-"}</dd></div>
              </dl>
            </OpsPanel>
            <OpsPanel title={t("opsHealth.knownGaps")}>
              <ul className="compact-list">
                <li>{t("opsHealth.gapRedis")}</li>
                <li>{t("opsHealth.gapWorker")}</li>
                <li>{t("opsHealth.gapStorage")}</li>
              </ul>
            </OpsPanel>
          </section>
        </>
      ) : null}
    </main>
  );
}
