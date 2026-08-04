"use client";

import type {
  OperatorHomeCheckpoint,
  OperatorHomeMetric,
  OperatorHomePriorityItem,
  OperatorHomeRecentOutput,
  OperatorHomeStage,
  OperatorHomeSummaryResponse
} from "../../types/operations";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

function formatDuration(value: number | null): string {
  if (value == null) return "Duration unknown";
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function formatCheckpointAge(value: string | null, count: number): string {
  if (count === 0) return "No waiting age";
  return value ? `Oldest ${formatUpdatedAt(value)}` : "Age unavailable";
}

function statusLabel(status: OperatorHomeSummaryResponse["overall"]["status"]): string {
  if (status === "blocked") return "Blocked";
  if (status === "needs_attention") return "Needs attention";
  if (status === "in_progress") return "In progress";
  if (status === "healthy") return "Healthy";
  return "Quiet";
}

type PipelineCountKey =
  | "waiting_count"
  | "running_count"
  | "review_count"
  | "failed_count"
  | "ready_count";

const PIPELINE_SEGMENTS: Array<{ key: PipelineCountKey; label: string; className: string }> = [
  { key: "waiting_count", label: "Waiting", className: "is-waiting" },
  { key: "running_count", label: "Running", className: "is-running" },
  { key: "review_count", label: "Manual review", className: "is-review" },
  { key: "failed_count", label: "Failed", className: "is-failed" },
  { key: "ready_count", label: "Ready", className: "is-ready" }
];

function percent(value: number, total: number): number {
  return total > 0 ? (Math.max(0, value) / total) * 100 : 0;
}

function MetricIcon({ metricKey }: { metricKey: string }) {
  if (metricKey === "needs_attention") {
    return (
      <span aria-hidden="true" className="operator-home-v2-metric__icon is-needs-attention" data-metric-icon={metricKey}>
        <svg viewBox="0 0 24 24">
          <path d="M12 4.2 20 18H4L12 4.2Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
          <path d="M12 9v4.2M12 16.2h.01" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
        </svg>
      </span>
    );
  }
  if (metricKey === "in_progress") {
    return (
      <span aria-hidden="true" className="operator-home-v2-metric__icon is-in-progress" data-metric-icon={metricKey}>
        <svg viewBox="0 0 24 24">
          <circle cx="12" cy="12" fill="none" r="7.5" stroke="currentColor" strokeWidth="1.8" />
          <path d="M12 7.8v4.6l3.2 2" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
        </svg>
      </span>
    );
  }
  if (metricKey === "awaiting_review") {
    return (
      <span aria-hidden="true" className="operator-home-v2-metric__icon is-awaiting-review" data-metric-icon={metricKey}>
        <svg viewBox="0 0 24 24">
          <path d="M8 6.3H6.7A1.7 1.7 0 0 0 5 8v10.3A1.7 1.7 0 0 0 6.7 20h10.6a1.7 1.7 0 0 0 1.7-1.7V8a1.7 1.7 0 0 0-1.7-1.7H16" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
          <path d="M9.2 4.3h5.6a1 1 0 0 1 1 1v2h-7.6v-2a1 1 0 0 1 1-1ZM8.5 12h7M8.5 15.5h4.2" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
        </svg>
      </span>
    );
  }
  if (metricKey === "ready_downstream") {
    return (
      <span aria-hidden="true" className="operator-home-v2-metric__icon is-ready-downstream" data-metric-icon={metricKey}>
        <svg viewBox="0 0 24 24">
          <path d="M4.5 7.5 12 4l7.5 3.5v9L12 20l-7.5-3.5v-9Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
          <path d="m8.3 12.2 2.2 2.2 5.2-5.1" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
        </svg>
      </span>
    );
  }
  return null;
}

function MetricCard({ metric }: { metric: OperatorHomeMetric }) {
  const content = (
    <>
      <div className="operator-home-v2-metric__head">
        <span>{metric.label}</span>
        <MetricIcon metricKey={metric.key} />
      </div>
      <strong>{metric.value.toLocaleString()}</strong>
      <p>{metric.detail}</p>
    </>
  );
  return metric.href ? (
    <a className={`operator-home-v2-metric tone-${metric.tone}`} href={metric.href} title={metric.detail}>
      {content}
    </a>
  ) : (
    <article className={`operator-home-v2-metric tone-${metric.tone}`} title={metric.detail}>
      {content}
    </article>
  );
}

function PriorityStageIcon({ stageKey }: { stageKey: OperatorHomePriorityItem["stage_key"] }) {
  let glyph = <path d="M5 8.2h14v9.3H5V8.2Zm3-3.2h8v3.2H8V5Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />;
  if (stageKey === "capture") {
    glyph = <><path d="M5 8h14l-1.2 10H6.2L5 8Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="M8 8 9.2 5h5.6L16 8M9 12h6" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></>;
  } else if (stageKey === "review") {
    glyph = <><path d="M8 6.5H6.8A1.8 1.8 0 0 0 5 8.3v9.4a1.8 1.8 0 0 0 1.8 1.8h10.4a1.8 1.8 0 0 0 1.8-1.8V8.3a1.8 1.8 0 0 0-1.8-1.8H16" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="M9 4.5h6v3H9v-3Zm-.5 8 2 2 4-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></>;
  } else if (stageKey === "reup_queue") {
    glyph = <><path d="M6 7h12v4H6V7Zm0 6h12v4H6v-4Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="m15 9 2-2-2-2M9 15l-2 2 2 2" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></>;
  } else if (stageKey === "download") {
    glyph = <path d="M12 4.5v10m-4-4 4 4 4-4M5 18.5h14" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />;
  } else if (stageKey === "audio_analysis" || stageKey === "tts") {
    glyph = <path d="M4.5 12h2l1.5-5 2.4 10 2.2-8 1.8 6 1.5-3h3.6" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />;
  } else if (stageKey === "translate") {
    glyph = <><path d="M5 6h7M8.5 4v2m-2 3c1.3 2.2 3 3.8 5.3 5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /><path d="m13 18 3-7 3 7m-5-2h4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></>;
  } else if (stageKey === "ocr") {
    glyph = <><path d="M8 5H5v3m11-3h3v3M8 19H5v-3m11 3h3v-3" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" /><path d="M8 10h8M8 14h6" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" /></>;
  } else if (stageKey === "render" || stageKey === "output_review") {
    glyph = <><rect fill="none" height="12" rx="2" stroke="currentColor" strokeWidth="1.7" width="14" x="5" y="6" /><path d="M8 6v12m8-12v12M5 10h3m8 0h3M5 14h3m8 0h3" fill="none" stroke="currentColor" strokeWidth="1.5" /></>;
  } else if (stageKey === "draft" || stageKey === "export_package" || stageKey === "publish_handoff") {
    glyph = <><path d="m5 8 7-3 7 3-7 3-7-3Zm0 0v8l7 3 7-3V8" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="M12 11v8" fill="none" stroke="currentColor" strokeWidth="1.7" /></>;
  }
  return (
    <span aria-hidden="true" className={`operator-home-v2-priority__icon is-${stageKey.replaceAll("_", "-")}`} data-stage-icon={stageKey}>
      <svg viewBox="0 0 24 24">{glyph}</svg>
    </span>
  );
}

function PriorityHero({ item }: { item: OperatorHomePriorityItem }) {
  return (
    <a className={`operator-home-v2-priority-hero is-${item.severity}`} href={item.href} title={item.detail}>
      <span className="operator-home-v2-priority-hero__eyebrow"><i aria-hidden="true" />Do first</span>
      <span className={`operator-home-v2-severity is-${item.severity}`}>{item.severity}</span>
      <PriorityStageIcon stageKey={item.stage_key} />
      <span className="operator-home-v2-priority-hero__copy">
        <small>{item.stage_key.replaceAll("_", " ")}</small>
        <strong>{item.title}</strong>
      </span>
      <span className="operator-home-v2-priority-hero__count"><b>{item.count.toLocaleString()}</b><small>affected</small></span>
      <span className="operator-home-v2-priority-hero__action">{item.recommended_action}</span>
      <span className="operator-home-v2-priority-hero__cta">Open workspace <WorkItemActionIcon kind="enter" /></span>
    </a>
  );
}

function PriorityImpactCard({ item, maxCount }: { item: OperatorHomePriorityItem; maxCount: number }) {
  return (
    <a className={`operator-home-v2-priority-impact is-${item.severity}`} href={item.href} title={item.detail}>
      <PriorityStageIcon stageKey={item.stage_key} />
      <span className="operator-home-v2-priority-impact__meta"><span>{item.stage_key.replaceAll("_", " ")}</span><span className={`operator-home-v2-severity is-${item.severity}`}>{item.severity}</span></span>
      <strong>{item.title}</strong>
      <span className="operator-home-v2-priority-impact__count"><b>{item.count.toLocaleString()}</b><small>affected</small></span>
      <span className="operator-home-v2-priority-impact__action">{item.recommended_action}</span>
      <span aria-hidden="true" className="operator-home-v2-priority-impact__track"><i style={{ width: `${maxCount > 0 ? percent(item.count, maxCount) : 0}%` }} /></span>
      <WorkItemActionIcon kind="enter" />
    </a>
  );
}

function stageTotal(stage: OperatorHomeStage): number {
  return PIPELINE_SEGMENTS.reduce((total, segment) => total + stage[segment.key], 0);
}

function PipelineWorkloadChart({ stages }: { stages: OperatorHomeStage[] }) {
  const maxTotal = Math.max(0, ...stages.map(stageTotal));

  return (
    <div className="operator-home-v2-pipeline-chart">
      <div aria-label="Pipeline workload legend" className="operator-home-v2-chart-legend">
        {PIPELINE_SEGMENTS.map((segment) => (
          <span className={segment.className} key={segment.key}><i aria-hidden="true" />{segment.label}</span>
        ))}
      </div>
      <nav aria-label="Production pipeline workload by stage" className="operator-home-v2-pipeline-chart__rows">
        {stages.map((stage, index) => {
          const total = stageTotal(stage);
          const detail = PIPELINE_SEGMENTS.map((segment) => `${segment.label} ${stage[segment.key]}`).join(", ");
          const signalClass = stage.failed_count > 0 ? "has-failure" : stage.running_count > 0 ? "has-running" : "";
          return (
            <a
              aria-label={`${stage.label}: ${detail}`}
              className={`operator-home-v2-pipeline-chart__row is-${stage.status} ${signalClass}`}
              href={stage.href}
              key={stage.key}
              title={`Open ${stage.label} · ${detail}`}
            >
              <span className="operator-home-v2-pipeline-chart__label">
                <small>{String(index + 1).padStart(2, "0")}</small>
                <i aria-hidden="true" className="operator-home-v2-pipeline-chart__signal" />
                <strong>{stage.label}</strong>
              </span>
              <span aria-hidden="true" className="operator-home-v2-pipeline-chart__track">
                {PIPELINE_SEGMENTS.map((segment) => (
                  <i
                    className={segment.className}
                    key={segment.key}
                    style={{ width: `${maxTotal > 0 ? percent(stage[segment.key], maxTotal) : 0}%` }}
                  />
                ))}
              </span>
              <b>{total > 0 ? total.toLocaleString() : "Clear"}</b>
            </a>
          );
        })}
      </nav>
    </div>
  );
}

function AttentionDonutChart({ breakdown }: { breakdown: OperatorHomeSummaryResponse["attention_breakdown"] }) {
  const categories = [
    { key: "critical", label: "Critical", value: breakdown.critical, className: "is-critical" },
    { key: "warning", label: "Warning", value: breakdown.warning, className: "is-warning" },
    { key: "manual", label: "Manual review", value: breakdown.manual_review, className: "is-manual" }
  ];
  const criticalEnd = percent(breakdown.critical, breakdown.total) * 3.6;
  const warningEnd = criticalEnd + percent(breakdown.warning, breakdown.total) * 3.6;
  const background = breakdown.total > 0
    ? `conic-gradient(#d45d69 0deg ${criticalEnd}deg, #d99a2b ${criticalEnd}deg ${warningEnd}deg, #4d7faf ${warningEnd}deg 360deg)`
    : "#e7edf3";

  return (
    <div className="operator-home-v2-attention-chart">
      <div
        aria-label={`${breakdown.total} attention items: ${breakdown.critical} critical, ${breakdown.warning} warning, ${breakdown.manual_review} manual review`}
        className="operator-home-v2-attention-chart__donut"
        role="img"
        style={{ background }}
      >
        <span><strong>{breakdown.total.toLocaleString()}</strong><small>items</small></span>
      </div>
      <ul>
        {categories.map((category) => (
          <li className={category.className} key={category.key}>
            <i aria-hidden="true" />
            <span>{category.label}</span>
            <b>{category.value.toLocaleString()}</b>
            <small>{breakdown.total > 0 ? `${Math.round(percent(category.value, breakdown.total))}%` : "0%"}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

function OutputQaHealthChart({ summary }: { summary: OperatorHomeSummaryResponse["output_qa_summary"] }) {
  const categories = [
    { key: "passed", label: "Passed", value: summary.passed, className: "is-passed" },
    { key: "warned", label: "Warning", value: summary.warned, className: "is-warned" },
    { key: "failed", label: "Failed", value: summary.failed, className: "is-failed" },
    { key: "ungraded", label: "Ungraded", value: summary.ungraded, className: "is-ungraded" }
  ];

  return (
    <div className="operator-home-v2-qa-chart">
      <div
        aria-label={`${summary.total} outputs: ${summary.passed} passed, ${summary.warned} warning, ${summary.failed} failed, ${summary.ungraded} ungraded`}
        className="operator-home-v2-qa-chart__track"
        role="img"
      >
        {categories.map((category) => (
          <span className={category.className} key={category.key} style={{ width: `${percent(category.value, summary.total)}%` }} />
        ))}
      </div>
      <ul>
        {categories.map((category) => (
          <li className={category.className} key={category.key}>
            <span><i aria-hidden="true" />{category.label}</span>
            <b>{category.value.toLocaleString()}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

function HomeSurfaceIcon({ kind }: { kind: string }) {
  let glyph = <path d="M5 7h14v10H5V7Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />;
  if (kind === "capture" || kind === "candidate_review") {
    glyph = <><path d="M5 8h14l-1.2 10H6.2L5 8Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="M8 8 9.2 5h5.6L16 8m-4 3v4m-2-2h4" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></>;
  } else if (kind === "review") {
    glyph = <><path d="M8 6.5H6.8A1.8 1.8 0 0 0 5 8.3v9.4a1.8 1.8 0 0 0 1.8 1.8h10.4a1.8 1.8 0 0 0 1.8-1.8V8.3a1.8 1.8 0 0 0-1.8-1.8H16" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="M9 4.5h6v3H9v-3Zm-.5 8 2 2 4-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></>;
  } else if (kind === "queue") {
    glyph = <><path d="M6 7h12v4H6V7Zm0 6h12v4H6v-4Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="m15 9 2-2-2-2m-6 10-2 2 2 2" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></>;
  } else if (kind === "translation_review") {
    glyph = <><path d="M5 6h7M8.5 4v2m-2 3c1.3 2.2 3 3.8 5.3 5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /><path d="m13 18 3-7 3 7m-5-2h4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" /></>;
  } else if (kind === "ocr_review") {
    glyph = <><path d="M8 5H5v3m11-3h3v3M8 19H5v-3m11 3h3v-3" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" /><path d="M8 10h8M8 14h6" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" /></>;
  } else if (kind === "output_review" || kind === "output") {
    glyph = <><rect fill="none" height="12" rx="2" stroke="currentColor" strokeWidth="1.7" width="14" x="5" y="6" /><path d="m9.5 10 5 2.5-5 2.5v-5Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" /></>;
  } else if (kind === "api") {
    glyph = <path d="M7 7.5 3.8 12 7 16.5M17 7.5l3.2 4.5-3.2 4.5M14.2 5l-4.4 14" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />;
  } else if (kind === "worker") {
    glyph = <><circle cx="12" cy="12" fill="none" r="3.2" stroke="currentColor" strokeWidth="1.7" /><path d="M12 4v2m0 12v2M4 12h2m12 0h2M6.4 6.4l1.4 1.4m8.4 8.4 1.4 1.4m0-11.2-1.4 1.4m-8.4 8.4-1.4 1.4" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></>;
  } else if (kind === "ocr") {
    glyph = <><path d="M8 5H5v3m11-3h3v3M8 19H5v-3m11 3h3v-3" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" /><path d="M9 9h6v6H9V9Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" /></>;
  } else if (kind === "tts") {
    glyph = <><path d="M5 14h3l4 3V7l-4 3H5v4Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" /><path d="M15 9.5c1.3 1.2 1.3 3.8 0 5m2.6-7.3c2.5 2.4 2.5 7.2 0 9.6" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" /></>;
  } else if (kind === "extension") {
    glyph = <path d="M8 4.5h4v4h3.5a2 2 0 1 1 0 4H12v3.5a2 2 0 1 1-4 0v-3.5H4.5v-4H8v-4Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />;
  }
  return <span aria-hidden="true" className={`operator-home-v2-surface-icon is-${kind.replaceAll("_", "-")}`} data-surface-icon={kind}><svg viewBox="0 0 24 24">{glyph}</svg></span>;
}

function ActiveWorkLaunchpad() {
  const destinations = [
    { key: "capture", label: "Capture Inbox", hint: "Collect", description: "Import and reconcile fresh Douyin candidates.", signals: ["Profile and post intake", "Metadata readiness"], action: "Start intake", href: "/selection/capture-inbox" },
    { key: "review", label: "Review Board", hint: "Decide", description: "Score shortlisted videos and make keep or reject decisions.", signals: ["Score and shortlist", "Keep or reject"], action: "Review candidates", href: "/selection/review-board" },
    { key: "queue", label: "Reup Queue", hint: "Produce", description: "Continue approved videos through the production pipeline.", signals: ["Localization pipeline", "Render and output QA"], action: "Open production", href: "/selection/reup-queue" }
  ];
  return (
    <div className="operator-home-v2-launchpad">
      <div className="operator-home-v2-launchpad__intro">
        <span aria-hidden="true" className="operator-home-v2-launchpad__pulse" />
        <div><strong>Ready for a new run</strong><span>Choose the entry point that matches the work already completed.</span></div>
        <span className="operator-home-v2-launchpad__status">3 entry points</span>
      </div>
      <nav aria-label="Start production work" className="operator-home-v2-launchpad__routes">
        {destinations.map((item, index) => (
          <a data-step={index + 1} href={item.href} key={item.key}>
            <small>0{index + 1} · {item.hint}</small>
            <span className="operator-home-v2-launchpad__route-main">
              <HomeSurfaceIcon kind={item.key} />
              <span className="operator-home-v2-launchpad__route-copy"><strong>{item.label}</strong><span>{item.description}</span></span>
            </span>
            <span className="operator-home-v2-launchpad__route-signals">{item.signals.map((signal) => <span key={signal}>{signal}</span>)}</span>
            <span className="operator-home-v2-launchpad__route-action"><span>{item.action}</span><WorkItemActionIcon kind="enter" /></span>
          </a>
        ))}
      </nav>
    </div>
  );
}

function ManualCheckpointMatrix({ checkpoints }: { checkpoints: OperatorHomeCheckpoint[] }) {
  const cards = [...checkpoints].sort((left, right) => right.count - left.count);
  const maxCount = Math.max(0, ...cards.map((item) => item.count));
  const totalCount = cards.reduce((total, item) => total + item.count, 0);
  const activeGateCount = cards.filter((item) => item.count > 0).length;
  const oldestAt = cards.reduce<string | null>((oldest, item) => {
    if (!item.oldest_at) return oldest;
    if (!oldest) return item.oldest_at;
    return new Date(item.oldest_at).getTime() < new Date(oldest).getTime() ? item.oldest_at : oldest;
  }, null);
  return (
    <div className="operator-home-v2-checkpoint-matrix">
      <div className="operator-home-v2-checkpoint-summary">
        <span className="operator-home-v2-checkpoint-summary__total"><strong>{totalCount.toLocaleString()}</strong><small>waiting decisions</small></span>
        <span><strong>{activeGateCount}/{cards.length}</strong><small>active gates</small></span>
        <span><strong>{oldestAt ? formatUpdatedAt(oldestAt) : "All clear"}</strong><small>oldest backlog</small></span>
      </div>
      {cards.map((item) => (
        <a aria-label={`Open ${item.label}: ${item.count} waiting`} className={`operator-home-v2-gate tone-${item.tone} ${item.count === 0 ? "is-clear" : "has-work"}`} href={item.href} key={item.key} title={item.detail}>
          <span className="operator-home-v2-gate__top">
            <HomeSurfaceIcon kind={item.key} />
            <span className="operator-home-v2-gate__copy"><strong>{item.label}</strong><small>{item.detail}</small></span>
            <WorkItemActionIcon kind="enter" />
          </span>
          <span className="operator-home-v2-gate__metric">
            <b>{item.count.toLocaleString()}</b>
            <span><em>{item.count === 0 ? "Clear" : "Waiting"}</em><small>{item.count > 0 ? `${Math.round(percent(item.count, totalCount))}% of manual load` : "No backlog"}</small></span>
          </span>
          <span className="operator-home-v2-gate__footer">
            <span>{formatCheckpointAge(item.oldest_at, item.count)}</span>
            <span aria-hidden="true" className="operator-home-v2-gate__track"><i style={{ width: `${maxCount > 0 ? percent(item.count, maxCount) : 0}%` }} /></span>
          </span>
        </a>
      ))}
    </div>
  );
}

function OutputCard({ output, index }: { output: OperatorHomeRecentOutput; index: number }) {
  return (
    <li>
      <a aria-label={`Open ${output.title}`} className={`operator-home-v2-output-card is-art-${(index % 4) + 1}`} href={output.href} title={output.title}>
        <span className="operator-home-v2-output-card__art">
          <span aria-hidden="true" className="operator-home-v2-output-card__frame"><HomeSurfaceIcon kind="output" /><i>0{index + 1}</i></span>
          <span className="operator-home-v2-output-card__duration">{formatDuration(output.duration_seconds)}</span>
        </span>
        <span className="operator-home-v2-output-card__body">
          <span className="operator-home-v2-output-card__head">
            <span>{output.render_status.toLowerCase().replaceAll("_", " ")}</span>
            <span className={`operator-home-v2-qa is-${output.qa_status}`}>{output.qa_status === "ungraded" ? "Not graded" : `QA ${output.qa_status}`}</span>
          </span>
          <strong>{output.title}</strong>
          <span className="operator-home-v2-output-card__meta">{output.finished_at ? `Finished ${formatUpdatedAt(output.finished_at)}` : "Finished time pending"}</span>
          <span className="operator-home-v2-output-card__open"><span>Inspect output</span><WorkItemActionIcon kind="enter" /></span>
        </span>
      </a>
    </li>
  );
}

function SystemReadinessOrbit({ items }: { items: OperatorHomeSummaryResponse["system_readiness"] }) {
  const readyCount = items.filter((item) => item.status === "ready").length;
  const readyDegrees = items.length > 0 ? (readyCount / items.length) * 360 : 0;
  return (
    <div className="operator-home-v2-readiness-orbit">
      <div aria-label={`${readyCount} of ${items.length} services ready`} className="operator-home-v2-readiness-orbit__hub" role="img" style={{ background: `conic-gradient(#3b8b68 0deg ${readyDegrees}deg, #e7edf2 ${readyDegrees}deg 360deg)` }}>
        <span><strong>{readyCount}/{items.length}</strong><small>services ready</small></span>
      </div>
      <ul className="operator-home-v2-readiness-nodes">
        {items.map((item) => {
          const content = <><HomeSurfaceIcon kind={item.key} /><span className="operator-home-v2-readiness-node__copy"><strong>{item.label}</strong><small>{item.status}</small></span><i aria-hidden="true" className={`is-${item.status}`} />{item.href ? <WorkItemActionIcon kind="enter" /> : null}</>;
          return <li className={`is-${item.status}`} key={item.key} title={item.detail}>{item.href ? <a aria-label={`Open ${item.label}: ${item.status}`} href={item.href}>{content}</a> : <div>{content}</div>}</li>;
        })}
      </ul>
    </div>
  );
}

export function OperatorHomeCommandCenter({ summary }: { summary: OperatorHomeSummaryResponse }) {
  const nextPriority = summary.priority_items[0] ?? null;
  const allReady = summary.system_readiness.every((item) => item.status === "ready");
  const criticalPriority = summary.priority_items.find((item) => item.severity === "critical") ?? nextPriority;
  const impactPriorities = summary.priority_items.filter((item) => item.id !== criticalPriority?.id).slice(0, 4);
  const maxImpactCount = Math.max(0, ...impactPriorities.map((item) => item.count));
  const criticalPriorityCount = summary.priority_items.filter((item) => item.severity === "critical").length;
  const warningPriorityCount = summary.priority_items.filter((item) => item.severity === "warning").length;
  const readySystemCount = summary.system_readiness.filter((item) => item.status === "ready").length;

  return (
    <div className="operator-home operator-home-v2">
      <section className={`operator-home-v2-status is-${summary.overall.status}`}>
        <div className="operator-home-v2-status__main">
          <span>{statusLabel(summary.overall.status)}</span>
          <strong>{summary.overall.headline}</strong>
        </div>
        <div className="operator-home-v2-status__meta">
          <span><b>{summary.overall.critical_count}</b> critical</span>
          <span><b>{summary.overall.running_count}</b> running</span>
          <time dateTime={summary.overall.generated_at}>Updated {formatUpdatedAt(summary.overall.generated_at)}</time>
          <a href={nextPriority?.href ?? "/selection/capture-inbox"}>
            {nextPriority ? "Handle next priority" : "Start new work"}
            <WorkItemActionIcon kind="enter" />
          </a>
        </div>
      </section>

      <section aria-label="Decision metrics" className="operator-home-v2-metrics">
        {summary.decision_metrics.map((metric) => <MetricCard key={metric.key} metric={metric} />)}
      </section>

      <section aria-label="Operational charts" className="operator-home-v2-chart-grid">
        <article className="operator-home-v2-panel operator-home-v2-pipeline">
          <header className="operator-home-v2-panel__head">
            <div>
              <span className="operator-home-v2-eyebrow">Workload map</span>
              <h2>Production pipeline</h2>
              <p>One shared scale across every stage, grouped by operational state.</p>
            </div>
            <a href="/ops/pipeline">Open pipeline</a>
          </header>
          <PipelineWorkloadChart stages={summary.stages} />
        </article>

        <div className="operator-home-v2-chart-stack operator-home-v2-health-rail">
          <article className="operator-home-v2-panel operator-home-v2-health-card is-attention">
            <header className="operator-home-v2-panel__head">
              <div><span className="operator-home-v2-eyebrow">Decision load</span><h2>Attention breakdown</h2></div>
              <span>{summary.attention_breakdown.total.toLocaleString()} items</span>
            </header>
            <AttentionDonutChart breakdown={summary.attention_breakdown} />
          </article>

          <article className="operator-home-v2-panel operator-home-v2-health-card is-qa">
            <header className="operator-home-v2-panel__head">
              <div><span className="operator-home-v2-eyebrow">Final quality</span><h2>Output QA health</h2></div>
              <a href="/production/output-review">Review outputs</a>
            </header>
            <OutputQaHealthChart summary={summary.output_qa_summary} />
          </article>
        </div>
      </section>

      <section className="operator-home-v2-panel operator-home-v2-priority">
        <header className="operator-home-v2-panel__head">
          <div>
            <span className="operator-home-v2-eyebrow">Decision queue</span>
            <h2>Priority command deck</h2>
            <p>One critical action, then the checkpoints with the largest impact.</p>
          </div>
          <div className="operator-home-v2-priority__summary">
            <span className="is-critical"><b>{criticalPriorityCount}</b> critical</span>
            <span className="is-warning"><b>{warningPriorityCount}</b> warnings</span>
            <span><b>{summary.priority_items.length}</b> priorities</span>
          </div>
        </header>
        {criticalPriority ? (
          <div aria-label="Priority command deck" className="operator-home-v2-priority__deck">
            <PriorityHero item={criticalPriority} />
            <div className="operator-home-v2-priority__impact-grid">
              {impactPriorities.map((item) => <PriorityImpactCard item={item} key={item.id} maxCount={maxImpactCount} />)}
            </div>
          </div>
        ) : (
          <div className="operator-home-v2-empty"><strong>No urgent work</strong><span>The workspace has no critical or warning priority.</span></div>
        )}
      </section>

      <section className="operator-home-v2-grid is-focus">
        <article className="operator-home-v2-panel operator-home-v2-active">
          <header className="operator-home-v2-panel__head">
            <div><span className="operator-home-v2-eyebrow">Current context</span><h2>Active work</h2></div>
          </header>
          {summary.active_work ? (
            <div className="operator-home-v2-active__body">
              <div className="operator-home-v2-active__title">
                <span>{summary.active_work.stage_key.replaceAll("_", " ")}</span>
                <strong>{summary.active_work.title}</strong>
                <p>{summary.active_work.current_step ?? summary.active_work.status.toLowerCase().replaceAll("_", " ")}</p>
              </div>
              <div className="operator-home-v2-progress__meta">
                <span>{summary.active_work.started_at ? `Started ${formatUpdatedAt(summary.active_work.started_at)}` : "Start time pending"}</span>
                <strong>{summary.active_work.progress_percent}% complete</strong>
                <span>Updated {formatUpdatedAt(summary.active_work.updated_at)}</span>
              </div>
              <div className="operator-home-v2-progress" aria-label={`${summary.active_work.progress_percent}% complete`}>
                <span style={{ width: `${Math.max(0, Math.min(100, summary.active_work.progress_percent))}%` }} />
              </div>
              <div className="operator-home-v2-active__footer">
                <span>{summary.active_work.next_action}</span>
                <a href={summary.active_work.href}>Resume work <WorkItemActionIcon kind="enter" /></a>
              </div>
            </div>
          ) : (
            <ActiveWorkLaunchpad />
          )}
        </article>

        <article className="operator-home-v2-panel operator-home-v2-checkpoints">
          <header className="operator-home-v2-panel__head">
            <div><span className="operator-home-v2-eyebrow">Human gates</span><h2>Manual checkpoints</h2></div>
          </header>
          <ManualCheckpointMatrix checkpoints={summary.manual_checkpoints} />
        </article>
      </section>

      <section className="operator-home-v2-grid is-secondary">
        <article className="operator-home-v2-panel operator-home-v2-outputs">
          <header className="operator-home-v2-panel__head">
            <div><span className="operator-home-v2-eyebrow">Finished media</span><h2>Recent outputs</h2></div>
            <a href="/production/output-review">Open Output Review</a>
          </header>
          {summary.recent_outputs.length > 0 ? (
            <ul className="operator-home-v2-output-grid">{summary.recent_outputs.map((output, index) => <OutputCard index={index} key={output.render_output_id} output={output} />)}</ul>
          ) : (
            <div className="operator-home-v2-empty"><strong>No rendered output yet</strong><span>Completed renders will appear here with their QA status.</span></div>
          )}
        </article>

        <aside className="operator-home-v2-panel operator-home-v2-readiness">
          <header className="operator-home-v2-panel__head">
            <div><span className="operator-home-v2-eyebrow">Local runtime</span><h2>System readiness</h2></div>
            <span className={`operator-home-v2-readiness__score ${allReady ? "is-ready" : "is-attention"}`}>{allReady ? "All nominal" : `${summary.system_readiness.length - readySystemCount} attention`}</span>
          </header>
          <SystemReadinessOrbit items={summary.system_readiness} />
        </aside>
      </section>
    </div>
  );
}
