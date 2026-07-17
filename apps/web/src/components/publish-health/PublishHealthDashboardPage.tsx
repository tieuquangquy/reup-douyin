"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useT } from "../../lib/i18n";
import { fetchPublishHealthDashboard, submitOperatorFeedback } from "../../lib/api";
import { buildFeedbackPayload, healthStatusLabel, needsAttentionCount } from "../../lib/publishHealthState";
import { humanizeStatus } from "../../lib/statusLabels";
import type { AnalyticsWindow, PublicationOutcomeItem, PublishHealthDashboard } from "../../types/analytics";

const windows: AnalyticsWindow[] = ["today", "last_7_days", "last_30_days"];

export function PublishHealthDashboardPage() {
  const t = useT();
  const [windowValue, setWindowValue] = useState<AnalyticsWindow>("last_7_days");
  const [snapshot, setSnapshot] = useState<PublishHealthDashboard | null>(null);
  const [selectedPublication, setSelectedPublication] = useState<PublicationOutcomeItem | null>(null);
  const [qualityLabel, setQualityLabel] = useState("GOOD");
  const [confidence, setConfidence] = useState("SCALABLE");
  const [rootCause, setRootCause] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await fetchPublishHealthDashboard(windowValue));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishHealthPage.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  const statusLabel = useMemo(() => (snapshot ? healthStatusLabel(snapshot) : "Loading"), [snapshot]);

  async function handleFeedbackSubmit() {
    if (!selectedPublication) return;
    setSaving(true);
    setError(null);
    try {
      await submitOperatorFeedback(
        buildFeedbackPayload(selectedPublication, {
          qualityLabel,
          confidence,
          rootCause,
          note
        })
      );
      setMessage(t("publishHealthPage.feedbackSuccess"));
      setNote("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishHealthPage.saveError"));
    } finally {
      setSaving(false);
    }
  }

  if (loading && !snapshot) {
    return <main className="health-page"><div className="state-panel skeleton">{t("publishHealthPage.loading")}</div></main>;
  }

  if (error && !snapshot) {
    return (
      <main className="health-page">
        <div className="state-panel">
          <h1>{t("publishHealthPage.unavailable")}</h1>
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>{t("publishHealthPage.retry")}</button>
        </div>
      </main>
    );
  }

  return (
    <main className="health-page">
      <header className="health-header">
        <div>
          <span className="eyebrow">{t("publishHealthPage.operations")}</span>
          <h1>{t("publishHealthPage.pageTitle")}</h1>
          <p>{t("publishHealthPage.pageDesc")}</p>
        </div>
        <div className="health-header-actions">
          <select value={windowValue} onChange={(event) => setWindowValue(event.target.value as AnalyticsWindow)}>
            {windows.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
          </select>
          <button type="button" onClick={() => void load()}>{t("publishHealthPage.refresh")}</button>
        </div>
      </header>

      {error ? <div className="inline-error">{error}</div> : null}
      {message ? <div className="publish-ready-banner">{message}</div> : null}

      {snapshot ? (
        <>
          <section className="health-overview-grid">
            <MetricCard label={t("publishHealthPage.statusLabel")} value={statusLabel} detail={`${needsAttentionCount(snapshot)} ${t("publishHealthPage.needsAttentionItems")}`} />
            <MetricCard label={t("publishHealthPage.successRate")} value={`${snapshot.overview.success_rate_percent}%`} detail={`${snapshot.overview.succeeded_attempts}/${snapshot.overview.total_attempts} ${t("publishHealthPage.attemptsOf")}`} />
            <MetricCard label={t("publishHealthPage.published")} value={snapshot.overview.canonical_published_count.toString()} detail={t("publishHealthPage.canonicalPublications")} />
            <MetricCard label={t("publishHealthPage.reconcile")} value={snapshot.overview.needs_reconciliation_attempts.toString()} detail={t("publishHealthPage.attemptsNeedCheck")} />
            <MetricCard label={t("publishHealthPage.readyBacklog")} value={snapshot.overview.drafts_ready_not_published.toString()} detail={t("publishHealthPage.draftsReady")} />
            <MetricCard label={t("publishHealthPage.riskBlocked")} value={snapshot.overview.drafts_blocked_by_risk.toString()} detail={t("publishHealthPage.publishBlocked")} />
          </section>

          <section className="health-layout">
            <div className="health-main">
              <Panel title={t("publishHealthPage.accountPageHealth")}>
                <table className="health-table">
                  <thead>
                    <tr><th>{t("publishHealthPage.account")}</th><th>{t("publishHealthPage.attempts")}</th><th>{t("publishHealthPage.success")}</th><th>{t("publishHealthPage.failed")}</th><th>{t("publishHealthPage.reconcile")}</th><th>{t("publishHealthPage.recentError")}</th></tr>
                  </thead>
                  <tbody>
                    {snapshot.account_health.length === 0 ? <tr><td colSpan={6}>{t("publishHealthPage.noAccountAttempts")}</td></tr> : null}
                    {snapshot.account_health.map((account) => (
                      <tr key={account.platform_account_id ?? account.display_name}>
                        <td>{account.display_name}</td>
                        <td>{account.attempts}</td>
                        <td>{account.success_rate_percent}%</td>
                        <td>{account.failed}</td>
                        <td>{account.needs_reconciliation}</td>
                        <td>{account.recent_error_code ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>

              <Panel title={t("publishHealthPage.pipelineHints")}>
                <div className="health-column-grid">
                  <FeedbackGroup title={t("publishHealthPage.bySource")} groups={snapshot.pipeline_feedback.by_source_profile} />
                  <FeedbackGroup title={t("publishHealthPage.byPreset")} groups={snapshot.pipeline_feedback.by_preset} />
                  <FeedbackGroup title={t("publishHealthPage.byNiche")} groups={snapshot.pipeline_feedback.by_niche} />
                </div>
              </Panel>

              <Panel title={t("publishHealthPage.recentSuccess")}>
                <PublicationList
                  items={snapshot.action_queue.recent_successes}
                  empty={t("publishHealthPage.noRecentSuccess")}
                  onFeedback={setSelectedPublication}
                />
              </Panel>
            </div>

            <aside className="health-side">
              <Panel title={t("publishHealthPage.operatorQueue")}>
                <h3>{t("publishHealthPage.needsReconciliation")}</h3>
                <PublicationList items={snapshot.action_queue.needs_reconciliation} empty={t("publishHealthPage.noReconciliationBacklog")} compact />
                <h3>{t("publishHealthPage.readyPublish")}</h3>
                <PublicationList items={snapshot.action_queue.drafts_ready} empty={t("publishHealthPage.noReadyBacklog")} compact />
              </Panel>

              <Panel title={t("publishHealthPage.failureInsights")}>
                {snapshot.failure_categories.length === 0 ? <p className="muted">{t("publishHealthPage.noFailures")}</p> : null}
                <ul className="compact-list">
                  {snapshot.failure_categories.map((item) => (
                    <li key={item.error_code}>{item.label}: {item.count}</li>
                  ))}
                </ul>
              </Panel>

              <Panel title={t("publishHealthPage.feedback")}>
                {selectedPublication ? (
                  <div className="feedback-form">
                    <div className="small-meta">{t("publishHealthPage.draft")} {selectedPublication.publish_draft_id.slice(0, 8)}</div>
                    <label>{t("publishHealthPage.quality")}
                      <select value={qualityLabel} onChange={(event) => setQualityLabel(event.target.value)}>
                        <option value="GOOD">{t("publishHealthPage.good")}</option>
                        <option value="ACCEPTABLE">{t("publishHealthPage.acceptable")}</option>
                        <option value="WEAK">{t("publishHealthPage.weak")}</option>
                      </select>
                    </label>
                    <label>{t("publishHealthPage.confidence")}
                      <select value={confidence} onChange={(event) => setConfidence(event.target.value)}>
                        <option value="SCALABLE">{t("publishHealthPage.scalable")}</option>
                        <option value="NEEDS_IMPROVEMENT">{t("publishHealthPage.needsImprovement")}</option>
                        <option value="DO_NOT_REUSE_PATTERN">{t("publishHealthPage.doNotReuse")}</option>
                      </select>
                    </label>
                    <label>{t("publishHealthPage.rootCause")}
                      <select value={rootCause} onChange={(event) => setRootCause(event.target.value)}>
                        <option value="">{t("publishHealthPage.none")}</option>
                        <option value="SOURCE_SELECTION_ISSUE">{t("publishHealthPage.sourceSelection")}</option>
                        <option value="TRANSCRIPT_QUALITY_ISSUE">{t("publishHealthPage.transcriptQuality")}</option>
                        <option value="TTS_ISSUE">{t("publishHealthPage.tts")}</option>
                        <option value="SUBTITLE_ISSUE">{t("publishHealthPage.subtitle")}</option>
                        <option value="RENDER_ISSUE">{t("publishHealthPage.render")}</option>
                        <option value="PUBLISH_ISSUE">{t("publishHealthPage.publish")}</option>
                        <option value="RISK_FALSE_POSITIVE">{t("publishHealthPage.riskFalsePositive")}</option>
                        <option value="CTA_CAPTION_ISSUE">{t("publishHealthPage.ctaCaption")}</option>
                        <option value="OTHER">{t("publishHealthPage.other")}</option>
                      </select>
                    </label>
                    <label>{t("publishHealthPage.note")}
                      <textarea value={note} rows={4} onChange={(event) => setNote(event.target.value)} />
                    </label>
                    <button className="primary" type="button" disabled={saving} onClick={() => void handleFeedbackSubmit()}>
                      {saving ? t("publishHealthPage.saving") : t("publishHealthPage.saveFeedback")}
                    </button>
                  </div>
                ) : (
                  <p className="muted">{t("publishHealthPage.selectPublication")}</p>
                )}
              </Panel>
            </aside>
          </section>
        </>
      ) : null}
    </main>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="health-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="health-panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function FeedbackGroup({ title, groups }: { title: string; groups: PublishHealthDashboard["pipeline_feedback"]["by_source_profile"] }) {
  const t = useT();
  return (
    <div>
      <h3>{title}</h3>
      <ul className="compact-list">
        {groups.length === 0 ? <li>{t("publishHealthPage.noData")}</li> : null}
        {groups.slice(0, 5).map((group) => (
          <li key={group.group_key}>
            {group.label}: {group.published_count} {t("publishHealthPage.published")}, {group.good_feedback_count} {t("publishHealthPage.good")}, {group.weak_feedback_count} {t("publishHealthPage.weak")}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PublicationList({
  items,
  empty,
  compact,
  onFeedback
}: {
  items: PublicationOutcomeItem[];
  empty: string;
  compact?: boolean;
  onFeedback?: (item: PublicationOutcomeItem) => void;
}) {
  const t = useT();
  if (items.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className={compact ? "compact-list" : "publication-list"}>
      {items.map((item) => (
        <li key={item.publish_draft_id}>
          <div>
            <strong>{item.source_profile_name ?? t("publishHealthPage.unknownSource")}</strong>
            <span>{humanizeStatus(item.status)} / {humanizeStatus(item.external_status)}</span>
            <small>{item.preset_name ?? t("publishHealthPage.noPreset")} - {t("publishHealthPage.score")} {item.score ?? "-"}</small>
          </div>
          <a href={`/publishing/drafts/${item.publish_draft_id}`}>{t("publishHealthPage.openDraft")}</a>
          {item.external_permalink ? <a href={item.external_permalink} target="_blank" rel="noreferrer">{t("publishHealthPage.open")}</a> : null}
          {onFeedback ? <button type="button" onClick={() => onFeedback(item)}>{t("publishHealthPage.feedbackButton")}</button> : null}
        </li>
      ))}
    </ul>
  );
}
