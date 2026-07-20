"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchPublishHealthDashboard, submitOperatorFeedback } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { buildFeedbackPayload, healthStatusLabel, needsAttentionCount } from "../../lib/publishHealthState";
import { humanizeStatus } from "../../lib/statusLabels";
import type { AnalyticsWindow, PublicationOutcomeItem, PublishHealthDashboard } from "../../types/analytics";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { OpsState, formatDateTime, type OpsTone } from "../ops-console/OpsShared";

const windows: AnalyticsWindow[] = ["today", "last_7_days", "last_30_days"];

function PhKpi({
  label,
  value,
  detail,
  tone = "muted",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: OpsTone;
}) {
  return (
    <article className={`ops-ph-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function PhPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-ph-panel">
      <div className="ops-ph-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-ph-panel__body">{children}</div>
    </section>
  );
}

function windowLabel(value: AnalyticsWindow, t: (key: string) => string): string {
  if (value === "today") return t("publishHealthPage.windowToday");
  if (value === "last_7_days") return t("publishHealthPage.window7d");
  return t("publishHealthPage.window30d");
}

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
  }, [windowValue, t]);

  const statusLabel = useMemo(() => (snapshot ? healthStatusLabel(snapshot) : "—"), [snapshot]);
  const attention = snapshot ? needsAttentionCount(snapshot) : 0;

  async function handleFeedbackSubmit() {
    if (!selectedPublication) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await submitOperatorFeedback(
        buildFeedbackPayload(selectedPublication, {
          qualityLabel,
          confidence,
          rootCause,
          note,
        }),
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

  const refreshAction = (
    <TopbarRefreshButton busy={loading && Boolean(snapshot)} disabled={loading && !snapshot} onClick={() => void load()} />
  );

  if (loading && !snapshot) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("publishHealthPage.pageDesc")} title={t("publishHealthPage.pageTitle")}>
        <OpsState title={t("publishHealthPage.loading")} detail={t("publishHealthPage.loadingDetail")} />
      </OpsConsoleShell>
    );
  }

  if (error && !snapshot) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("publishHealthPage.pageDesc")} title={t("publishHealthPage.pageTitle")}>
        <OpsState title={t("publishHealthPage.unavailable")} detail={error} retry={() => void load()} />
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("publishHealthPage.pageDesc")} title={t("publishHealthPage.pageTitle")}>
      <main className="ops-page ops-ph-page">
        {error ? <div className="inline-error">{error}</div> : null}
        {message ? <div className="ops-ph-notice">{message}</div> : null}

        <p className="ops-ph-freshness">
          {t("publishHealthPage.metricsGenerated")}{" "}
          <time dateTime={snapshot?.generated_at}>{formatDateTime(snapshot?.generated_at)}</time>
          <span className="ops-ph-freshness__sep">·</span>
          {windowLabel(windowValue, t)}
        </p>

        {snapshot ? (
          <>
            <section className="ops-ph-kpis" aria-label={t("publishHealthPage.pageTitle")}>
              <PhKpi
                label={t("publishHealthPage.statusLabel")}
                value={statusLabel}
                detail={`${attention} ${t("publishHealthPage.needsAttentionItems")}`}
                tone={attention > 0 ? "warn" : "good"}
              />
              <PhKpi
                label={t("publishHealthPage.successRate")}
                value={`${snapshot.overview.success_rate_percent}%`}
                detail={`${snapshot.overview.succeeded_attempts}/${snapshot.overview.total_attempts} ${t("publishHealthPage.attemptsOf")}`}
                tone="muted"
              />
              <PhKpi
                label={t("publishHealthPage.published")}
                value={String(snapshot.overview.canonical_published_count)}
                detail={t("publishHealthPage.canonicalPublications")}
                tone="good"
              />
              <PhKpi
                label={t("publishHealthPage.reconcile")}
                value={String(snapshot.overview.needs_reconciliation_attempts)}
                detail={t("publishHealthPage.attemptsNeedCheck")}
                tone={snapshot.overview.needs_reconciliation_attempts > 0 ? "warn" : "good"}
              />
              <PhKpi
                label={t("publishHealthPage.readyBacklog")}
                value={String(snapshot.overview.drafts_ready_not_published)}
                detail={t("publishHealthPage.draftsReady")}
                tone="muted"
              />
              <PhKpi
                label={t("publishHealthPage.riskBlocked")}
                value={String(snapshot.overview.drafts_blocked_by_risk)}
                detail={t("publishHealthPage.publishBlocked")}
                tone={snapshot.overview.drafts_blocked_by_risk > 0 ? "danger" : "good"}
              />
            </section>

            <div className="ops-ph-toolbar">
              <label className="ops-ph-window">
                <span>{t("publishHealthPage.window")}</span>
                <select
                  aria-label={t("publishHealthPage.window")}
                  value={windowValue}
                  onChange={(event) => setWindowValue(event.target.value as AnalyticsWindow)}
                >
                  {windows.map((item) => (
                    <option key={item} value={item}>
                      {windowLabel(item, t)}
                    </option>
                  ))}
                </select>
              </label>
              <nav className="ops-ph-actions" aria-label={t("publishHealthPage.triage")}>
                <Link href="/ops/reconciliation">{t("publishHealthPage.openReconciliation")}</Link>
                <Link href="/ops/accounts">{t("publishHealthPage.openAccounts")}</Link>
              </nav>
            </div>

            <section className="ops-ph-layout">
              <div className="ops-ph-main">
                <PhPanel title={t("publishHealthPage.accountPageHealth")}>
                  {snapshot.account_health.length === 0 ? (
                    <p className="ops-ph-empty">{t("publishHealthPage.noAccountAttempts")}</p>
                  ) : (
                    <ul className="ops-ph-sheet ops-ph-account">
                      <li className="ops-ph-row is-head" aria-hidden="true">
                        <span>{t("publishHealthPage.account")}</span>
                        <span>{t("publishHealthPage.attempts")}</span>
                        <span>{t("publishHealthPage.success")}</span>
                        <span>{t("publishHealthPage.failed")}</span>
                        <span>{t("publishHealthPage.reconcile")}</span>
                        <span>{t("publishHealthPage.recentError")}</span>
                      </li>
                      {snapshot.account_health.map((account) => (
                        <li className="ops-ph-row" key={account.platform_account_id ?? account.display_name}>
                          <strong className="ops-ph-row__title">{account.display_name}</strong>
                          <span>{account.attempts}</span>
                          <span>{account.success_rate_percent}%</span>
                          <span>{account.failed}</span>
                          <span>{account.needs_reconciliation}</span>
                          <span className="ops-ph-row__id">{account.recent_error_code ?? "—"}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </PhPanel>

                <PhPanel title={t("publishHealthPage.recentSuccess")}>
                  <PublicationList
                    items={snapshot.action_queue.recent_successes}
                    empty={t("publishHealthPage.noRecentSuccess")}
                    onFeedback={setSelectedPublication}
                  />
                </PhPanel>

                <PhPanel title={t("publishHealthPage.pipelineHints")}>
                  <div className="ops-ph-pipeline">
                    <FeedbackGroup title={t("publishHealthPage.bySource")} groups={snapshot.pipeline_feedback.by_source_profile} />
                    <FeedbackGroup title={t("publishHealthPage.byPreset")} groups={snapshot.pipeline_feedback.by_preset} />
                    <FeedbackGroup title={t("publishHealthPage.byNiche")} groups={snapshot.pipeline_feedback.by_niche} />
                  </div>
                </PhPanel>
              </div>

              <aside className="ops-ph-side">
                <PhPanel title={t("publishHealthPage.operatorQueue")}>
                  <div className="ops-ph-queue">
                    <h3>{t("publishHealthPage.needsReconciliation")}</h3>
                    <PublicationList
                      items={snapshot.action_queue.needs_reconciliation}
                      empty={t("publishHealthPage.noReconciliationBacklog")}
                      compact
                    />
                    <h3>{t("publishHealthPage.readyPublish")}</h3>
                    <PublicationList items={snapshot.action_queue.drafts_ready} empty={t("publishHealthPage.noReadyBacklog")} compact />
                  </div>
                </PhPanel>

                <PhPanel title={t("publishHealthPage.failureInsights")}>
                  {snapshot.failure_categories.length === 0 ? (
                    <p className="ops-ph-empty">{t("publishHealthPage.noFailures")}</p>
                  ) : (
                    <ul className="ops-ph-failures">
                      {snapshot.failure_categories.map((item) => (
                        <li key={item.error_code}>
                          <span>{item.label}</span>
                          <strong>{item.count}</strong>
                        </li>
                      ))}
                    </ul>
                  )}
                </PhPanel>

                <PhPanel title={t("publishHealthPage.feedback")}>
                  {selectedPublication ? (
                    <div className="ops-ph-feedback">
                      <p className="ops-ph-feedback__meta">
                        {t("publishHealthPage.draft")} {selectedPublication.publish_draft_id.slice(0, 8)}
                      </p>
                      <label>
                        {t("publishHealthPage.quality")}
                        <select value={qualityLabel} onChange={(event) => setQualityLabel(event.target.value)}>
                          <option value="GOOD">{t("publishHealthPage.good")}</option>
                          <option value="ACCEPTABLE">{t("publishHealthPage.acceptable")}</option>
                          <option value="WEAK">{t("publishHealthPage.weak")}</option>
                        </select>
                      </label>
                      <label>
                        {t("publishHealthPage.confidence")}
                        <select value={confidence} onChange={(event) => setConfidence(event.target.value)}>
                          <option value="SCALABLE">{t("publishHealthPage.scalable")}</option>
                          <option value="NEEDS_IMPROVEMENT">{t("publishHealthPage.needsImprovement")}</option>
                          <option value="DO_NOT_REUSE_PATTERN">{t("publishHealthPage.doNotReuse")}</option>
                        </select>
                      </label>
                      <label>
                        {t("publishHealthPage.rootCause")}
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
                      <label>
                        {t("publishHealthPage.note")}
                        <textarea value={note} rows={4} onChange={(event) => setNote(event.target.value)} />
                      </label>
                      <button className="primary" type="button" disabled={saving} onClick={() => void handleFeedbackSubmit()}>
                        {saving ? t("publishHealthPage.saving") : t("publishHealthPage.saveFeedback")}
                      </button>
                    </div>
                  ) : (
                    <p className="ops-ph-empty">{t("publishHealthPage.selectPublication")}</p>
                  )}
                </PhPanel>
              </aside>
            </section>
          </>
        ) : null}
      </main>
    </OpsConsoleShell>
  );
}

function FeedbackGroup({
  title,
  groups,
}: {
  title: string;
  groups: PublishHealthDashboard["pipeline_feedback"]["by_source_profile"];
}) {
  const t = useT();
  return (
    <div className="ops-ph-pipeline__group">
      <h3>{title}</h3>
      <ul>
        {groups.length === 0 ? <li className="ops-ph-empty">{t("publishHealthPage.noData")}</li> : null}
        {groups.slice(0, 5).map((group) => (
          <li key={group.group_key}>
            <strong>{group.label}</strong>
            <span>
              {group.published_count} {t("publishHealthPage.published")} · {group.good_feedback_count}{" "}
              {t("publishHealthPage.good")} · {group.weak_feedback_count} {t("publishHealthPage.weak")}
            </span>
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
  onFeedback,
}: {
  items: PublicationOutcomeItem[];
  empty: string;
  compact?: boolean;
  onFeedback?: (item: PublicationOutcomeItem) => void;
}) {
  const t = useT();
  if (items.length === 0) return <p className="ops-ph-empty">{empty}</p>;
  return (
    <ul className={`ops-ph-publications${compact ? " is-compact" : ""}`}>
      {items.map((item) => (
        <li key={item.publish_draft_id}>
          <div>
            <strong>{item.source_profile_name ?? t("publishHealthPage.unknownSource")}</strong>
            <span>
              {humanizeStatus(item.status)} / {humanizeStatus(item.external_status)}
            </span>
            <em>
              {item.preset_name ?? t("publishHealthPage.noPreset")} · {t("publishHealthPage.score")} {item.score ?? "—"}
            </em>
          </div>
          <div className="ops-ph-publications__actions">
            <Link href={`/publishing/drafts/${item.publish_draft_id}`}>{t("publishHealthPage.openDraft")}</Link>
            {item.external_permalink ? (
              <a href={item.external_permalink} target="_blank" rel="noreferrer">
                {t("publishHealthPage.open")}
              </a>
            ) : null}
            {onFeedback ? (
              <button type="button" onClick={() => onFeedback(item)}>
                {t("publishHealthPage.feedbackButton")}
              </button>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
