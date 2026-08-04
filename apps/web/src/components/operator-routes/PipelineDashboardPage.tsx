"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchPipelineDashboard } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
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
import { OpsState, formatDateTime, type OpsTone } from "../ops-console/OpsShared";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";

const EXCEPTION_LIMIT = 8;
const ACTION_DECK_LIMIT = 3;
const ACTIVITY_CLUSTER_WINDOW_MS = 2 * 60 * 1000;

type BucketKey = "waiting" | "running" | "review" | "failed" | "ready";
type PipelineGroupKey = "intake" | "production" | "delivery";

const PIPELINE_GROUPS: Array<{ key: PipelineGroupKey; labelKey: string; stageKeys: PipelineStageKey[] }> = [
  { key: "intake", labelKey: "opsPipeline.groupIntake", stageKeys: ["capture", "review", "reup_queue"] },
  { key: "production", labelKey: "opsPipeline.groupProduction", stageKeys: ["download", "audio_analysis", "translate", "tts", "ocr", "render", "output_review"] },
  { key: "delivery", labelKey: "opsPipeline.groupDelivery", stageKeys: ["draft", "export_package", "publish_handoff"] },
];

const PIPELINE_STAGE_ORDER = PIPELINE_GROUPS.flatMap((group) => group.stageKeys);

const BUCKETS: Array<{ key: BucketKey; labelKey: string }> = [
  { key: "waiting", labelKey: "opsPipeline.bucketWaiting" },
  { key: "running", labelKey: "opsPipeline.bucketRunning" },
  { key: "review", labelKey: "opsPipeline.bucketReview" },
  { key: "failed", labelKey: "opsPipeline.bucketFailed" },
  { key: "ready", labelKey: "opsPipeline.bucketReady" },
];

function PipelineChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ops-pipeline-chip tone-${tone}`}>{label}</span>;
}

function PipelineOpenIcon() {
  return (
    <svg className="ops-pipeline-open-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PipelineStatusBeacon({ status }: { status: PipelineDashboardStatus }) {
  const calm = status === "healthy" || status === "in_progress" || status === "quiet";
  return (
    <span aria-hidden="true" className="ops-pipeline-control-strip__beacon">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M12 3.5l6.5 2.6v5.2c0 4-2.55 7.25-6.5 9.2-3.95-1.95-6.5-5.2-6.5-9.2V6.1L12 3.5z" stroke="currentColor" strokeWidth="1.55" strokeLinejoin="round" />
        {calm ? (
          <path d="M8.8 12l2.05 2.05 4.45-4.45" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        ) : (
          <>
            <path d="M12 7.8v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <circle cx="12" cy="15.8" r="0.9" fill="currentColor" />
          </>
        )}
      </svg>
    </span>
  );
}

function PipelineClockIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <circle cx="12" cy="12" r="8.25" stroke="currentColor" strokeWidth="1.65" />
      <path d="M12 7.5v4.9l3.2 1.9" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PipelineMetricIcon({ metricKey }: { metricKey: string }) {
  if (metricKey === "attention_items") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <path d="M10.25 4.75L3.6 17a1.55 1.55 0 001.36 2.25h14.08A1.55 1.55 0 0020.4 17L13.75 4.75a2 2 0 00-3.5 0z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M12 9v4.25" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        <circle cx="12" cy="16.25" r="0.9" fill="currentColor" />
      </svg>
    );
  }
  if (metricKey === "running") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <circle cx="12" cy="12" r="8.25" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10.2 8.75l5.1 3.25-5.1 3.25v-6.5z" stroke="currentColor" strokeWidth="1.55" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <rect x="5" y="7.25" width="14" height="11.5" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 7.25V5.9a1.65 1.65 0 011.65-1.65h4.7A1.65 1.65 0 0116 5.9v1.35M8.5 11.25h7M8.5 14.5h4.5" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" />
    </svg>
  );
}

function PipelinePanelGlyph({ kind }: { kind: "bottleneck" | "qa" | "action" | "activity" }) {
  return (
    <span aria-hidden="true" className={`ops-pipeline-panel-glyph is-${kind}`}>
      <svg viewBox="0 0 24 24" fill="none">
        {kind === "bottleneck" ? <><path d="M5 18.5V14h3v4.5H5zm5.5 0V9.5h3v9h-3zm5.5 0V5h3v13.5h-3z" stroke="currentColor" strokeWidth="1.55" strokeLinejoin="round" /><path d="M4 20h16" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" /></> : null}
        {kind === "qa" ? <><path d="M12 3.8l6 2.4V11c0 3.7-2.35 6.7-6 8.5-3.65-1.8-6-4.8-6-8.5V6.2l6-2.4z" stroke="currentColor" strokeWidth="1.55" strokeLinejoin="round" /><path d="M9.1 11.7l1.85 1.85 4-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></> : null}
        {kind === "action" ? <><path d="M10.25 4.75L3.6 17a1.55 1.55 0 001.36 2.25h14.08A1.55 1.55 0 0020.4 17L13.75 4.75a2 2 0 00-3.5 0z" stroke="currentColor" strokeWidth="1.55" strokeLinejoin="round" /><path d="M12 9v4.2M12 16.2h.01" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></> : null}
        {kind === "activity" ? <path d="M3.5 12h3l1.8-4.25 3.1 8.5 2.4-5.25 1.35 2.4h5.35" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /> : null}
      </svg>
    </span>
  );
}

function PipelineStageGlyph({ stageKey }: { stageKey: PipelineStageKey }) {
  const group = pipelineGroupForStage(stageKey);
  return (
    <span aria-hidden="true" className={`ops-pipeline-stage-glyph is-${group}`}>
      <svg viewBox="0 0 24 24" fill="none">
        {stageKey === "ocr" ? <><path d="M8 4.5H5.5V7M16 4.5h2.5V7M8 19.5H5.5V17M16 19.5h2.5V17" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" /><path d="M8.5 9h7M8.5 12h7M8.5 15h4.5" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" /></> : null}
        {stageKey === "tts" || stageKey === "audio_analysis" ? <path d="M4.5 12h2l1.3-4 2.1 8 2.2-10 2.1 12 1.8-7 1.3 3h2.2" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" /> : null}
        {stageKey === "render" || stageKey === "output_review" ? <><rect x="4.5" y="6" width="15" height="12" rx="2.2" stroke="currentColor" strokeWidth="1.55" /><path d="M10 9.25l5 2.75-5 2.75v-5.5z" stroke="currentColor" strokeWidth="1.45" strokeLinejoin="round" /></> : null}
        {group === "intake" ? <><path d="M5 8h14l-1.2 10H6.2L5 8z" stroke="currentColor" strokeWidth="1.55" strokeLinejoin="round" /><path d="M8 8l1.2-3h5.6L16 8M8.5 12h7" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" /></> : null}
        {group === "delivery" ? <><path d="M5 7.5L12 4l7 3.5v9L12 20l-7-3.5v-9z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="M5.5 7.8L12 11l6.5-3.2M12 11v8.5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></> : null}
        {group === "production" && stageKey !== "ocr" && stageKey !== "tts" && stageKey !== "audio_analysis" && stageKey !== "render" && stageKey !== "output_review" ? <><circle cx="7" cy="12" r="2.3" stroke="currentColor" strokeWidth="1.5" /><circle cx="17" cy="7" r="2.3" stroke="currentColor" strokeWidth="1.5" /><circle cx="17" cy="17" r="2.3" stroke="currentColor" strokeWidth="1.5" /><path d="M9.2 11l5.5-3M9.2 13l5.5 3" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" /></> : null}
      </svg>
    </span>
  );
}

function PipelineStageMarker({ stageKey }: { stageKey: PipelineStageKey }) {
  const stageIndex = PIPELINE_STAGE_ORDER.indexOf(stageKey);
  const group = pipelineGroupForStage(stageKey);
  return (
    <span aria-hidden="true" className={`ops-pipeline-stage-marker is-${group}`}>
      {String(stageIndex >= 0 ? stageIndex + 1 : 0).padStart(2, "0")}
    </span>
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

  const refreshAction = <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />;

  if (!dashboard && !request.error) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsPipeline.description")} title={t("opsPipeline.title")}>
        <AsyncContentBoundary skeletonVariant="detail" loadingLabel={t("opsPipeline.loadingDetail")} status="loading"><span /></AsyncContentBoundary>
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
        <PipelineDashboardBody dashboard={dashboard} t={t} />
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}

function PipelineDashboardBody({ dashboard, t }: { dashboard: PipelineDashboardResponse; t: (key: string) => string }) {
  const initialStage = useMemo(() => findFocusStage(dashboard.stages), [dashboard.stages]);
  const [selectedStageKey, setSelectedStageKey] = useState<PipelineStageKey>(initialStage.key);
  const selectedStage = dashboard.stages.find((stage) => stage.key === selectedStageKey) ?? initialStage;
  const selectedAttention = dashboard.attention_items.filter((item) => item.stage_key === selectedStage.key && item.severity !== "info");
  const controlMetrics = useMemo(() => selectControlMetrics(dashboard.summary_metrics), [dashboard.summary_metrics]);
  const exceptions = useMemo(() => pickExceptions(dashboard.attention_items), [dashboard.attention_items]);

  return (
    <main className="ops-page ops-pipeline-page ops-pipeline-operations">
      <ControlStrip dashboard={dashboard} metrics={controlMetrics} t={t} />

      <section className="ops-pipeline-studio-grid">
        <section className="ops-pipeline-board" aria-labelledby="pipeline-board-title">
          <header className="ops-pipeline-section-head">
            <div>
              <span>{t("opsPipeline.liveSnapshot")}</span>
              <h2 id="pipeline-board-title">{t("opsPipeline.pipelineFlow")}</h2>
            </div>
            <p>{t("opsPipeline.pipelineFlowDetail")}</p>
          </header>
          <PipelineFlowMap
            selectedStageKey={selectedStage.key}
            setSelectedStageKey={setSelectedStageKey}
            stages={dashboard.stages}
            t={t}
          />
        </section>

        <StageInspector
          attention={selectedAttention}
          selectedStage={selectedStage}
          t={t}
        />
      </section>

      <section className="ops-pipeline-analytics-grid" aria-label={t("opsPipeline.analytics")}>
        <BottleneckSpotlight items={dashboard.attention_items} t={t} />
        <OutputQaGauge summary={dashboard.output_qa_summary} t={t} />
      </section>

      <section className="ops-pipeline-lower-grid">
        <ActionDeck items={exceptions} t={t} />
        <ActivityPulse items={dashboard.recent_activity} t={t} />
      </section>

      <p className="ops-pipeline-footnote">{t("opsPipeline.readOnlyFootnote")}</p>
    </main>
  );
}

function ControlStrip({ dashboard, metrics, t }: { dashboard: PipelineDashboardResponse; metrics: PipelineDashboardMetric[]; t: (key: string) => string }) {
  return (
    <section className={`ops-pipeline-control-strip is-${dashboard.overall_status}`} aria-label={t("opsPipeline.summary")}>
      <div className="ops-pipeline-control-strip__status">
        <PipelineStatusBeacon status={dashboard.overall_status} />
        <div className="ops-pipeline-control-strip__copy">
          <div className="ops-pipeline-control-strip__meta">
            <PipelineChip label={statusLabel(dashboard.overall_status, t)} tone={toneForStatus(dashboard.overall_status)} />
            <span className="ops-pipeline-control-strip__time"><PipelineClockIcon />{t("opsPipeline.loadedAt")} <time dateTime={dashboard.generated_at}>{formatDateTime(dashboard.generated_at)}</time></span>
          </div>
          <strong>{dashboard.headline}</strong>
        </div>
      </div>
      <dl className="ops-pipeline-control-strip__metrics">
        {metrics.map((metric) => (
          <div className={`is-${metric.key}${metric.value > 0 ? " has-value" : ""}`} key={metric.key} title={metric.detail ?? undefined}>
            <span className="ops-pipeline-control-strip__metric-icon"><PipelineMetricIcon metricKey={metric.key} /></span>
            <dt>{metric.label}</dt>
            <dd>{metric.value}</dd>
            <small>{controlMetricHint(metric.key, t)}</small>
          </div>
        ))}
      </dl>
    </section>
  );
}

function PipelineFlowMap({ selectedStageKey, setSelectedStageKey, stages, t }: { selectedStageKey: PipelineStageKey; setSelectedStageKey: (key: PipelineStageKey) => void; stages: PipelineDashboardStage[]; t: (key: string) => string }) {
  const stageByKey = new Map(stages.map((stage) => [stage.key, stage]));
  return (
    <div className="ops-pipeline-composition">
      <div className="ops-pipeline-composition__legend" aria-label={t("opsPipeline.legend")}>
        {BUCKETS.map((bucket) => <span className={`is-${bucket.key}`} key={bucket.key}><i aria-hidden="true" />{t(bucket.labelKey)}</span>)}
      </div>
      <div className="ops-pipeline-composition__groups">
        {PIPELINE_GROUPS.map((group) => (
          <section aria-labelledby={`pipeline-group-${group.key}`} className={`ops-pipeline-composition__group is-${group.key}`} key={group.key}>
            <h3 id={`pipeline-group-${group.key}`}>
              <span><i aria-hidden="true" />{t(group.labelKey)}</span>
              <small>{group.stageKeys.length} {t("opsPipeline.stages")}</small>
            </h3>
            {group.stageKeys.map((stageKey) => {
              const stage = stageByKey.get(stageKey);
              if (!stage) return null;
              const selected = stage.key === selectedStageKey;
              const bucketSummary = BUCKETS.map((bucket) => `${t(bucket.labelKey)}: ${bucketValue(stage, bucket.key)}`).join(", ");
              return (
                <div className={`ops-pipeline-composition__row is-${stage.status}${selected ? " is-selected" : ""}`} data-stage-key={stage.key} key={stage.key}>
                  <button aria-pressed={selected} className="ops-pipeline-composition__select" onClick={() => setSelectedStageKey(stage.key)} type="button">
                    <span className="ops-pipeline-composition__identity">
                      <PipelineStageMarker stageKey={stage.key} />
                      <span>{stage.label}</span>
                    </span>
                    <span className="ops-pipeline-composition__node-state"><i aria-hidden="true" />{statusLabel(stage.status, t)}</span>
                    <span className="ops-pipeline-composition__total"><b>{stage.total_count}</b><small>{t("opsPipeline.workItems")}</small></span>
                    <span aria-label={`${stage.label}. ${bucketSummary}`} className="ops-pipeline-composition__track" role="img">
                      {stage.total_count > 0 ? BUCKETS.map((bucket) => {
                        const value = bucketValue(stage, bucket.key);
                        if (value <= 0) return null;
                        return <span className={`ops-pipeline-composition__segment is-${bucket.key}`} key={bucket.key} style={{ width: `${(value / stage.total_count) * 100}%` }} title={`${t(bucket.labelKey)}: ${value}`} />;
                      }) : <span className="ops-pipeline-composition__empty">{t("opsPipeline.noWorkload")}</span>}
                    </span>
                  </button>
                  <PipelineOpenLink href={stage.href} label={`${t("opsPipeline.open")} ${stage.label}`} />
                </div>
              );
            })}
          </section>
        ))}
      </div>
    </div>
  );
}

function BottleneckSpotlight({ items, t }: { items: PipelineDashboardAttentionItem[]; t: (key: string) => string }) {
  const rankedItems = [...items]
    .filter((item) => item.severity !== "info" && item.count > 0)
    .sort((a, b) => b.count - a.count || severityRank(a.severity) - severityRank(b.severity))
    .slice(0, EXCEPTION_LIMIT);
  const maximum = Math.max(1, ...rankedItems.map((item) => item.count));
  const total = rankedItems.reduce((sum, item) => sum + item.count, 0);
  const featured = rankedItems[0];
  const remaining = rankedItems.slice(1);
  return (
    <section className="ops-pipeline-flat-section ops-pipeline-bottleneck-spotlight" aria-labelledby="pipeline-bottlenecks-title">
      <header className="ops-pipeline-visual-head">
        <div><PipelinePanelGlyph kind="bottleneck" /><span className="ops-pipeline-visual-head__title"><small>{t("opsPipeline.workloadRanking")}</small><h2 id="pipeline-bottlenecks-title">{t("opsPipeline.bottlenecks")}</h2></span></div>
        <span className="ops-pipeline-visual-head__count"><b>{rankedItems.length}</b>{t("opsPipeline.categories")}</span>
      </header>
      {featured ? (
        <div className="ops-pipeline-bottleneck-spotlight__layout">
          <Link className={`ops-pipeline-bottleneck-spotlight__hero is-${featured.severity}`} href={featured.href} title={featured.recommended_action}>
            <span className="ops-pipeline-bottleneck-spotlight__rank">#1</span>
            <PipelineStageGlyph stageKey={featured.stage_key} />
            <span className="ops-pipeline-bottleneck-spotlight__copy"><small>{stageKeyLabel(featured.stage_key, t)}</small><strong>{featured.title}</strong></span>
            <span className="ops-pipeline-bottleneck-spotlight__value"><b>{featured.count}</b><small>{t("opsPipeline.affected")}</small></span>
            <span className="ops-pipeline-bottleneck-spotlight__share">{total > 0 ? Math.round((featured.count / total) * 100) : 0}%</span>
            <span className="ops-pipeline-bottleneck-spotlight__open"><PipelineOpenIcon /></span>
            <span className="ops-pipeline-bottleneck-spotlight__hero-meter"><i style={{ width: `${(featured.count / maximum) * 100}%` }} /></span>
          </Link>
          <ol>{remaining.map((item, index) => (
            <li className={`is-${item.severity}`} key={item.id}>
              <Link href={item.href} title={item.recommended_action}>
                <span className="ops-pipeline-bottleneck-spotlight__rank">#{index + 2}</span>
                <PipelineStageGlyph stageKey={item.stage_key} />
                <span className="ops-pipeline-bottleneck-spotlight__copy"><small>{stageKeyLabel(item.stage_key, t)}</small><strong>{item.title}</strong></span>
                <span className="ops-pipeline-bottleneck-spotlight__mini-meter"><i style={{ width: `${(item.count / maximum) * 100}%` }} /></span>
                <b>{item.count}</b>
                <PipelineOpenIcon />
              </Link>
            </li>
          ))}</ol>
        </div>
      ) : <p className="ops-pipeline-empty">{t("opsPipeline.noAttention")}</p>}
    </section>
  );
}

function OutputQaGauge({ summary, t }: { summary: PipelineDashboardResponse["output_qa_summary"]; t: (key: string) => string }) {
  const values = [
    { key: "passed", label: t("opsPipeline.qaPassed"), value: summary.passed },
    { key: "warned", label: t("opsPipeline.qaWarned"), value: summary.warned },
    { key: "failed", label: t("opsPipeline.qaFailed"), value: summary.failed },
    { key: "ungraded", label: t("opsPipeline.qaUngraded"), value: summary.ungraded },
  ];
  const total = summary.total;
  const summaryLabel = values.map((item) => `${item.label}: ${item.value}`).join(", ");
  const passedStop = total > 0 ? (summary.passed / total) * 100 : 0;
  const warnedStop = total > 0 ? passedStop + (summary.warned / total) * 100 : 0;
  const failedStop = total > 0 ? warnedStop + (summary.failed / total) * 100 : 0;
  const gaugeBackground = `conic-gradient(#22c55e 0 ${passedStop}%, #f59e0b ${passedStop}% ${warnedStop}%, #ef4444 ${warnedStop}% ${failedStop}%, #94a3b8 ${failedStop}% 100%)`;
  return (
    <section className={`ops-pipeline-flat-section ops-pipeline-qa-gauge${total === 0 ? " is-empty" : ""}`} aria-labelledby="pipeline-output-qa-title">
      <header className="ops-pipeline-visual-head">
        <div><PipelinePanelGlyph kind="qa" /><span className="ops-pipeline-visual-head__title"><small>{t("opsPipeline.qualityGate")}</small><h2 id="pipeline-output-qa-title">{t("opsPipeline.outputQa")}</h2></span></div>
        <PipelineOpenLink href="/production/output-review" label={`${t("opsPipeline.open")} ${t("opsPipeline.outputQa")}`} />
      </header>
      {total > 0 ? (
        <div className="ops-pipeline-qa-gauge__content">
          <div aria-label={summaryLabel} className="ops-pipeline-qa-gauge__ring" role="img" style={{ background: gaugeBackground }}>
            <span><b>{total}</b><small>{t("opsPipeline.qaOutputs")}</small></span>
          </div>
          <dl>{values.map((item) => (
            <div className={`is-${item.key}`} key={item.key}><dt><i aria-hidden="true" />{item.label}</dt><dd><b>{item.value}</b><small>{Math.round((item.value / total) * 100)}%</small></dd></div>
          ))}</dl>
        </div>
      ) : (
        <div className="ops-pipeline-qa-gauge__empty">
          <span className="ops-pipeline-qa-gauge__empty-ring"><PipelinePanelGlyph kind="qa" /><b>0</b></span>
          <strong>{t("opsPipeline.qaAwaiting")}</strong>
          <small>{t("opsPipeline.qaAwaitingHint")}</small>
        </div>
      )}
    </section>
  );
}

