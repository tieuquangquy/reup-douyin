"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchPipelineDashboard } from "../../lib/api";
import type {
  PipelineDashboardActivityItem,
  PipelineDashboardAttentionItem,
  PipelineDashboardMetric,
  PipelineDashboardResponse,
  PipelineDashboardStage,
  PipelineDashboardStatus
} from "../../types/operations";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { PageShell } from "../app-shell/PageShell";
import {
  OpsActionRow,
  OpsDetailPanel,
  OpsDetailSection,
  OpsItemCard,
  OpsMetadataList,
  OpsNextActionBanner,
  OpsStatePanel,
  OpsSummaryCards,
  OpsWorkflowContext,
  type OpsItemAction,
  type OpsSummaryCardItem,
  type OpsTone
} from "../ops-console/OpsShared";

const WORKFLOW_STEPS = ["Capture", "Review", "Reup Queue", "Export Package", "Publish Handoff", "Publish progress"];

const CANONICAL_PIPELINE_HREFS = {
  capture: "/ops/extensions/douyin/capture-inbox",
  review: "/selection/review-board",
  reupQueue: "/selection/reup-queue",
  exportPackages: "/publishing/export-packages",
  publishHandoffs: "/publishing/publish-handoffs",
  publishDrafts: "/publishing/drafts",
  publishHealth: "/ops/publish-health",
  publishAttempts: "/ops/publish-attempts",
  reconciliation: "/ops/reconciliation"
} as const;

