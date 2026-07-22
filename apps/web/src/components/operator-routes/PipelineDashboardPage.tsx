"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchPipelineDashboard } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import { humanizeStatus } from "../../lib/statusLabels";
import type {
  PipelineDashboardActivityItem,
  PipelineDashboardAttentionItem,
  PipelineDashboardMetric,
  PipelineDashboardResponse,
  PipelineDashboardStage,
  PipelineDashboardStatus,
  PipelineStageKey,
} from "../../types/operations";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, type OpsTone } from "../ops-console/OpsShared";

const TRIAGE_LINKS = [
  { key: "capture", href: "/ops/extensions/douyin/capture-inbox", labelKey: "opsPipeline.openCapture" },
  { key: "review", href: "/selection/review-board", labelKey: "opsPipeline.openReview" },
  { key: "reupQueue", href: "/selection/reup-queue", labelKey: "opsPipeline.openReupQueue" },
  { key: "publishDrafts", href: "/publishing/drafts", labelKey: "opsPipeline.openPublishDrafts" },
] as const;

const NEXT_WORK_LIMIT = 3;

function PipelineKpi({
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
    <article className={`ops-pipeline-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function PipelinePanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-pipeline-panel">
      <div className="ops-pipeline-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-pipeline-panel__body">{children}</div>
    </section>
  );
}

function PipelineChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ops-pipeline-chip tone-${tone}`}>{label}</span>;
}

function PipelineOpenIcon() {
  return (
    <svg className="ops-pipeline-open-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PipelineOpenLink({ href, label }: { href: string; label: string }) {
  return (
    <Link className="ops-pipeline-open" href={href} aria-label={label} title={label}>
      <PipelineOpenIcon />
    </Link>
  );
}

export function PipelineDashboardPage() {
  const t = useT();
  const [dashboard, setDashboard] = useState<PipelineDashboardResponse | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = dashboard ? "refresh" : "initial";
    try {
      const result = await request.run(() => fetchPipelineDashboard(), setDashboard, mode);
      if (mode === "refresh" && result) notify({ id: "pipeline-refresh", message: "Pipeline refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "pipeline-refresh", message: err instanceof Error ? err.message : t("opsPipeline.loadError"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  if (!dashboard && !request.error) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsPipeline.description")} title={t("opsPipeline.title")}>
        <AsyncContentBoundary skeletonVariant="detail" status="loading"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  if (request.error && !dashboard) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsPipeline.description")} title={t("opsPipeline.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("opsPipeline.unavailableTitle")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="detail" status="error"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  if (!dashboard) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsPipeline.description")} title={t("opsPipeline.title")}>
        <OpsState title={t("opsPipeline.unavailableTitle")} detail={t("opsPipeline.emptyDetail")} />
      </OperatorStudioShell>
    );
  }

  return (
    <OperatorStudioShell actions={refreshAction} description={t("opsPipeline.description")} title={t("opsPipeline.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="detail" status="success">
        <PipelineDashboardBody dashboard={dashboard} error={null} t={t} />
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}

function PipelineDashboardBody({
  dashboard,
  error,
  t,
}: {
  dashboard: PipelineDashboardResponse;
  error: string | null;
  t: (key: string) => string;
}) {
  const nextWork = useMemo(() => pickNextWork(dashboard.attention_items), [dashboard.attention_items]);
  const kpis = useMemo(() => selectKpis(dashboard.summary_metrics, t), [dashboard.summary_metrics, t]);
  const attentionByStage = useMemo(() => groupAttentionByStage(dashboard.attention_items), [dashboard.attention_items]);

  return (
    <>
      {error ? <div className="inline-error">{error}</div> : null}

      <main className="ops-page ops-pipeline-page">
        <div className="ops-pipeline-freshness">
          <p>
            {t("opsPipeline.loadedAt")}{" "}
            <time dateTime={dashboard.generated_at}>{formatDateTime(dashboard.generated_at)}</time>
          </p>
          <PipelineChip label={statusLabel(dashboard.overall_status, t)} tone={toneForStatus(dashboard.overall_status)} />
          <span className="ops-pipeline-freshness__headline">{dashboard.headline}</span>
        </div>

        <section className="ops-pipeline-kpis" aria-label={t("opsPipeline.summary")}>
          {kpis.map((metric) => (
            <PipelineKpi
              key={metric.key}
              label={metric.label}
              value={String(metric.value)}
              detail={metric.detail ?? summaryMetricDescription(metric.key, t)}
              tone={kpiTone(metric.key, dashboard.overall_status)}
            />
          ))}
        </section>

        <div className="ops-pipeline-toolbar">
          <nav className="ops-pipeline-actions" aria-label={t("opsPipeline.triage")}>
            {TRIAGE_LINKS.map((link) => (
              <Link href={link.href} key={link.key}>
                {t(link.labelKey)}
              </Link>
            ))}
          </nav>
        </div>

        {nextWork.length > 0 ? (
          <section className="ops-pipeline-next" aria-label={t("opsPipeline.nextWork")}>
            <div className="ops-pipeline-next__head">
              <h2>{t("opsPipeline.nextWork")}</h2>
              <span>{t("opsPipeline.nextWorkHint")}</span>
            </div>
            <ul className="ops-pipeline-next__list">
              {nextWork.map((item) => (
                <li className={`ops-pipeline-next__item tone-${toneForSeverity(item.severity)}`} key={item.id}>
                  <PipelineChip label={severityLabel(item.severity, t)} tone={toneForSeverity(item.severity)} />
                  <div className="ops-pipeline-next__body">
                    <strong>{item.title}</strong>
                    <span title={item.detail}>{item.detail}</span>
                  </div>
                  <div className="ops-pipeline-next__trail">
                    <em className="ops-pipeline-next__stage">{stageKeyLabel(item.stage_key, t)}</em>
                    <b className="ops-pipeline-num">{item.count}</b>
                  </div>
                  <PipelineOpenLink href={item.href} label={t("opsPipeline.open")} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="ops-pipeline-main">
          <PipelinePanel title={t("opsPipeline.stages")}>
            <ul className="ops-pipeline-stages">
              {dashboard.stages.map((stage) => (
                <StageRow
                  key={stage.key}
                  stage={stage}
                  inlineAttention={attentionByStage.get(stage.key)?.[0] ?? null}
                  t={t}
                />
              ))}
            </ul>
            <p className="ops-pipeline-footnote">{t("opsPipeline.readOnlyFootnote")}</p>
          </PipelinePanel>
        </section>

        <PipelinePanel title={t("opsPipeline.recentActivity")}>
          {dashboard.recent_activity.length === 0 ? (
            <p className="ops-pipeline-empty">{t("opsPipeline.noRecentActivity")}</p>
          ) : (
            <ul className="ops-pipeline-activity">
              {dashboard.recent_activity.map((item) => (
                <ActivityRow item={item} key={item.id} t={t} />
              ))}
            </ul>
          )}
        </PipelinePanel>
      </main>
    </>
  );
}

function StageRow({
  stage,
  inlineAttention,
  t,
}: {
  stage: PipelineDashboardStage;
  inlineAttention: PipelineDashboardAttentionItem | null;
  t: (key: string) => string;
}) {
  const chipTone = toneForStatus(stage.status);
  const rowTone = stage.status === "blocked" || inlineAttention?.severity === "critical" ? "danger" : chipTone;
  return (
    <li className={`ops-pipeline-stage tone-${rowTone}${stage.status === "blocked" ? " is-blocked" : ""}`}>
      <div className="ops-pipeline-stage__identity">
        <strong className="ops-pipeline-stage__title" title={stage.description}>
          {stage.label}
        </strong>
        <PipelineChip label={statusLabel(stage.status, t)} tone={chipTone} />
      </div>
      <div className="ops-pipeline-stage__primary" title={stage.primary_label}>
        <b className="ops-pipeline-num">{stage.primary_count}</b>
        <em>{stage.primary_label}</em>
      </div>
      <div className="ops-pipeline-stage__secondary" title={stage.secondary_label}>
        <b className="ops-pipeline-num">{stage.secondary_count}</b>
        <em>{stage.secondary_label}</em>
      </div>
      <PipelineOpenLink href={stage.href} label={t("opsPipeline.open")} />
    </li>
  );
}

function ActivityRow({
  item,
  t,
}: {
  item: PipelineDashboardActivityItem;
  t: (key: string) => string;
}) {
  const detail = humanizeDetail(item.detail);
  const compactTime = formatCompactActivityTime(item.occurred_at);
  return (
    <li className="ops-pipeline-activity__item">
      <PipelineChip label={stageKeyLabel(item.stage_key, t)} tone={activityStageTone(item.stage_key)} />
      <div className="ops-pipeline-activity__body">
        <strong>{item.title}</strong>
        <span title={detail}>{detail}</span>
      </div>
      <div className="ops-pipeline-activity__trail">
        <time dateTime={item.occurred_at} title={formatDateTime(item.occurred_at)}>
          {compactTime}
        </time>
        <PipelineOpenLink href={item.href} label={t("opsPipeline.open")} />
      </div>
    </li>
  );
}

function formatCompactActivityTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const time = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  const day = date.getDate();
  const month = date.getMonth() + 1;
  return `${time} · ${day}/${month}`;
}

function pickNextWork(items: PipelineDashboardAttentionItem[]): PipelineDashboardAttentionItem[] {
  return [...items]
    .filter((item) => item.severity === "critical" || item.severity === "warning")
    .sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
    .slice(0, NEXT_WORK_LIMIT);
}

function groupAttentionByStage(items: PipelineDashboardAttentionItem[]): Map<string, PipelineDashboardAttentionItem[]> {
  const map = new Map<string, PipelineDashboardAttentionItem[]>();
  for (const item of [...items]
    .filter((entry) => entry.severity === "critical" || entry.severity === "warning")
    .sort((a, b) => severityRank(a.severity) - severityRank(b.severity))) {
    const list = map.get(item.stage_key) ?? [];
    list.push(item);
    map.set(item.stage_key, list);
  }
  return map;
}

function selectKpis(metrics: PipelineDashboardMetric[], t: (key: string) => string): PipelineDashboardMetric[] {
  const byKey = new Map(metrics.map((metric) => [metric.key, metric]));
  const exportReady = Number(byKey.get("export_ready")?.value ?? 0);
  const handoffReady = Number(byKey.get("handoff_ready")?.value ?? 0);
  const selected: PipelineDashboardMetric[] = [];

  const backlog = byKey.get("active_backlog");
  if (backlog) selected.push(backlog);

  const attention = byKey.get("attention_items");
  if (attention) selected.push(attention);

  selected.push({
    key: "ready_outbound",
    label: t("opsPipeline.readyOutbound"),
    value: exportReady + handoffReady,
    detail: t("opsPipeline.readyOutboundDetail"),
  });

  const published = byKey.get("published");
  if (published) selected.push(published);

  return selected;
}

function kpiTone(key: string, overall: PipelineDashboardStatus): OpsTone {
  if (key === "attention_items") return toneForStatus(overall);
  if (key === "ready_outbound") return "good";
  if (key === "published") return "good";
  return "muted";
}

function summaryMetricDescription(key: string, t: (key: string) => string): string {
  const map: Record<string, string> = {
    active_backlog: t("opsPipeline.metricBacklog"),
    attention_items: t("opsPipeline.metricAttention"),
    ready_outbound: t("opsPipeline.readyOutboundDetail"),
    published: t("opsPipeline.metricPublished"),
  };
  return map[key] ?? t("opsPipeline.metricDefault");
}

function humanizeDetail(detail: string): string {
  return detail.replace(/\b([A-Z][A-Z0-9_]{2,})\b/g, (rawStatus) => humanizeStatus(rawStatus));
}

function severityRank(severity: PipelineDashboardAttentionItem["severity"]): number {
  if (severity === "critical") return 0;
  if (severity === "warning") return 1;
  return 2;
}

function toneForStatus(status: PipelineDashboardStatus): OpsTone {
  if (status === "blocked") return "danger";
  if (status === "needs_attention") return "warn";
  if (status === "healthy" || status === "in_progress") return "good";
  return "muted";
}

function toneForSeverity(severity: PipelineDashboardAttentionItem["severity"]): OpsTone {
  if (severity === "critical") return "danger";
  if (severity === "warning") return "warn";
  return "muted";
}

function activityStageTone(stageKey: PipelineStageKey): OpsTone {
  if (stageKey === "reup_queue") return "warn";
  if (stageKey === "publish_progress" || stageKey === "publish_handoff") return "good";
  if (stageKey === "export_package") return "muted";
  return "muted";
}

function statusLabel(status: PipelineDashboardStatus, t: (key: string) => string): string {
  const map: Record<PipelineDashboardStatus, string> = {
    healthy: t("opsPipeline.statusHealthy"),
    needs_attention: t("opsPipeline.statusNeedsAttention"),
    blocked: t("opsPipeline.statusBlocked"),
    quiet: t("opsPipeline.statusQuiet"),
    in_progress: t("opsPipeline.statusInProgress"),
  };
  return map[status];
}

function severityLabel(severity: PipelineDashboardAttentionItem["severity"], t: (key: string) => string): string {
  const map: Record<PipelineDashboardAttentionItem["severity"], string> = {
    info: t("opsPipeline.severityInfo"),
    warning: t("opsPipeline.severityWarning"),
    critical: t("opsPipeline.severityCritical"),
  };
  return map[severity];
}

function stageKeyLabel(stageKey: string, t: (key: string) => string): string {
  const map: Record<string, string> = {
    capture: t("opsPipeline.stageCapture"),
    review: t("opsPipeline.stageReview"),
    reup_queue: t("opsPipeline.stageReupQueue"),
    export_package: t("opsPipeline.stageExport"),
    publish_handoff: t("opsPipeline.stageHandoff"),
    publish_progress: t("opsPipeline.stagePublish"),
  };
  return map[stageKey] ?? stageKey;
}