function StageInspector({ attention, selectedStage, t }: { attention: PipelineDashboardAttentionItem[]; selectedStage: PipelineDashboardStage; t: (key: string) => string }) {
  return (
    <aside aria-live="polite" className={`ops-pipeline-inspector is-${selectedStage.status}`} aria-labelledby="pipeline-inspector-title">
      <header className="ops-pipeline-inspector__head">
        <div className="ops-pipeline-inspector__identity">
          <PipelineStageMarker stageKey={selectedStage.key} />
          <div>
            <span>{t("opsPipeline.stageInspector")}</span>
            <h2 id="pipeline-inspector-title">{selectedStage.label}</h2>
          </div>
        </div>
        <PipelineChip label={statusLabel(selectedStage.status, t)} tone={toneForStatus(selectedStage.status)} />
        <Link className="ops-pipeline-inspector__open" href={selectedStage.href}>{t("opsPipeline.openStage")}<PipelineOpenIcon /></Link>
      </header>
      <div className="ops-pipeline-inspector__content">
        <div className="ops-pipeline-inspector__summary">
          <p>{selectedStage.description}</p>
          <dl>
            {BUCKETS.map((bucket) => (
              <div className={`is-${bucket.key}`} key={bucket.key}><dt>{t(bucket.labelKey)}</dt><dd>{bucketValue(selectedStage, bucket.key)}</dd></div>
            ))}
          </dl>
        </div>
        <div className="ops-pipeline-inspector__action">
          <span>{t("opsPipeline.recommendedAction")}</span>
          <strong>{selectedStage.next_action}</strong>
          {attention.length > 0 ? (
            <ul>{attention.map((item) => <li key={item.id}><PipelineChip label={severityLabel(item.severity, t)} tone={toneForSeverity(item.severity)} /><span>{item.title}</span><b>{item.count}</b></li>)}</ul>
          ) : <p>{t("opsPipeline.noStageExceptions")}</p>}
        </div>
      </div>
    </aside>
  );
}

