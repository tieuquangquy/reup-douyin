"use client";

import { useEffect, useState } from "react";
import { fetchPublishControlQueue, fetchRoutingRules } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PublishControlQueue, RoutingRule } from "../../types/publish-control";
import { StatusBadge } from "../app-shell/StatusBadge";
import { OpsMetricCard, OpsPageHeader, OpsPanel, OpsState, statusTone } from "./OpsShared";

export function OpsRoutingRulesPage() {
  const t = useT();
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [rulesPayload, queuePayload] = await Promise.all([fetchRoutingRules(), fetchPublishControlQueue()]);
      setRules(rulesPayload.rules);
      setQueue(queuePayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsRoutingRules.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  if (loading && rules.length === 0) return <OpsState title={t("opsRoutingRules.loadingTitle")} detail={t("opsRoutingRules.loadingDetail")} />;
  if (error && rules.length === 0) return <OpsState title={t("opsRoutingRules.unavailableTitle")} detail={error} retry={() => void load()} />;

  return (
    <main className="ops-page">
      <OpsPageHeader title={t("opsRoutingRules.title")} description={t("opsRoutingRules.description")} actions={<><a href="/ops/publish-control">{t("opsAccounts.openPublishControl")}</a><button type="button" onClick={() => void load()}>{t("common.refresh")}</button></>} />
      {error ? <div className="inline-error">{error}</div> : null}

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
  );
}