export function PipelineDashboardPage() {
  const [dashboard, setDashboard] = useState<PipelineDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchPipelineDashboard();
      setDashboard(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pipeline dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const criticalAttention = useMemo(
    () => dashboard?.attention_items.filter((item) => item.severity === "critical") ?? [],
    [dashboard]
  );

  return (
    <OpsConsoleShell
      actions={<button type="button" onClick={() => void load()}>Refresh</button>}
      description="End-to-end command view for Capture, Review, Reup Queue, Export Package, Publish Handoff, and Publish progress."
      title="Pipeline Dashboard"
    >
      {loading ? <OpsStatePanel detail="Aggregating pipeline health, backlog, blockers, and recent movement from canonical workflow tables." title="Loading pipeline dashboard" variant="loading" /> : null}
      {!loading && error ? (
        <OpsStatePanel
          action={<button type="button" onClick={() => void load()}>Retry</button>}
          detail={error}
          title="Could not load pipeline dashboard"
          variant="error"
        />
      ) : null}
      {!loading && !error && !dashboard ? <OpsStatePanel detail="No dashboard payload was returned by the API." title="Pipeline dashboard unavailable" variant="empty" /> : null}
      {!loading && !error && dashboard ? (
        <PageShell
          actions={
            <>
              <a href={CANONICAL_PIPELINE_HREFS.capture}>Capture Inbox</a>
              <a href={CANONICAL_PIPELINE_HREFS.reupQueue}>Reup Queue</a>
              <a href={CANONICAL_PIPELINE_HREFS.publishHealth}>Publish Health</a>
            </>
          }
          description={`${statusLabel(dashboard.overall_status)} · Generated ${formatDateTime(dashboard.generated_at)}`}
          title="End-to-end workflow command center"
        >
          <OpsNextActionBanner
            actions={<OpsActionRow actions={nextActionLinks(dashboard)} />}
            description={dashboard.headline}
            title="Pipeline status"
            tone={toneForStatus(dashboard.overall_status)}
          />

          <OpsWorkflowContext
            currentStep="Canonical workflow boundary"
            metrics={[
              { label: "Overall status", value: statusLabel(dashboard.overall_status) },
              { label: "Attention items", value: dashboard.attention_items.length },
              { label: "Critical blockers", value: criticalAttention.length },
              { label: "Generated", value: formatDateTime(dashboard.generated_at) }
            ]}
            steps={WORKFLOW_STEPS}
          />

          <OpsSummaryCards cards={summaryCards(dashboard.summary_metrics, dashboard.overall_status)} hint="These API-aggregated metrics summarize the full pipeline without browser-side database inference." title="Pipeline summary" />

          <OpsDetailPanel title="Stage-by-stage progress">
            <div className="operator-quick-grid pipeline-stage-grid">
              {dashboard.stages.map((stage, index) => (
                <StageCard index={index} key={stage.key} stage={stage} totalStages={dashboard.stages.length} />
              ))}
            </div>
          </OpsDetailPanel>

          <div className="operator-quick-grid">
            <AttentionPanel items={dashboard.attention_items} />
            <RecentActivityPanel items={dashboard.recent_activity} />
          </div>

          <OpsDetailPanel title="Quick actions and drill-downs">
            <div className="operator-quick-grid">
              {dashboard.quick_links.map((link) => (
                <OpsItemCard
                  actions={[{ key: "open", label: "Open surface", href: link.href, tone: "primary" }]}
                  key={link.href}
                  metadata={[{ label: "Stage", value: link.stage_key ? stageKeyLabel(link.stage_key) : "General" }]}
                  statusLabel="Canonical surface"
                  statusTone="good"
                  title={link.label}
                >
                  <p>{link.description}</p>
                </OpsItemCard>
              ))}
            </div>
          </OpsDetailPanel>
        </PageShell>
      ) : null}
    </OpsConsoleShell>
  );
}

function StageCard({ index, stage, totalStages }: { index: number; stage: PipelineDashboardStage; totalStages: number }) {
  return (
    <OpsItemCard
      actions={[{ key: "open", label: `Open ${stage.label}`, href: stage.href, tone: "primary" }]}
      metadata={[
        { label: "Progress", value: `${index + 1} / ${totalStages}` },
        { label: stage.primary_label, value: stage.primary_count },
        { label: stage.secondary_label, value: stage.secondary_count },
        { label: "Attention", value: stage.attention_count }
      ]}
      preview={<PipelineStepMarker index={index} status={stage.status} />}
      statusLabel={statusLabel(stage.status)}
      statusTone={toneForStatus(stage.status)}
      title={stage.label}
    >
      <p>{stage.description}</p>
      <OpsDetailSection description={stage.next_action} title="Next action">
        {stage.metrics.length > 0 ? <OpsMetadataList items={stage.metrics.map((metric) => ({ label: metric.label, value: metric.detail ? `${metric.value} · ${metric.detail}` : metric.value }))} /> : <p className="muted">No additional stage metrics require attention.</p>}
      </OpsDetailSection>
    </OpsItemCard>
  );
}

function PipelineStepMarker({ index, status }: { index: number; status: PipelineDashboardStatus }) {
  return <strong className={`pipeline-step-marker ${toneForStatus(status)}`}>{index + 1}</strong>;
}

function AttentionPanel({ items }: { items: PipelineDashboardAttentionItem[] }) {
  return (
    <OpsDetailPanel title="Attention and blockers">
      {items.length === 0 ? <OpsStatePanel detail="No blockers or operator attention items are currently reported by the aggregation endpoint." title="No attention needed" variant="success" /> : null}
      {items.map((item) => (
        <OpsItemCard
          actions={[{ key: "open", label: "Open stage", href: item.href, tone: item.severity === "critical" ? "danger" : "primary" }]}
          key={item.id}
          metadata={[
            { label: "Stage", value: stageKeyLabel(item.stage_key) },
            { label: "Count", value: item.count }
          ]}
          statusLabel={severityLabel(item.severity)}
          statusTone={toneForSeverity(item.severity)}
          title={item.title}
        >
          <p>{item.detail}</p>
          <OpsDetailSection title="Recommended action">
            <p>{item.recommended_action}</p>
          </OpsDetailSection>
        </OpsItemCard>
      ))}
    </OpsDetailPanel>
  );
}

function RecentActivityPanel({ items }: { items: PipelineDashboardActivityItem[] }) {
  return (
    <OpsDetailPanel title="Recent activity">
      {items.length === 0 ? <OpsStatePanel detail="No recent stage updates were found. Start with Capture Inbox when new source content is ready." title="No recent activity" variant="empty" /> : null}
      {items.map((item) => (
        <OpsItemCard
          actions={[{ key: "open", label: "Open related surface", href: item.href, tone: "primary" }]}
          key={item.id}
          metadata={[
            { label: "Stage", value: stageKeyLabel(item.stage_key) },
            { label: "Updated", value: formatDateTime(item.occurred_at) }
          ]}
          statusLabel="Activity"
          statusTone="muted"
          title={item.title}
        >
          <p>{item.detail}</p>
        </OpsItemCard>
      ))}
    </OpsDetailPanel>
  );
}

function summaryCards(metrics: PipelineDashboardMetric[], status: PipelineDashboardStatus): OpsSummaryCardItem[] {
  return metrics.map((metric) => ({
    key: metric.key,
    label: metric.label,
    value: metric.value,
    description: metric.detail ?? summaryMetricDescription(metric.key),
    tone: metric.key === "attention_items" ? toneForStatus(status) : "muted"
  }));
}

function nextActionLinks(dashboard: PipelineDashboardResponse): OpsItemAction[] {
  const firstCritical = dashboard.attention_items.find((item) => item.severity === "critical");
  const firstAttention = dashboard.attention_items[0];
  const target = firstCritical ?? firstAttention;
  if (target) {
    return [
        { key: "attention", label: "Open top attention item", href: target.href, tone: target.severity === "critical" ? "danger" : "primary" },
        { key: "review", label: "Review Board", href: CANONICAL_PIPELINE_HREFS.review },
        { key: "publish", label: "Publish progress", href: CANONICAL_PIPELINE_HREFS.publishHealth }
    ];
  }
  return [
    { key: "capture", label: "Start Capture Inbox", href: CANONICAL_PIPELINE_HREFS.capture, tone: "primary" },
    { key: "queue", label: "Open Reup Queue", href: CANONICAL_PIPELINE_HREFS.reupQueue },
    { key: "drafts", label: "Open Publish Drafts", href: CANONICAL_PIPELINE_HREFS.publishDrafts }
  ];
}

function summaryMetricDescription(key: string): string {
  const descriptions: Record<string, string> = {
    captures_last_24h: "New capture sessions received in the last 24 hours.",
    active_backlog: "Review, queue, and publish work currently in motion.",
    attention_items: "Operator-facing items that should be cleared or monitored.",
    export_ready: "Queue or package records ready for export handoff work.",
    handoff_ready: "Publish Handoffs waiting for manual operator handling.",
    published: "Drafts with completed publication state."
  };
  return descriptions[key] ?? "Aggregated pipeline metric.";
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

function statusLabel(status: PipelineDashboardStatus): string {
  const labels: Record<PipelineDashboardStatus, string> = {
    healthy: "Healthy",
    needs_attention: "Needs attention",
    blocked: "Blocked",
    quiet: "Quiet",
    in_progress: "In progress"
  };
  return labels[status];
}

function severityLabel(severity: PipelineDashboardAttentionItem["severity"]): string {
  const labels: Record<PipelineDashboardAttentionItem["severity"], string> = {
    info: "Info",
    warning: "Warning",
    critical: "Critical"
  };
  return labels[severity];
}

function stageKeyLabel(stageKey: string): string {
  const labels: Record<string, string> = {
    capture: "Capture",
    review: "Review",
    reup_queue: "Reup Queue",
    export_package: "Export Package",
    publish_handoff: "Publish Handoff",
    publish_progress: "Publish progress"
  };
  return labels[stageKey] ?? stageKey;
}

function formatDateTime(value: string | null): string {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