function ActionDeck({ items, t }: { items: PipelineDashboardAttentionItem[]; t: (key: string) => string }) {
  const priorityItems = items.slice(0, ACTION_DECK_LIMIT);
  return (
    <section className="ops-pipeline-flat-section ops-pipeline-action-deck" aria-labelledby="pipeline-actions-title">
      <header className="ops-pipeline-visual-head">
        <div><PipelinePanelGlyph kind="action" /><span className="ops-pipeline-visual-head__title"><small>{t("opsPipeline.doFirst")}</small><h2 id="pipeline-actions-title">{t("opsPipeline.priorityActions")}</h2></span></div>
        <span className="ops-pipeline-visual-head__count"><b>{priorityItems.length}/{items.length}</b>{t("opsPipeline.actions")}</span>
      </header>
      {priorityItems.length > 0 ? (
        <div className="ops-pipeline-action-deck__grid">{priorityItems.map((item, index) => (
          <Link className={`ops-pipeline-action-deck__card is-${item.severity}`} data-priority={index + 1} href={item.href} key={item.id} title={`${item.title}: ${item.recommended_action}`}>
            <span aria-label={severityLabel(item.severity, t)} className="ops-pipeline-action-deck__severity" role="img">
              <svg viewBox="0 0 24 24" aria-hidden="true" fill="none"><path d="M12 8v5M12 16.5h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /><circle cx="12" cy="12" r="8.25" stroke="currentColor" strokeWidth="1.55" /></svg>
            </span>
            <PipelineStageGlyph stageKey={item.stage_key} />
            <span className="ops-pipeline-action-deck__copy"><small>#{index + 1} · {stageKeyLabel(item.stage_key, t)}</small><strong>{item.recommended_action}</strong></span>
            <span className="ops-pipeline-action-deck__count"><b>{item.count}</b><small>{t("opsPipeline.affected")}</small></span>
            <span className="ops-pipeline-action-deck__open"><PipelineOpenIcon /></span>
            <span className="ops-pipeline-action-deck__reveal">{item.title}</span>
          </Link>
        ))}</div>
      ) : <p className="ops-pipeline-empty">{t("opsPipeline.noAttention")}</p>}
    </section>
  );
}

