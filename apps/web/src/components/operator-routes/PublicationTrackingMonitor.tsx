"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  fetchPublicationMetricSnapshots,
  fetchPublicationMetricTrackingMonitor,
  pausePublicationMetricTracking,
  resumePublicationMetricTracking,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import type {
  PublicationMetricSnapshot,
  PublicationMetricTrackingHealth,
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

const DUE_SOON_MS = 15 * 60 * 1000;
const ATTENTION_HEALTH = new Set<PublicationMetricTrackingHealth>(["DELAYED", "BLOCKED", "COOLDOWN"]);
const FAILED_JOB = new Set(["FAILED", "RETRYABLE"]);
const QUIET_HEALTH_REASONS = new Set([
  "tracking_healthy",
  "tracking_window_completed",
  "schedule_paused",
  "schedule_blocked",
]);

type MonitorLaneKey = "attention" | "due" | "steady" | "parked";
type MonitorIconKind = "attention" | "check" | "clock" | "pause" | "play" | "chevron" | "queue" | "refresh" | "publication" | "external";

function MonitorIcon({ kind, className = "tracking-monitor-icon" }: { kind: MonitorIconKind; className?: string }) {
  const common = { className, fill: "none", viewBox: "0 0 24 24", "aria-hidden": true } as const;
  if (kind === "attention") return <svg {...common}><path d="M12 4 21 19H3L12 4Z" /><path d="M12 9.5v4M12 16.4v.1" /></svg>;
  if (kind === "check") return <svg {...common}><path d="m5 13 3.2 3.2L19 6.8" /><path d="M4.5 19.5h15" /></svg>;
  if (kind === "clock") return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>;
  if (kind === "pause") return <svg {...common}><rect height="12" rx="1.2" width="3.2" x="7.2" y="6" /><rect height="12" rx="1.2" width="3.2" x="13.6" y="6" /></svg>;
  if (kind === "play") return <svg {...common}><path d="M8.5 6.5v11l9-5.5z" /></svg>;
  if (kind === "chevron") return <svg {...common}><path d="m7.5 9.5 4.5 4.5 4.5-4.5" /></svg>;
  if (kind === "queue") return <svg {...common}><rect height="4" rx="1.5" width="13" x="5.5" y="5" /><rect height="4" rx="1.5" width="13" x="5.5" y="10" /><rect height="4" rx="1.5" width="9" x="5.5" y="15" /></svg>;
  if (kind === "publication") return <svg {...common}><rect height="14" rx="2" width="11" x="5" y="5" /><path d="M9 9h3M9 12h5M9 15h4" /></svg>;
  if (kind === "external") return <svg {...common}><path d="M10 6H6.5A1.5 1.5 0 0 0 5 7.5v10A1.5 1.5 0 0 0 6.5 19h10a1.5 1.5 0 0 0 1.5-1.5V14" /><path d="M13 5h6v6M19 5l-8 8" /></svg>;
  return <svg {...common}><path d="M19 8.5A7.5 7.5 0 1 0 19.4 15M19 4v4.5h-4.5" /></svg>;
}

function numberValue(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat().format(value);
}

function reasonLabel(value: string): string {
  return value.replaceAll("_", " ").replaceAll(":", " · ");
}

function isParked(item: PublicationMetricTrackingMonitorItem): boolean {
  return item.schedule.status === "PAUSED" || item.schedule.status === "COMPLETED"
    || item.health_status === "PAUSED" || item.health_status === "COMPLETED";
}

function isDueSoon(item: PublicationMetricTrackingMonitorItem, nowMs: number): boolean {
  const nextAt = item.schedule.next_collection_at;
  if (!nextAt) return false;
  const nextMs = Date.parse(nextAt);
  return !Number.isNaN(nextMs) && nextMs <= nowMs + DUE_SOON_MS;
}

function monitorLane(item: PublicationMetricTrackingMonitorItem, nowMs: number): MonitorLaneKey {
  if (isParked(item)) return "parked";
  const jobFailed = item.last_job != null && FAILED_JOB.has(item.last_job.status);
  if (ATTENTION_HEALTH.has(item.health_status) || item.growth.counter_regression_detected || jobFailed) return "attention";
  if (item.health_status === "WAITING" || isDueSoon(item, nowMs)) return "due";
  return "steady";
}

function sortLaneItems(items: PublicationMetricTrackingMonitorItem[]): PublicationMetricTrackingMonitorItem[] {
  return [...items].sort((a, b) => (b.growth.latest_view_count ?? -1) - (a.growth.latest_view_count ?? -1));
}

function engagementWidth(item: PublicationMetricTrackingMonitorItem): number {
  const value = item.growth.latest_engagement_rate_percent;
  if (value == null || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function compactNumber(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function compactDateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function workloadNote(item: PublicationMetricTrackingMonitorItem): string | null {
  const job = item.last_job;
  if (!job) return null;
  if (job.error_message) return `${job.status} · ${job.error_message}`;
  if (job.status === "COMPLETED" || job.status === "CANCELLED") return null;
  if (FAILED_JOB.has(job.status) || job.status === "QUEUED" || job.status === "RUNNING" || job.status === "WAITING_FOR_REVIEW") {
    return job.status;
  }
  return null;
}

function rowHealthNote(item: PublicationMetricTrackingMonitorItem): string | null {
  const raw = item.health_reason?.trim();
  if (!raw || QUIET_HEALTH_REASONS.has(raw)) return null;
  return reasonLabel(raw);
}

function looksLikeTechnicalId(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (/^local-pilot-/i.test(trimmed)) return true;
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(trimmed)) return true;
  return trimmed.length > 64;
}

function drawerTitle(item: PublicationMetricTrackingMonitorItem): string {
  const caption = item.caption?.trim();
  if (caption && !looksLikeTechnicalId(caption)) return caption;
  if (item.page_display_name?.trim()) return item.page_display_name.trim();
  if (caption) return caption;
  return item.external_reel_id || "Reel";
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
  const [accountFilter, setAccountFilter] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [laneFilter, setLaneFilter] = useState<MonitorLaneKey | "">("");
  const [collapsedLanes, setCollapsedLanes] = useState<Set<MonitorLaneKey>>(new Set());
  const [selected, setSelected] = useState<PublicationMetricTrackingMonitorItem | null>(null);
  const [drawerSnapshots, setDrawerSnapshots] = useState<PublicationMetricSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadMonitor(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchPublicationMetricTrackingMonitor({
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
  }, [accountFilter, query, selected?.schedule.id]);

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

  function toggleLane(key: MonitorLaneKey) {
    setCollapsedLanes((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const nowMs = Date.now();
  const attentionRows = useMemo(() => sortLaneItems(monitor.items.filter((item) => monitorLane(item, nowMs) === "attention")), [monitor.items]);
  const dueRows = useMemo(() => sortLaneItems(monitor.items.filter((item) => monitorLane(item, nowMs) === "due")), [monitor.items]);
  const steadyRows = useMemo(() => sortLaneItems(monitor.items.filter((item) => monitorLane(item, nowMs) === "steady")), [monitor.items]);
  const parkedRows = useMemo(() => sortLaneItems(monitor.items.filter((item) => monitorLane(item, nowMs) === "parked")), [monitor.items]);

  const trackedViews = monitor.items.reduce<number | null>((sum, item) => {
    const views = item.growth.latest_view_count;
    if (views == null) return sum;
    return (sum ?? 0) + views;
  }, null);
  const growingCount = monitor.items.filter((item) => item.growth.trend_label === "GROWING").length;
  const monitorLanes: Array<{ key: MonitorLaneKey; label: string; hint: string; icon: MonitorIconKind; items: PublicationMetricTrackingMonitorItem[] }> = [
    { key: "attention", label: t("trackingMonitor.laneAttention"), hint: t("trackingMonitor.needsAttentionHint"), icon: "attention", items: attentionRows },
    { key: "due", label: t("trackingMonitor.laneDue"), hint: t("trackingMonitor.dueSoonHint"), icon: "clock", items: dueRows },
    { key: "steady", label: t("trackingMonitor.laneSteady"), hint: t("trackingMonitor.laneSteadyHint"), icon: "check", items: steadyRows },
    { key: "parked", label: t("trackingMonitor.laneParked"), hint: t("trackingMonitor.laneParkedHint"), icon: "pause", items: parkedRows },
  ];
  const laneTotal = Math.max(monitor.items.length, 1);
  const lanePeak = Math.max(attentionRows.length, dueRows.length, steadyRows.length, parkedRows.length, 1);
  const attentionDeg = (attentionRows.length / laneTotal) * 360;
  const dueDeg = (dueRows.length / laneTotal) * 360;
  const steadyDeg = (steadyRows.length / laneTotal) * 360;
  const donutGradient = monitor.items.length === 0
    ? "conic-gradient(#d5e0db 0deg 90deg, #c5d4ce 90deg 180deg, #b7c7c0 180deg 270deg, #a9bab3 270deg 360deg)"
    : `conic-gradient(#d99a2c 0deg ${attentionDeg}deg, #4a90c8 ${attentionDeg}deg ${attentionDeg + dueDeg}deg, #2f8f6f ${attentionDeg + dueDeg}deg ${attentionDeg + dueDeg + steadyDeg}deg, #6f857c ${attentionDeg + dueDeg + steadyDeg}deg 360deg)`;
  const visibleLanes = laneFilter ? monitorLanes.filter((lane) => lane.key === laneFilter) : monitorLanes.filter((lane) => lane.items.length > 0);
  const nextDueAt = monitor.items
    .filter((item) => !isParked(item) && item.schedule.next_collection_at)
    .map((item) => item.schedule.next_collection_at as string)
    .sort()[0] ?? null;
  const lastMeasuredAt = monitor.items
    .map((item) => item.growth.latest_observed_at ?? item.schedule.last_completed_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null;

  function renderScheduleAction(item: PublicationMetricTrackingMonitorItem): ReactNode {
    if (item.schedule.status === "ACTIVE") {
      return (
        <AsyncButton
          aria-label={t("publicationLibrary.pauseTracking")}
          className="tracking-monitor-table__action"
          leadingIcon={<MonitorIcon kind="pause" />}
          onClick={() => void changeSchedule(item, "pause")}
          pending={actionBusy === `pause-${item.schedule.id}`}
        >
          {t("publicationLibrary.pauseTracking")}
        </AsyncButton>
      );
    }
    if (item.schedule.status === "PAUSED") {
      return (
        <AsyncButton
          aria-label={t("publicationLibrary.resumeTracking")}
          className="tracking-monitor-table__action is-primary"
          leadingIcon={<MonitorIcon kind="play" />}
          onClick={() => void changeSchedule(item, "resume")}
          pending={actionBusy === `resume-${item.schedule.id}`}
        >
          {t("publicationLibrary.resumeTracking")}
        </AsyncButton>
      );
    }
    return null;
  }

  return (
    <section className="tracking-monitor-page is-v80 is-v81">
      {error ? <div className="inline-error" role="alert">{error}</div> : null}

      <section aria-label={t("trackingMonitor.title")} className="tracking-monitor-spectrum is-metric-band">
        <div className="tracking-monitor-spectrum__chart">
          <div className="tracking-monitor-spectrum__stage">
            <div className="tracking-monitor-spectrum__head">
              <span className="tracking-monitor-spectrum__eyebrow"><MonitorIcon kind="queue" />{t("trackingMonitor.spectrumEyebrow")}</span>
              <strong className="tracking-monitor-spectrum__total">
                <b>{monitor.total}</b>
                <small>{t("trackingMonitor.schedules")}</small>
              </strong>
            </div>
            <div aria-hidden="true" className="tracking-monitor-spectrum__donut" style={{ background: donutGradient }}>
              <div className="tracking-monitor-spectrum__donut-core">
                <b>{monitor.total}</b>
              </div>
            </div>
            <div className="tracking-monitor-spectrum__bars" role="list">
              {monitorLanes.map((lane) => {
                const barW = lane.items.length === 0 ? 0 : Math.max(12, Math.round((lane.items.length / lanePeak) * 100));
                return (
                  <button
                    aria-label={`${lane.label}: ${lane.items.length}`}
                    className={`is-${lane.key}${lane.items.length === 0 ? " is-empty" : ""}${laneFilter === lane.key ? " is-current" : ""}`}
                    key={lane.key}
                    onClick={() => setLaneFilter((current) => current === lane.key ? "" : lane.key)}
                    role="listitem"
                    style={{ ["--bar-w" as string]: `${barW}%` }}
                    type="button"
                  >
                    <span><i aria-hidden="true" />{lane.label}</span>
                    <em aria-hidden="true" />
                    <strong>{lane.items.length}</strong>
                  </button>
                );
              })}
            </div>
            <div className="tracking-monitor-spectrum__metrics">
              <div className="is-views">
                <span>{t("trackingMonitor.trackedViews")}</span>
                <strong>{compactNumber(trackedViews)}</strong>
              </div>
              <div className={`is-active${monitor.kpis.active_count === 0 ? " is-empty" : ""}`}>
                <span>{t("trackingMonitor.active")}</span>
                <strong>{monitor.kpis.active_count}</strong>
              </div>
              <div className={`is-next${nextDueAt ? "" : " is-empty"}`}>
                <span>{t("trackingMonitor.nextDue")}</span>
                <strong>{nextDueAt ? compactDateTime(nextDueAt) : t("trackingMonitor.noneDue")}</strong>
              </div>
              <div className={`is-due${monitor.kpis.due_soon_count === 0 ? " is-empty" : ""}`}>
                <span>{t("trackingMonitor.dueSoon")}</span>
                <strong>{monitor.kpis.due_soon_count}</strong>
              </div>
              <div className={`is-snapshots${monitor.kpis.snapshots_today_count === 0 ? " is-empty" : ""}`}>
                <span>{t("trackingMonitor.snapshotsToday")}</span>
                <strong>{monitor.kpis.snapshots_today_count}</strong>
              </div>
              <div className={`is-growing${growingCount === 0 ? " is-empty" : ""}`}>
                <span>{t("trackingMonitor.growing")}</span>
                <strong>{growingCount}</strong>
              </div>
              <div className={`is-attention${monitor.kpis.needs_attention_count === 0 ? " is-empty" : ""}`}>
                <span>{t("trackingMonitor.needsAttention")}</span>
                <strong>{monitor.kpis.needs_attention_count}</strong>
              </div>
              <div className={`is-measured${lastMeasuredAt ? "" : " is-empty"}`}>
                <span>{t("trackingMonitor.lastMeasured")}</span>
                <strong>{lastMeasuredAt ? compactDateTime(lastMeasuredAt) : "—"}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="tracking-monitor-board">
        <header className="tracking-monitor-board__head">
          <div>
            <h2><MonitorIcon kind="queue" />{t("trackingMonitor.title")}</h2>
          </div>
          <form
            className="tracking-monitor-board__commands"
            onSubmit={(event) => {
              event.preventDefault();
              setQuery(queryInput.trim());
            }}
          >
            <input
              aria-label={t("trackingMonitor.search")}
              onChange={(event) => setQueryInput(event.target.value)}
              placeholder={t("trackingMonitor.searchPlaceholder")}
              value={queryInput}
            />
            <select aria-label={t("trackingMonitor.page")} onChange={(event) => setAccountFilter(event.target.value)} value={accountFilter}>
              <option value="">{t("trackingMonitor.allPages")}</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.display_name}</option>
              ))}
            </select>
            <AsyncButton leadingIcon={<MonitorIcon kind="refresh" />} pending={loading} onClick={() => void loadMonitor(true)} type="button">
              {t("common.refresh")}
            </AsyncButton>
          </form>
        </header>

        {loading && monitor.items.length === 0 ? (
          <p className="muted tracking-monitor-board__empty">{t("trackingMonitor.loading")}</p>
        ) : monitor.items.length === 0 ? (
          <p className="muted tracking-monitor-board__empty">{t("trackingMonitor.empty")}</p>
        ) : (
          <div className="tracking-monitor-table-shell">
            <div className="tracking-monitor-table__scroll">
              <table className="tracking-monitor-table">
                <colgroup>
                  <col className="is-reel" />
                  <col className="is-state" />
                  <col className="is-performance" />
                  <col className="is-workload" />
                  <col className="is-window" />
                  <col className="is-action" />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">{t("trackingMonitor.reel")}</th>
                    <th scope="col">{t("trackingMonitor.health")}</th>
                    <th scope="col">{t("publicationLibrary.views")}</th>
                    <th scope="col">{t("publicationLibrary.snapshots")}</th>
                    <th scope="col">{t("trackingMonitor.nextShort")}</th>
                    <th aria-label={t("trackingMonitor.actions")} scope="col" />
                  </tr>
                </thead>
                {visibleLanes.map((lane) => {
                  const collapsed = collapsedLanes.has(lane.key);
                  return (
                    <tbody className={`is-${lane.key}`} key={lane.key}>
                      <tr className="tracking-monitor-table__group">
                        <th colSpan={6} scope="rowgroup">
                          <button
                            aria-expanded={!collapsed}
                            onClick={() => toggleLane(lane.key)}
                            title={lane.hint}
                            type="button"
                          >
                            <MonitorIcon kind={lane.icon} />
                            <b>{lane.label}</b>
                            <em>{lane.items.length}</em>
                            <MonitorIcon className="tracking-monitor-table__chevron" kind="chevron" />
                          </button>
                        </th>
                      </tr>
                      {!collapsed ? lane.items.map((item) => {
                        const focused = selected?.schedule.id === item.schedule.id;
                        const healthNote = rowHealthNote(item);
                        const trend = item.growth.trend_label;
                        const jobNote = workloadNote(item);
                        const parked = isParked(item);
                        const nextAt = item.schedule.next_collection_at;
                        const lastAt = item.schedule.last_completed_at;
                        const windowPrimary = parked
                          ? (lastAt ? compactDateTime(lastAt) : "—")
                          : (nextAt ? compactDateTime(nextAt) : "—");
                        const windowTitle = parked
                          ? (lastAt ? `${t("trackingMonitor.lastMeasured")} · ${compactDateTime(lastAt)}` : undefined)
                          : (lastAt ? `${t("trackingMonitor.lastMeasured")} · ${compactDateTime(lastAt)}` : undefined);
                        return (
                          <tr
                            className={`tracking-monitor-table__row${focused ? " is-focused" : ""}`}
                            key={item.schedule.id}
                            onClick={() => void openDrawer(item)}
                          >
                            <td>
                              <div className="tracking-monitor-reel tracking-monitor-table__identity">
                                {item.thumbnail_url ? <img alt="" referrerPolicy="no-referrer" src={item.thumbnail_url} /> : <span aria-hidden="true" />}
                                <div>
                                  <strong title={item.caption || item.external_reel_id || "Reel"}>{item.caption || item.external_reel_id || "Reel"}</strong>
                                  <small>{item.page_display_name}</small>
                                </div>
                              </div>
                            </td>
                            <td>
                              <div className={`tracking-monitor-table__state${healthNote ? "" : " is-quiet"}`}>
                                <div>
                                  <span className={`tracking-health-badge is-${item.health_status.toLowerCase()}`}>
                                    <i aria-hidden="true" />
                                    {t(`trackingMonitor.healthStatus.${item.health_status}`)}
                                  </span>
                                </div>
                                {healthNote ? <small title={healthNote}>{healthNote}</small> : null}
                              </div>
                            </td>
                            <td>
                              <div
                                className={`tracking-monitor-table__performance${trend === "COUNTER_REGRESSION" ? " is-regression" : ""}${trend === "GROWING" ? " is-growing" : ""}${trend === "FLAT" ? " is-flat" : ""}`}
                              >
                                <div>
                                  <strong>{numberValue(item.growth.latest_view_count)}</strong>
                                  <small>{numberValue(item.growth.recent_views_per_hour)} / hour · {t(`publicationLibrary.trendLabel.${trend}`)}</small>
                                </div>
                                <span aria-hidden="true"><i style={{ width: `${engagementWidth(item)}%` }} /></span>
                              </div>
                            </td>
                            <td>
                              <div className={`tracking-monitor-table__workload${jobNote ? "" : " is-quiet"}`}>
                                <strong><MonitorIcon kind="queue" />{item.growth.snapshot_count}</strong>
                                {jobNote ? <small title={jobNote}>{jobNote}</small> : null}
                              </div>
                            </td>
                            <td>
                              <div className={`tracking-monitor-table__window${parked ? " is-parked" : ""}`} title={windowTitle}>
                                <span aria-hidden="true" />
                                <div>
                                  <strong>{windowPrimary}</strong>
                                </div>
                              </div>
                            </td>
                            <td onClick={(event) => event.stopPropagation()}>
                              {renderScheduleAction(item)}
                            </td>
                          </tr>
                        );
                      }) : null}
                    </tbody>
                  );
                })}
              </table>
            </div>
          </div>
        )}
      </section>

      {selected ? (
        <div
          className="tracking-monitor-drawer-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setSelected(null);
          }}
        >
          <aside aria-label={t("trackingMonitor.drawerTitle")} className="tracking-monitor-drawer is-v81" role="dialog">
            <header className="tracking-monitor-drawer__header">
              <div className="tracking-monitor-drawer__identity">
                {selected.thumbnail_url ? (
                  <img alt="" className="tracking-monitor-drawer__thumb" referrerPolicy="no-referrer" src={selected.thumbnail_url} />
                ) : (
                  <span aria-hidden="true" className="tracking-monitor-drawer__thumb is-empty" />
                )}
                <div className="tracking-monitor-drawer__copy">
                  <span className={`tracking-health-badge is-${selected.health_status.toLowerCase()}`}>
                    <i aria-hidden="true" />
                    {t(`trackingMonitor.healthStatus.${selected.health_status}`)}
                  </span>
                  <strong title={drawerTitle(selected)}>{drawerTitle(selected)}</strong>
                  <small>{selected.page_display_name}</small>
                  {selected.external_reel_id ? (
                    <code className="tracking-monitor-drawer__reel-id" title={selected.external_reel_id}>
                      {selected.external_reel_id}
                    </code>
                  ) : null}
                </div>
              </div>
              <button aria-label={t("common.close")} onClick={() => setSelected(null)} type="button">×</button>
            </header>
            <div className="tracking-monitor-drawer__body">
              <section className="tracking-monitor-drawer-metrics is-v81">
                <div>
                  <span>{t("publicationLibrary.views")}</span>
                  <b>{numberValue(selected.growth.latest_view_count)}</b>
                </div>
                <div>
                  <span>{t("publicationLibrary.viewsPerHour")}</span>
                  <b>{numberValue(selected.growth.recent_views_per_hour)}</b>
                </div>
                <div>
                  <span>{t("publicationLibrary.engagement")}</span>
                  <b>
                    {selected.growth.latest_engagement_rate_percent == null
                      ? "—"
                      : `${selected.growth.latest_engagement_rate_percent.toFixed(2)}%`}
                  </b>
                </div>
                <div>
                  <span>{t("publicationLibrary.snapshots")}</span>
                  <b>{selected.growth.snapshot_count}</b>
                </div>
              </section>
              <section className="tracking-monitor-drawer__panel" aria-label={t("trackingMonitor.scheduleDetail")}>
                <span className="tracking-monitor-drawer__eyebrow">{t("trackingMonitor.scheduleDetail")}</span>
                <dl>
                  <div>
                    <dt>{t("trackingMonitor.status")}</dt>
                    <dd>{selected.schedule.status}</dd>
                  </div>
                  <div>
                    <dt>{t("publicationLibrary.nextCollection")}</dt>
                    <dd>{selected.schedule.next_collection_at ? formatDateTime(selected.schedule.next_collection_at) : "—"}</dd>
                  </div>
                  <div>
                    <dt>{t("publicationLibrary.lastCollection")}</dt>
                    <dd>{selected.schedule.last_completed_at ? formatDateTime(selected.schedule.last_completed_at) : "—"}</dd>
                  </div>
                  <div>
                    <dt>{t("publicationLibrary.trackingEnds")}</dt>
                    <dd>{selected.schedule.tracking_ends_at ? formatDateTime(selected.schedule.tracking_ends_at) : "—"}</dd>
                  </div>
                  <div>
                    <dt>{t("trackingMonitor.decision")}</dt>
                    <dd>{reasonLabel(String(selected.schedule.last_decision_json?.reason || selected.health_reason))}</dd>
                  </div>
                </dl>
                <div className="tracking-monitor-drawer__job-slot">
                  <span className="tracking-monitor-drawer__eyebrow">{t("trackingMonitor.latestJob")}</span>
                  {selected.last_job ? (
                    <div className={`tracking-monitor-job is-${selected.last_job.status.toLowerCase()}`}>
                      <b>{selected.last_job.status} · {selected.last_job.progress_percent}%</b>
                      <small title={selected.last_job.id}>{selected.last_job.id}</small>
                      {selected.last_job.error_message ? <p>{selected.last_job.error_message}</p> : null}
                    </div>
                  ) : (
                    <p className="muted">{t("trackingMonitor.noJob")}</p>
                  )}
                </div>
              </section>
              <section className="tracking-monitor-drawer__timeline" aria-label={t("trackingMonitor.snapshotTimeline")}>
                <span className="tracking-monitor-drawer__eyebrow">{t("trackingMonitor.snapshotTimeline")}</span>
                {drawerSnapshots.length === 0 ? (
                  <p className="muted">{t("trackingMonitor.noSnapshots")}</p>
                ) : (
                  <ol className="tracking-monitor-timeline">
                    {drawerSnapshots.map((snapshot) => (
                      <li key={snapshot.id}>
                        <time>{formatDateTime(snapshot.observed_at)}</time>
                        <b>{numberValue(snapshot.view_count)} {t("publicationLibrary.views").toLowerCase()}</b>
                        <small>
                          {snapshot.views_per_hour == null
                            ? t("trackingMonitor.baselineOrUnstable")
                            : `${numberValue(snapshot.views_per_hour)} / hour`}
                          {" · "}
                          {snapshot.data_quality}
                        </small>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </div>
            <footer className="tracking-monitor-drawer__footer">
              <AsyncButton leadingIcon={<MonitorIcon kind="publication" />} onClick={() => void onOpenPublication(selected)}>
                {t("trackingMonitor.openPublication")}
              </AsyncButton>
              {selected.external_permalink ? (
                <a href={selected.external_permalink} rel="noreferrer" target="_blank">
                  <MonitorIcon kind="external" />
                  {t("publicationLibrary.openFacebook")}
                </a>
              ) : null}
              {selected.schedule.status === "ACTIVE" ? (
                <AsyncButton
                  leadingIcon={<MonitorIcon kind="pause" />}
                  pending={actionBusy === `pause-${selected.schedule.id}`}
                  onClick={() => void changeSchedule(selected, "pause")}
                >
                  {t("publicationLibrary.pauseTracking")}
                </AsyncButton>
              ) : selected.schedule.status === "PAUSED" ? (
                <AsyncButton
                  className="primary"
                  leadingIcon={<MonitorIcon kind="play" />}
                  pending={actionBusy === `resume-${selected.schedule.id}`}
                  onClick={() => void changeSchedule(selected, "resume")}
                >
                  {t("publicationLibrary.resumeTracking")}
                </AsyncButton>
              ) : null}
            </footer>
          </aside>
        </div>
      ) : null}
    </section>
  );
}
