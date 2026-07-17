"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useT } from "../../lib/i18n";
import { fetchOptimizationDashboard, fetchOptimizationSchedulingHints } from "../../lib/api";
import { automationReadinessLabel, groupTone, optimizationHeadline } from "../../lib/optimizationState";
import type { OptimizationDashboard, OutcomeGroupSummary, RoutingHints, SchedulingHints } from "../../types/optimization";

export function OptimizationPage() {
  const t = useT();
  const [snapshot, setSnapshot] = useState<OptimizationDashboard | null>(null);
  const [selectedSchedule, setSelectedSchedule] = useState<SchedulingHints | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingScheduleId, setLoadingScheduleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await fetchOptimizationDashboard());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("optimizationPage.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  async function loadScheduleHint(draftId: string) {
    setLoadingScheduleId(draftId);
    setError(null);
    try {
      setSelectedSchedule(await fetchOptimizationSchedulingHints(draftId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("optimizationPage.scheduleHintError"));
    } finally {
      setLoadingScheduleId(null);
    }
  }

  if (loading && !snapshot) {
    return <main className="optimization-page"><div className="state-panel skeleton">{t("optimizationPage.loading")}</div></main>;
  }

  if (error && !snapshot) {
    return (
      <main className="optimization-page">
        <div className="state-panel">
          <h1>{t("optimizationPage.unavailable")}</h1>
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>{t("optimizationPage.retry")}</button>
        </div>
      </main>
    );
  }

  return (
    <main className="optimization-page">
      <header className="optimization-header">
        <div>
          <span className="eyebrow">{t("optimizationPage.operations")}</span>
          <h1>{t("optimizationPage.pageTitle")}</h1>
          <p>{snapshot ? optimizationHeadline(snapshot) : t("optimizationPage.feedbackLoopDesc")}</p>
        </div>
        <button type="button" onClick={() => void load()}>{t("optimizationPage.refresh")}</button>
      </header>

      {error ? <div className="inline-error">{error}</div> : null}

      {snapshot ? (
        <section className="optimization-layout">
          <div className="optimization-main">
            <Panel title={t("optimizationPage.outcomeOverview")}>
              <div className="optimization-grid">
                <GroupColumn title={t("optimizationPage.bySource")} groups={snapshot.outcome_summaries.by_source_profile} />
                <GroupColumn title={t("optimizationPage.byNiche")} groups={snapshot.outcome_summaries.by_niche} />
                <GroupColumn title={t("optimizationPage.byPreset")} groups={snapshot.outcome_summaries.by_preset} />
              </div>
            </Panel>

            <Panel title={t("optimizationPage.presetFeedback")}>
              <table className="health-table">
                <thead>
                  <tr><th>Preset</th><th>{t("optimizationPage.items")}</th><th>{t("optimizationPage.avgOutcome")}</th><th>{t("optimizationPage.strong")}</th><th>{t("optimizationPage.weak")}</th><th>{t("optimizationPage.hint")}</th></tr>
                </thead>
                <tbody>
                  {snapshot.preset_feedback.items.length === 0 ? <tr><td colSpan={6}>{t("optimizationPage.noPresetData")}</td></tr> : null}
                  {snapshot.preset_feedback.items.map((item) => (
                    <tr key={item.preset_name}>
                      <td>{item.preset_name}</td>
                      <td>{item.item_count}</td>
                      <td>{item.average_outcome_score ?? "-"}</td>
                      <td>{item.strong_count}</td>
                      <td>{item.weak_count}</td>
                      <td>{item.tuning_hints[0] ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            <Panel title={t("optimizationPage.routingHints")}>
              <div className="routing-hint-list">
                {snapshot.ready_draft_routing_hints.length === 0 ? <p className="muted">{t("optimizationPage.noRoutingHints")}</p> : null}
                {snapshot.ready_draft_routing_hints.map((hint) => (
                  <RoutingHintCard key={hint.publish_draft_id} hint={hint} loadingScheduleId={loadingScheduleId} onSchedule={loadScheduleHint} />
                ))}
              </div>
            </Panel>
          </div>

          <aside className="optimization-side">
            <Panel title={t("optimizationPage.manualHotspots")}>
              <ul className="compact-list">
                {snapshot.manual_touch_summary.hotspots.map((item) => (
                  <li key={item.area}>
                    <strong>{item.area.replaceAll("_", " ")}</strong>
                    <span>{item.count} signals / {item.severity}</span>
                    <small>{item.hint}</small>
                  </li>
                ))}
              </ul>
            </Panel>

            <Panel title={t("optimizationPage.schedulingHints")}>
              {selectedSchedule ? (
                <div className="schedule-hints">
                  <span className="small-meta">{t("optimizationPage.draft")} {selectedSchedule.publish_draft_id.slice(0, 8)}</span>
                  {selectedSchedule.suggested_slots.map((slot) => (
                    <div className="schedule-slot" key={`${slot.platform_account_id ?? "manual"}-${slot.suggested_publish_at}`}>
                      <strong>{new Date(slot.suggested_publish_at).toLocaleString()}</strong>
                      <span>{slot.account_name ?? t("optimizationPage.chooseManually")} / {slot.confidence_label}</span>
                      <small>{slot.reasons[0]}</small>
                      {slot.warnings[0] ? <small className="warning-text">{slot.warnings[0]}</small> : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">{t("optimizationPage.selectRoutingHint")}</p>
              )}
            </Panel>

            <Panel title={t("optimizationPage.guardrailSummary")}>
              <p className="muted">
                {t("optimizationPage.guardrailDesc")}
              </p>
            </Panel>
          </aside>
        </section>
      ) : null}
    </main>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="health-panel"><h2>{title}</h2>{children}</section>;
}

function GroupColumn({ title, groups }: { title: string; groups: OutcomeGroupSummary[] }) {
  const t = useT();
  return (
    <div>
      <h3>{title}</h3>
      <ul className="compact-list">
        {groups.length === 0 ? <li>{t("optimizationPage.noDataYet")}</li> : null}
        {groups.slice(0, 6).map((group) => (
          <li key={group.group_key} className="optimization-group-row">
            <span className={`pill ${groupTone(group)}`}>{group.average_outcome_score ?? "-"}</span>
            <div>
              <strong>{group.label}</strong>
              <small>{group.item_count} {t("optimizationPage.itemsCount")}, {group.strong_count} {t("optimizationPage.strongCount")}, {group.weak_count} {t("optimizationPage.weakCount")}</small>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RoutingHintCard({
  hint,
  loadingScheduleId,
  onSchedule
}: {
  hint: RoutingHints;
  loadingScheduleId: string | null;
  onSchedule: (draftId: string) => Promise<void>;
}) {
  const t = useT();
  const top = hint.recommended_accounts[0];
  return (
    <div className="routing-hint-card">
      <div>
        <strong>{t("optimizationPage.draft")} {hint.publish_draft_id.slice(0, 8)}</strong>
        <span className="pill">{automationReadinessLabel(hint)}</span>
      </div>
      {top ? (
        <>
          <p><strong>{top.display_name}</strong> / {top.confidence_label} / {top.confidence_score}</p>
          <small>{top.reasons[0] ?? t("optimizationPage.noReason")}</small>
        </>
      ) : (
        <p className="muted">{t("optimizationPage.noRecommendation")}</p>
      )}
      {hint.automation_policy.blocking_reasons?.[0] ? <small className="warning-text">{hint.automation_policy.blocking_reasons[0]}</small> : null}
      <button type="button" disabled={loadingScheduleId === hint.publish_draft_id} onClick={() => void onSchedule(hint.publish_draft_id)}>
        {loadingScheduleId === hint.publish_draft_id ? t("optimizationPage.loadingSlots") : t("optimizationPage.viewScheduleHints")}
      </button>
    </div>
  );
}
