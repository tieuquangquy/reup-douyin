"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useT } from "../../lib/i18n";
import { fetchOptimizationDashboard, fetchOptimizationSchedulingHints } from "../../lib/api";
import { useLatestRequest } from "../../lib/useLatestRequest";
import { automationReadinessLabel, groupTone, optimizationHeadline } from "../../lib/optimizationState";
import type { OptimizationDashboard, OutcomeGroupSummary, RoutingHints, SchedulingHints } from "../../types/optimization";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";

export function OptimizationPage() {
  const t = useT();
  const [snapshot, setSnapshot] = useState<OptimizationDashboard | null>(null);
  const [selectedSchedule, setSelectedSchedule] = useState<SchedulingHints | null>(null);
  const [loadingScheduleId, setLoadingScheduleId] = useState<string | null>(null);
  const request = useLatestRequest();
  const scheduleRequest = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = snapshot ? "refresh" : "initial";
    try {
      const result = await request.run(() => fetchOptimizationDashboard(), setSnapshot, mode);
      if (mode === "refresh" && result) notify({ id: "optimization-refresh", message: "Optimization refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "optimization-refresh", message: err instanceof Error ? err.message : t("optimizationPage.loadError"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  async function loadScheduleHint(draftId: string) {
    setLoadingScheduleId(draftId);
    try {
      const result = await scheduleRequest.run(() => fetchOptimizationSchedulingHints(draftId), setSelectedSchedule, "refresh");
      if (result) notify({ id: "schedule-hints", message: "Schedule hints loaded.", tone: "success" });
    } catch (err) {
      notify({ id: "schedule-hints", message: err instanceof Error ? err.message : t("optimizationPage.scheduleHintError"), tone: "error" });
    } finally {
      setLoadingScheduleId(null);
    }
  }

  if (!snapshot && !request.error) {
    return <main className="optimization-page"><AsyncContentBoundary skeletonVariant="detail" loadingLabel={t("optimizationPage.loading")} status="loading"><span /></AsyncContentBoundary></main>;
  }

  if (request.error && !snapshot) {
    return (
      <main className="optimization-page">
        <AsyncContentBoundary errorState={<div><h1>{t("optimizationPage.unavailable")}</h1><p>{request.error.message}</p><button type="button" onClick={() => void load()}>{t("optimizationPage.retry")}</button></div>} skeletonVariant="detail" status="error"><span /></AsyncContentBoundary>
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
        <AsyncButton pending={request.refreshing} pendingLabel={t("common.refreshing")} onClick={() => void load()}>{t("optimizationPage.refresh")}</AsyncButton>
      </header>

      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="detail" status="success">
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
                  <RoutingHintCard key={hint.publish_draft_id} hint={hint} loadingScheduleId={scheduleRequest.pending ? loadingScheduleId : null} onSchedule={loadScheduleHint} />
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
      </AsyncContentBoundary>
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
      <AsyncButton pending={loadingScheduleId === hint.publish_draft_id} pendingLabel={t("optimizationPage.loadingSlots")} onClick={() => void onSchedule(hint.publish_draft_id)}>
        {t("optimizationPage.viewScheduleHints")}
      </AsyncButton>
    </div>
  );
}