function ActivityPulse({ items, t }: { items: PipelineDashboardActivityItem[]; t: (key: string) => string }) {
  const clusteredItems = clusterActivity(items).slice(0, 8);
  const stageCounts = new Map<PipelineStageKey, number>();
  items.forEach((item) => stageCounts.set(item.stage_key, (stageCounts.get(item.stage_key) ?? 0) + 1));
  const activeStages = [...stageCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  return (
    <section className="ops-pipeline-flat-section ops-pipeline-activity-pulse" aria-labelledby="pipeline-activity-title">
      <header className="ops-pipeline-visual-head">
        <div><PipelinePanelGlyph kind="activity" /><span className="ops-pipeline-visual-head__title"><small>{t("opsPipeline.latestMovement")}</small><h2 id="pipeline-activity-title">{t("opsPipeline.activityPulse")}</h2></span></div>
        <span className="ops-pipeline-visual-head__count"><b>{items.length}</b>{t("opsPipeline.signals")}</span>
      </header>
      {items.length > 0 ? (
        <>
          <div className="ops-pipeline-activity-pulse__summary" aria-label={t("opsPipeline.activityByStage")}>{activeStages.map(([stageKey, count]) => (
            <span key={stageKey} title={stageKeyLabel(stageKey, t)}><PipelineStageGlyph stageKey={stageKey} /><small>{stageKeyLabel(stageKey, t)}</small><b>{count}</b></span>
          ))}</div>
          <ol>{clusteredItems.map((item) => (
            <li className={`is-${pipelineGroupForStage(item.stage_key)}`} key={item.id}>
              <Link href={item.href} title={humanizeDetail(item.detail)}>
                <time dateTime={item.occurred_at} title={`${formatDateTime(item.earliest_at)} – ${formatDateTime(item.occurred_at)}`}>{formatActivityTimeRange(item.occurred_at, item.earliest_at)}</time>
                <PipelineStageGlyph stageKey={item.stage_key} />
                <span className="ops-pipeline-activity-pulse__copy"><strong>{item.title}</strong><small>{stageKeyLabel(item.stage_key, t)}</small></span>
                {item.repeat_count > 1 ? <span className="ops-pipeline-activity-pulse__repeat">×{item.repeat_count}</span> : null}
                <PipelineOpenIcon />
                <span className="visually-hidden">{humanizeDetail(item.detail)}</span>
              </Link>
            </li>
          ))}</ol>
        </>
      ) : <p className="ops-pipeline-empty">{t("opsPipeline.noRecentActivity")}</p>}
    </section>
  );
}

function bucketValue(stage: PipelineDashboardStage, bucket: BucketKey) {
  const values: Record<BucketKey, number> = {
    waiting: stage.waiting_count,
    running: stage.running_count,
    review: stage.review_count,
    failed: stage.failed_count,
    ready: stage.ready_count,
  };
  return values[bucket];
}

function pipelineGroupForStage(stageKey: PipelineStageKey): PipelineGroupKey {
  return PIPELINE_GROUPS.find((group) => group.stageKeys.includes(stageKey))?.key ?? "production";
}

function findFocusStage(stages: PipelineDashboardStage[]) {
  return stages.find((stage) => stage.failed_count > 0)
    ?? stages.find((stage) => stage.review_count > 0 || stage.waiting_count > 0)
    ?? stages.find((stage) => stage.running_count > 0)
    ?? stages[0];
}

function selectControlMetrics(metrics: PipelineDashboardMetric[]) {
  const byKey = new Map(metrics.map((metric) => [metric.key, metric]));
  return ["active_backlog", "attention_items", "running"].map((key) => byKey.get(key)).filter((metric): metric is PipelineDashboardMetric => Boolean(metric));
}

function controlMetricHint(metricKey: string, t: (key: string) => string) {
  const hints: Record<string, string> = {
    active_backlog: t("opsPipeline.metricBacklogHint"),
    attention_items: t("opsPipeline.metricAttentionHint"),
    running: t("opsPipeline.metricRunningHint"),
  };
  return hints[metricKey] ?? t("opsPipeline.metricDefaultHint");
}

function pickExceptions(items: PipelineDashboardAttentionItem[]) {
  return [...items]
    .filter((item) => item.severity !== "info")
    .sort((a, b) => severityRank(a.severity) - severityRank(b.severity) || b.count - a.count)
    .slice(0, EXCEPTION_LIMIT);
}

function clusterActivity(items: PipelineDashboardActivityItem[]) {
  const clusters: Array<PipelineDashboardActivityItem & { earliest_at: string; repeat_count: number }> = [];
  const clusterBySignature = new Map<string, PipelineDashboardActivityItem & { earliest_at: string; repeat_count: number }>();
  items.forEach((item) => {
    const signature = JSON.stringify([item.stage_key, item.title, item.detail, item.href]);
    const existing = clusterBySignature.get(signature);
    const existingTime = existing ? new Date(existing.occurred_at).getTime() : Number.NaN;
    const itemTime = new Date(item.occurred_at).getTime();
    const withinClusterWindow = existing && Number.isFinite(existingTime) && Number.isFinite(itemTime) && Math.abs(existingTime - itemTime) <= ACTIVITY_CLUSTER_WINDOW_MS;
    if (existing && withinClusterWindow) {
      existing.repeat_count += 1;
      existing.earliest_at = item.occurred_at;
      return;
    }
    const cluster = { ...item, earliest_at: item.occurred_at, repeat_count: 1 };
    clusterBySignature.set(signature, cluster);
    clusters.push(cluster);
  });
  return clusters;
}

function formatActivityTimeRange(latestValue: string, earliestValue: string) {
  const latest = new Date(latestValue);
  const earliest = new Date(earliestValue);
  if (Number.isNaN(latest.getTime()) || Number.isNaN(earliest.getTime()) || latest.getTime() === earliest.getTime()) return formatCompactActivityTime(latestValue);
  const time = (date: Date) => date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  if (time(earliest) === time(latest)) return formatCompactActivityTime(latestValue);
  return `${time(earliest)}–${time(latest)}`;
}

function formatCompactActivityTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false })} · ${date.getDate()}/${date.getMonth() + 1}`;
}

function humanizeDetail(detail: string) {
  return detail.replace(/\b([A-Z][A-Z0-9_]{2,})\b/g, (rawStatus) => rawStatus.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()));
}

function severityRank(severity: PipelineDashboardAttentionItem["severity"]) {
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

function statusLabel(status: PipelineDashboardStatus, t: (key: string) => string) {
  return { healthy: t("opsPipeline.statusHealthy"), needs_attention: t("opsPipeline.statusNeedsAttention"), blocked: t("opsPipeline.statusBlocked"), quiet: t("opsPipeline.statusQuiet"), in_progress: t("opsPipeline.statusInProgress") }[status];
}

function severityLabel(severity: PipelineDashboardAttentionItem["severity"], t: (key: string) => string) {
  return { info: t("opsPipeline.severityInfo"), warning: t("opsPipeline.severityWarning"), critical: t("opsPipeline.severityCritical") }[severity];
}

function stageKeyLabel(stageKey: PipelineStageKey, t: (key: string) => string) {
  const map: Record<PipelineStageKey, string> = {
    capture: t("opsPipeline.stageCapture"), review: t("opsPipeline.stageReview"), reup_queue: t("opsPipeline.stageReupQueue"), download: t("opsPipeline.stageDownload"), audio_analysis: t("opsPipeline.stageAudio"), translate: t("opsPipeline.stageTranslate"), tts: t("opsPipeline.stageTts"), ocr: t("opsPipeline.stageOcr"), render: t("opsPipeline.stageRender"), output_review: t("opsPipeline.stageOutputReview"), draft: t("opsPipeline.stageDraft"), export_package: t("opsPipeline.stageExport"), publish_handoff: t("opsPipeline.stageHandoff"),
  };
  return map[stageKey];
}
