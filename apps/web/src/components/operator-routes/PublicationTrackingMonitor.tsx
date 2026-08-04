"use client";

import { useEffect, useState } from "react";
import {
  fetchPublicationMetricSnapshots,
  fetchPublicationMetricTrackingMonitor,
  pausePublicationMetricTracking,
  resumePublicationMetricTracking,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import type {
  PublicationMetricSnapshot,
  PublicationMetricTrackingMonitorItem,
  PublicationMetricTrackingMonitorResponse,
} from "../../types/publication-library";
import type { PlatformAccount } from "../../types/publish-draft";
import { formatDateTime } from "../ops-console/OpsShared";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";

const EMPTY_MONITOR: PublicationMetricTrackingMonitorResponse = {
  items: [],
  total: 0,
  limit: 100,
  offset: 0,
  kpis: {
    active_count: 0,
    due_soon_count: 0,
    needs_attention_count: 0,
    paused_count: 0,
    completed_count: 0,
    snapshots_today_count: 0,
  },
};

function numberValue(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat().format(value);
}

function reasonLabel(value: string): string {
  return value.replaceAll("_", " ").replaceAll(":", " · ");
}

export function PublicationTrackingMonitor({
  accounts,
  onOpenPublication,
}: {
  accounts: PlatformAccount[];
  onOpenPublication: (item: PublicationMetricTrackingMonitorItem) => Promise<void>;
}) {
  const t = useT();
  const { notify } = useNotice();
  const [monitor, setMonitor] = useState(EMPTY_MONITOR);
  const [statusFilter, setStatusFilter] = useState("");
  const [healthFilter, setHealthFilter] = useState("");
  const [accountFilter, setAccountFilter] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<PublicationMetricTrackingMonitorItem | null>(null);
  const [drawerSnapshots, setDrawerSnapshots] = useState<PublicationMetricSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadMonitor(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchPublicationMetricTrackingMonitor({
        status: statusFilter || undefined,
        health: healthFilter || undefined,
        platformAccountId: accountFilter || undefined,
        query: query || undefined,
        limit: 100,
      });
      setMonitor(payload);
      setError(null);
      if (selected) {
        const updated = payload.items.find((item) => item.schedule.id === selected.schedule.id);
        if (updated) {
          const snapshotChanged = updated.schedule.last_metric_snapshot_id !== selected.schedule.last_metric_snapshot_id;
          setSelected(updated);
          if (snapshotChanged) {
            const snapshots = await fetchPublicationMetricSnapshots(updated.schedule.platform_publication_id);
            setDrawerSnapshots(snapshots.snapshots);
          }
        }
      }
      if (showNotice) notify({ message: t("trackingMonitor.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("trackingMonitor.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    void loadMonitor();
    const timer = setInterval(() => void loadMonitor(), 15_000);
    return () => clearInterval(timer);
  }, [statusFilter, healthFilter, accountFilter, query, selected?.schedule.id]);

  async function openDrawer(item: PublicationMetricTrackingMonitorItem) {
    setSelected(item);
    setDrawerSnapshots([]);
    try {
      const snapshots = await fetchPublicationMetricSnapshots(item.schedule.platform_publication_id);
      setDrawerSnapshots(snapshots.snapshots);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("trackingMonitor.snapshotError"));
    }
  }

  async function changeSchedule(item: PublicationMetricTrackingMonitorItem, action: "pause" | "resume") {
    setActionBusy(`${action}-${item.schedule.id}`);
    try {
      const schedule = action === "pause"
        ? await pausePublicationMetricTracking(item.schedule.id)
        : await resumePublicationMetricTracking(item.schedule.id);
      setSelected((current) => current?.schedule.id === schedule.id ? { ...current, schedule } : current);
      await loadMonitor();
      notify({ message: action === "pause" ? t("trackingMonitor.actionPaused") : t("trackingMonitor.resumed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("trackingMonitor.actionError"));
    } finally {
      setActionBusy(null);
    }
  }

  const kpis = monitor.kpis;

  return <section className="tracking-monitor-page">
    {error ? <div className="inline-error" role="alert">{error}</div> : null}
    <section className="tracking-monitor-kpis">
      <article><span>{t("trackingMonitor.active")}</span><strong>{kpis.active_count}</strong><small>{t("trackingMonitor.activeHint")}</small></article>
      <article><span>{t("trackingMonitor.dueSoon")}</span><strong>{kpis.due_soon_count}</strong><small>{t("trackingMonitor.dueSoonHint")}</small></article>
      <article className={kpis.needs_attention_count ? "is-warning" : ""}><span>{t("trackingMonitor.needsAttention")}</span><strong>{kpis.needs_attention_count}</strong><small>{t("trackingMonitor.needsAttentionHint")}</small></article>
      <article><span>{t("trackingMonitor.paused")}</span><strong>{kpis.paused_count}</strong><small>{t("trackingMonitor.completed").replace("{count}", String(kpis.completed_count))}</small></article>
      <article><span>{t("trackingMonitor.snapshotsToday")}</span><strong>{kpis.snapshots_today_count}</strong><small>{t("trackingMonitor.snapshotsTodayHint")}</small></article>
    </section>

    <section className="tracking-monitor-toolbar">
      <label><span>{t("trackingMonitor.page")}</span><select value={accountFilter} onChange={(event) => setAccountFilter(event.target.value)}><option value="">{t("trackingMonitor.allPages")}</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select></label>
      <label><span>{t("trackingMonitor.status")}</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">{t("trackingMonitor.allStatuses")}</option>{["ACTIVE", "PAUSED", "BLOCKED", "COMPLETED"].map((value) => <option key={value} value={value}>{t(`publicationLibrary.trackingStatus.${value}`)}</option>)}</select></label>
      <label><span>{t("trackingMonitor.health")}</span><select value={healthFilter} onChange={(event) => setHealthFilter(event.target.value)}><option value="">{t("trackingMonitor.allHealth")}</option>{["HEALTHY", "WAITING", "DELAYED", "COOLDOWN", "BLOCKED", "PAUSED", "COMPLETED"].map((value) => <option key={value} value={value}>{t(`trackingMonitor.healthStatus.${value}`)}</option>)}</select></label>
      <form onSubmit={(event) => { event.preventDefault(); setQuery(queryInput.trim()); }}><label><span>{t("trackingMonitor.search")}</span><input onChange={(event) => setQueryInput(event.target.value)} placeholder={t("trackingMonitor.searchPlaceholder")} value={queryInput} /></label><AsyncButton pending={loading} type="submit">{t("trackingMonitor.apply")}</AsyncButton></form>
      <AsyncButton pending={loading} onClick={() => void loadMonitor(true)}>{t("common.refresh")}</AsyncButton>
    </section>

    <section className="tracking-monitor-table-wrap">
      <header><div><strong>{t("trackingMonitor.title")}</strong><small>{t("trackingMonitor.resultCount").replace("{count}", String(monitor.total))}</small></div></header>
      {loading && monitor.items.length === 0 ? <p className="muted">{t("trackingMonitor.loading")}</p> : monitor.items.length === 0 ? <p className="muted">{t("trackingMonitor.empty")}</p> : <table className="tracking-monitor-table"><thead><tr><th>{t("trackingMonitor.reel")}</th><th>{t("trackingMonitor.page")}</th><th>{t("trackingMonitor.health")}</th><th>{t("publicationLibrary.views")}</th><th>{t("publicationLibrary.viewsPerHour")}</th><th>{t("publicationLibrary.snapshots")}</th><th>{t("trackingMonitor.lastNext")}</th><th>{t("trackingMonitor.actions")}</th></tr></thead><tbody>{monitor.items.map((item) => <tr key={item.schedule.id} onClick={() => void openDrawer(item)}><td><div className="tracking-monitor-reel">{item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span>Reel</span>}<div><b>{item.caption || item.external_reel_id || "Reel"}</b><small>{item.external_reel_id}</small></div></div></td><td>{item.page_display_name}</td><td><span className={`tracking-health-badge is-${item.health_status.toLowerCase()}`}>{t(`trackingMonitor.healthStatus.${item.health_status}`)}</span><small className="tracking-monitor-reason">{reasonLabel(item.health_reason)}</small></td><td>{numberValue(item.growth.latest_view_count)}</td><td>{numberValue(item.growth.recent_views_per_hour)}</td><td>{item.growth.snapshot_count}</td><td><div className="tracking-monitor-times"><small>{t("trackingMonitor.lastShort")}: {item.schedule.last_completed_at ? formatDateTime(item.schedule.last_completed_at) : "—"}</small><small>{t("trackingMonitor.nextShort")}: {item.schedule.next_collection_at ? formatDateTime(item.schedule.next_collection_at) : "—"}</small></div></td><td onClick={(event) => event.stopPropagation()}><div className="tracking-monitor-actions">{item.schedule.status === "ACTIVE" ? <AsyncButton pending={actionBusy === `pause-${item.schedule.id}`} onClick={() => void changeSchedule(item, "pause")}>{t("publicationLibrary.pauseTracking")}</AsyncButton> : item.schedule.status === "PAUSED" ? <AsyncButton pending={actionBusy === `resume-${item.schedule.id}`} onClick={() => void changeSchedule(item, "resume")}>{t("publicationLibrary.resumeTracking")}</AsyncButton> : null}<button onClick={() => void openDrawer(item)} type="button">{t("trackingMonitor.details")}</button></div></td></tr>)}</tbody></table>}
    </section>

    {selected ? <div className="tracking-monitor-drawer-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) setSelected(null); }}><aside aria-label={t("trackingMonitor.drawerTitle")} className="tracking-monitor-drawer" role="dialog"><header><div><span className={`tracking-health-badge is-${selected.health_status.toLowerCase()}`}>{t(`trackingMonitor.healthStatus.${selected.health_status}`)}</span><strong>{selected.caption || selected.external_reel_id || "Reel"}</strong><small>{selected.page_display_name} · {selected.external_reel_id}</small></div><button aria-label={t("common.close")} onClick={() => setSelected(null)} type="button">×</button></header><section className="tracking-monitor-drawer-metrics"><div><span>{t("publicationLibrary.views")}</span><b>{numberValue(selected.growth.latest_view_count)}</b></div><div><span>{t("publicationLibrary.viewsPerHour")}</span><b>{numberValue(selected.growth.recent_views_per_hour)}</b></div><div><span>{t("publicationLibrary.engagement")}</span><b>{selected.growth.latest_engagement_rate_percent == null ? "—" : `${selected.growth.latest_engagement_rate_percent.toFixed(2)}%`}</b></div><div><span>{t("publicationLibrary.snapshots")}</span><b>{selected.growth.snapshot_count}</b></div></section><section><strong>{t("trackingMonitor.scheduleDetail")}</strong><dl><div><dt>{t("trackingMonitor.status")}</dt><dd>{selected.schedule.status}</dd></div><div><dt>{t("publicationLibrary.nextCollection")}</dt><dd>{selected.schedule.next_collection_at ? formatDateTime(selected.schedule.next_collection_at) : "—"}</dd></div><div><dt>{t("publicationLibrary.lastCollection")}</dt><dd>{selected.schedule.last_completed_at ? formatDateTime(selected.schedule.last_completed_at) : "—"}</dd></div><div><dt>{t("publicationLibrary.trackingEnds")}</dt><dd>{selected.schedule.tracking_ends_at ? formatDateTime(selected.schedule.tracking_ends_at) : "—"}</dd></div><div><dt>{t("trackingMonitor.decision")}</dt><dd>{reasonLabel(String(selected.schedule.last_decision_json?.reason || selected.health_reason))}</dd></div></dl></section><section><strong>{t("trackingMonitor.latestJob")}</strong>{selected.last_job ? <div className={`tracking-monitor-job is-${selected.last_job.status.toLowerCase()}`}><b>{selected.last_job.status} · {selected.last_job.progress_percent}%</b><small>{selected.last_job.id}</small>{selected.last_job.error_message ? <p>{selected.last_job.error_message}</p> : null}</div> : <p className="muted">{t("trackingMonitor.noJob")}</p>}</section><section><strong>{t("trackingMonitor.snapshotTimeline")}</strong>{drawerSnapshots.length === 0 ? <p className="muted">{t("trackingMonitor.noSnapshots")}</p> : <ol className="tracking-monitor-timeline">{drawerSnapshots.map((snapshot) => <li key={snapshot.id}><time>{formatDateTime(snapshot.observed_at)}</time><b>{numberValue(snapshot.view_count)} {t("publicationLibrary.views").toLowerCase()}</b><small>{snapshot.views_per_hour == null ? t("trackingMonitor.baselineOrUnstable") : `${numberValue(snapshot.views_per_hour)} / hour`} · {snapshot.data_quality}</small></li>)}</ol>}</section><footer><AsyncButton onClick={() => void onOpenPublication(selected)}>{t("trackingMonitor.openPublication")}</AsyncButton>{selected.external_permalink ? <a href={selected.external_permalink} rel="noreferrer" target="_blank">{t("publicationLibrary.openFacebook")}</a> : null}{selected.schedule.status === "ACTIVE" ? <AsyncButton pending={actionBusy === `pause-${selected.schedule.id}`} onClick={() => void changeSchedule(selected, "pause")}>{t("publicationLibrary.pauseTracking")}</AsyncButton> : selected.schedule.status === "PAUSED" ? <AsyncButton className="primary" pending={actionBusy === `resume-${selected.schedule.id}`} onClick={() => void changeSchedule(selected, "resume")}>{t("publicationLibrary.resumeTracking")}</AsyncButton> : null}</footer></aside></div> : null}
  </section>;
}
