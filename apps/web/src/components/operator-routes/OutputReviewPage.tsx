"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import {
  fetchMediaAssetObjectUrl,
  fetchRender,
  fetchReupQueueItems,
  runReupQueueAction
} from "../../lib/api";
import {
  outputReviewCounts,
  outputReviewFixTarget,
  outputReviewQueue,
  parseRenderQaVerdict,
  renderQaBadgeLabel,
  renderQaBadgeTone,
  type RenderQaVerdict
} from "../../lib/outputReview";
import {
  formatBytes,
  formatFps,
  formatRenderDuration,
  formatResolution,
  resolveRenderTechSpecs
} from "../../lib/finalReviewState";
import { groupInspectorLifecycleActions, itemTitle } from "../../lib/reupQueueStudioState";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { RenderOutput } from "../../types/final-review";
import type { ReupQueueAction, ReupQueueItem } from "../../types/reup-queue";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { OpsState, formatDateTime } from "../ops-console/OpsShared";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { WorkItemActionIcon, type WorkItemActionIconKind } from "../shared/WorkItemActionIcon";

const PAGE_TITLE = "Output Review";
const PAGE_DESCRIPTION =
  "Watch finished localized videos back to back. Automated QA already graded each render — start with the flagged ones.";
// SET_AUTOMATION needs a mode picker, which belongs in the queue inspector, not here.
const HIDDEN_ACTIONS = new Set<ReupQueueAction>(["SET_AUTOMATION"]);

function outputReviewActionIconKind(action: ReupQueueAction): WorkItemActionIconKind {
  if (action === "START_AUTO_PIPELINE") return "auto-run";
  if (action === "START_PROCESSING" || action === "RESUME") return "process";
  if (action === "HOLD") return "pause";
  if (action === "RETRY") return "retry";
  if (action === "MARK_MEDIA_READY" || action === "MARK_COMPLETED") return "approve";
  if (action === "DISMISS") return "dismiss";
  return "reject";
}

function outputReviewFixIconKind(href: string, label: string): WorkItemActionIconKind {
  if (href.includes("/transcript-editor/")) return "transcript";
  if (label.startsWith("Fix")) return "auto-render";
  return "open";
}

function ReviewPagerIcon({ direction }: { direction: "previous" | "next" }) {
  return (
    <svg aria-hidden="true" className="ops-output-review-pager__icon" viewBox="0 0 16 16">
      <path
        d={direction === "previous" ? "m9.75 3.5-4.5 4.5 4.5 4.5" : "m6.25 3.5 4.5 4.5-4.5 4.5"}
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

function formatReviewMoment(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    month: "short"
  }).format(date);
}

type OutputReviewRenderFact = {
  label: string;
  value: string;
};

function outputReviewRenderFacts(render: RenderOutput | null): OutputReviewRenderFact[] {
  if (!render) return [];
  const specs = resolveRenderTechSpecs(render);
  const geometry = formatResolution(specs.width, specs.height);
  const fps = formatFps(specs.fps);
  const size = formatBytes(specs.size_bytes);
  const finished = formatReviewMoment(specs.finished_at);
  const facts: Array<OutputReviewRenderFact | null> = [
    specs.render_version ? { label: "Render", value: specs.render_version } : null,
    geometry ? { label: "Frame", value: `${geometry}${fps ? ` · ${fps} fps` : ""}` } : null,
    specs.duration_seconds != null
      ? { label: "Duration", value: formatRenderDuration(specs.duration_seconds) }
      : null,
    size ? { label: "Size", value: size } : null,
    finished ? { label: "Finished", value: finished } : null
  ];
  return facts.filter((fact): fact is OutputReviewRenderFact => fact !== null);
}

type SummaryMetricKind = "failed" | "warnings" | "passed" | "ungraded";

function SummaryMetricIcon({ kind }: { kind: SummaryMetricKind }) {
  if (kind === "failed") {
    return (
      <svg aria-hidden="true" className="ops-output-review-pulse__metric-icon" viewBox="0 0 16 16">
        <path d="M8 2.1 14 13H2L8 2.1Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.35" />
        <path d="M8 5.6v3.6M8 11.4h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.45" />
      </svg>
    );
  }
  if (kind === "warnings") {
    return (
      <svg aria-hidden="true" className="ops-output-review-pulse__metric-icon" viewBox="0 0 16 16">
        <path d="M3.25 13.5V2.5m.4 1.1h7.7l-1.6 2.3 1.6 2.3h-7.7" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.35" />
      </svg>
    );
  }
  if (kind === "ungraded") {
    return (
      <svg aria-hidden="true" className="ops-output-review-pulse__metric-icon" viewBox="0 0 16 16">
        <circle cx="8" cy="8" fill="none" r="5.5" stroke="currentColor" strokeWidth="1.35" />
        <path d="M5.4 8h5.2" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.45" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="ops-output-review-pulse__metric-icon" viewBox="0 0 16 16">
      <circle cx="8" cy="8" fill="none" r="5.5" stroke="currentColor" strokeWidth="1.35" />
      <path d="m5.25 8 1.8 1.8 3.8-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.45" />
    </svg>
  );
}

function summaryPercentage(value: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round(Math.min(1, Math.max(0, value / total)) * 100);
}

function normalizedOutcomePercentages(values: number[], total: number): number[] {
  if (total <= 0) return values.map(() => 0);
  const percentages = values.map((value) => Math.round((Math.max(0, value) / total) * 1000) / 10);
  const correction = Math.round((100 - percentages.reduce((sum, value) => sum + value, 0)) * 10) / 10;
  const largestIndex = values.indexOf(Math.max(...values));
  percentages[largestIndex] = Math.round((percentages[largestIndex] + correction) * 10) / 10;
  return percentages;
}

function QaBadge({ quiet = false, verdict }: { quiet?: boolean; verdict: RenderQaVerdict | null }) {
  const status = verdict?.status ?? null;
  return (
    <span
      className={`ops-output-review-badge tone-${renderQaBadgeTone(status)}${quiet ? " is-quiet" : ""}`}
      title={verdict?.summary ?? undefined}
    >
      {renderQaBadgeLabel(status)}
    </span>
  );
}

function PlaybackEmptyIcon() {
  return (
    <svg aria-hidden="true" className="ops-output-review-player-empty__icon" viewBox="0 0 24 24">
      <rect fill="none" height="14" rx="3" stroke="currentColor" strokeWidth="1.5" width="18" x="3" y="5" />
      <path d="m10 9 5 3-5 3V9Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.5" />
      <path d="m5 3 14 18" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
    </svg>
  );
}

function QaChecklist({ verdict }: { verdict: RenderQaVerdict | null }) {
  if (!verdict) {
    return (
      <aside className="ops-output-review-inspection">
        <div className="ops-output-review-inspection__head">
          <div>
            <span className="ops-output-review-eyebrow">Inspection</span>
            <h3>Manual review needed</h3>
          </div>
          <span className="ops-output-review-inspection__count has-skipped">Not graded</span>
        </div>
        <p className="ops-output-review-empty">
          This render was produced before automated QA existed, or the gate could not run. Review it manually.
        </p>
      </aside>
    );
  }

  const attentionChecks = verdict.checks.filter((check) => check.status === "fail" || check.status === "warn");
  const verifiedChecks = verdict.checks.filter((check) => check.status === "pass");
  const skippedChecks = verdict.checks.filter((check) => check.status === "skipped");
  const inspectionLabel = attentionChecks.length > 0
    ? `${attentionChecks.length} need attention`
    : verdict.checks.length === 0
      ? "No check details"
      : skippedChecks.length > 0
        ? `${skippedChecks.length} not measured`
        : "All measured checks clear";

  function checkRows(checks: RenderQaVerdict["checks"]) {
    return checks.map((check) => (
      <li className={`is-${check.status}`} key={check.key}>
        <span aria-hidden="true" className="ops-output-review-check__indicator" />
        <span className="ops-output-review-check__copy">
          <strong>{check.key.replace(/_/g, " ")}</strong>
          <span>{check.detail}</span>
        </span>
      </li>
    ));
  }

  return (
    <aside className="ops-output-review-inspection">
      <div className="ops-output-review-inspection__head">
        <div>
          <span className="ops-output-review-eyebrow">Inspection</span>
          <h3>Automated checks</h3>
        </div>
        <span
          className={`ops-output-review-inspection__count${attentionChecks.length > 0 ? " has-attention" : skippedChecks.length > 0 || verdict.checks.length === 0 ? " has-skipped" : ""}`}
        >
          {inspectionLabel}
        </span>
      </div>

      {attentionChecks.length > 0 ? (
        <section aria-labelledby="output-review-attention" className="ops-output-review-check-group is-attention">
          <div className="ops-output-review-check-group__head">
            <h4 id="output-review-attention">Attention</h4>
            <span>Resolve before handoff</span>
          </div>
          <ul className="ops-output-review-checks">{checkRows(attentionChecks)}</ul>
        </section>
      ) : null}

      {verifiedChecks.length > 0 ? (
        <details className="ops-output-review-check-group is-verified" open>
          <summary>
            <span>Verified checks</span>
            <span>{verifiedChecks.length}</span>
          </summary>
          <ul className="ops-output-review-checks">{checkRows(verifiedChecks)}</ul>
        </details>
      ) : null}

      {skippedChecks.length > 0 ? (
        <details className="ops-output-review-check-group is-verified is-skipped">
          <summary>
            <span>Not measured</span>
            <span>{skippedChecks.length}</span>
          </summary>
          <ul className="ops-output-review-checks">{checkRows(skippedChecks)}</ul>
        </details>
      ) : null}

      {verdict.checks.length === 0 ? (
        <p className="ops-output-review-empty">The QA gate recorded a verdict without individual check details.</p>
      ) : null}
    </aside>
  );
}

function useRenderPlayback(item: ReupQueueItem | null) {
  const [url, setUrl] = useState<string | null>(null);
  const [render, setRender] = useState<RenderOutput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const activeUrl = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    function release() {
      if (activeUrl.current) {
        URL.revokeObjectURL(activeUrl.current);
        activeUrl.current = null;
      }
    }

    async function load() {
      release();
      setUrl(null);
      setRender(null);
      setError(null);
      setLoading(false);
      if (!item) return;
      if (!item.render_output_id) {
        setError("No playable render is linked to this queue item.");
        return;
      }
      setLoading(true);
      try {
        const renderOutput = await fetchRender(item.render_output_id);
        if (cancelled) return;
        setRender(renderOutput);
        if (!renderOutput.media_asset_id) throw new Error("Render has no playable asset yet.");
        const objectUrl = await fetchMediaAssetObjectUrl(renderOutput.media_asset_id);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        activeUrl.current = objectUrl;
        setUrl(objectUrl);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the rendered video.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
      release();
    };
  }, [item?.id, item?.render_output_id]);

  return { url, render, error, loading };
}

export function OutputReviewPage() {
  const [items, setItems] = useState<ReupQueueItem[]>([]);
  const [sourceTotalCount, setSourceTotalCount] = useState(0);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      try {
        await request.run(
          () => fetchReupQueueItems({ limit: 200, sort: "recent" }),
          (payload) => {
            setItems(payload.items);
            setSourceTotalCount(payload.total_count);
            setLoadedAt(new Date().toISOString());
          },
          mode
        );
      } catch (err) {
        if (mode === "refresh") {
          notify({
            id: "output-review-refresh",
            message: err instanceof Error ? err.message : "Could not refresh finished videos.",
            tone: "error"
          });
        }
      }
    },
    [notify, request]
  );

  useEffect(() => {
    void load("initial");
    // Load once on mount; refreshes are explicit so playback is never interrupted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const queue = useMemo(() => outputReviewQueue(items), [items]);
  const counts = useMemo(() => outputReviewCounts(items), [items]);
  const selected = useMemo(
    () => queue.find((entry) => entry.id === selectedId) ?? queue[0] ?? null,
    [queue, selectedId]
  );
  const selectedVerdict = selected ? parseRenderQaVerdict(selected) : null;
  const playback = useRenderPlayback(selected);
  const renderFacts = useMemo(() => outputReviewRenderFacts(playback.render), [playback.render]);

  const selectedIndex = selected ? queue.findIndex((entry) => entry.id === selected.id) : -1;
  const nextItem = selectedIndex >= 0 ? queue[selectedIndex + 1] ?? null : null;
  const previousItem = selectedIndex > 0 ? queue[selectedIndex - 1] ?? null : null;
  const fixTarget = selected ? outputReviewFixTarget(selected) : null;
  const actionGroups = groupInspectorLifecycleActions(
    selected?.available_actions.filter((entry) => !HIDDEN_ACTIONS.has(entry.action)) ?? []
  );
  const attentionCount = counts.failed + counts.warned;
  const gradedCount = counts.total - counts.ungraded;
  const gradedPercentage = summaryPercentage(gradedCount, counts.total);
  const [failedPercentage, warnedPercentage, passRatePercentage] = normalizedOutcomePercentages(
    [counts.failed, counts.warned, counts.passed],
    gradedCount
  );
  const summaryStatus = counts.total === 0
    ? "Waiting for renders"
    : attentionCount > 0
      ? "Attention first"
      : counts.ungraded > 0
        ? "Manual review pending"
        : "Queue is clear";
  const summaryTone = counts.failed > 0
    ? "danger"
    : counts.warned > 0
      ? "warning"
      : counts.ungraded > 0
        ? "pending"
        : counts.total > 0
          ? "clear"
          : "idle";
  const summaryIconKind: SummaryMetricKind = counts.failed > 0
    ? "failed"
    : counts.warned > 0
      ? "warnings"
      : counts.ungraded > 0
        ? "ungraded"
        : "passed";
  const signalCount = attentionCount > 0
    ? attentionCount
    : counts.ungraded > 0
      ? counts.ungraded
      : counts.total;
  const signalLabel = attentionCount > 0
    ? `${attentionCount === 1 ? "clip needs" : "clips need"} attention`
    : counts.ungraded > 0
      ? `${counts.ungraded === 1 ? "render is" : "renders are"} awaiting QA`
      : counts.total > 0
        ? `${counts.total === 1 ? "render is" : "renders are"} QA-cleared`
        : "finished renders";
  const summaryCue = counts.failed > 0
    ? "Resolve blocking defects before release."
    : counts.warned > 0
      ? "Review quality warnings before proceeding."
      : counts.ungraded > 0
        ? "Complete the remaining manual verdicts."
        : counts.total > 0
          ? "No blocking QA issue is currently detected."
          : "The deck will populate after the first render finishes.";
  const sourceQueueIsTruncated = sourceTotalCount > items.length;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      // Never steal keys from a field or from a focused video's own controls.
      if (target?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT", "VIDEO"].includes(target?.tagName ?? "")) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "j" || event.key === "ArrowDown") {
        if (nextItem) {
          setSelectedId(nextItem.id);
          event.preventDefault();
        }
      } else if (key === "k" || event.key === "ArrowUp") {
        if (previousItem) {
          setSelectedId(previousItem.id);
          event.preventDefault();
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [nextItem, previousItem]);

  async function applyAction(item: ReupQueueItem, action: ReupQueueAction) {
    const key = `${item.id}:${action}`;
    setPendingAction(key);
    try {
      await runReupQueueAction(item.id, { action });
      notify({ id: "output-review-action", message: `${action} applied.`, tone: "success" });
      if (nextItem) setSelectedId(nextItem.id);
      await load("refresh");
    } catch (err) {
      notify({
        id: "output-review-action",
        message: err instanceof Error ? err.message : "Action failed.",
        tone: "error"
      });
    } finally {
      setPendingAction(null);
    }
  }

  const refreshAction = (
    <TopbarRefreshButton
      busy={request.refreshing}
      disabled={request.initialLoading}
      onClick={() => void load("refresh")}
    />
  );

  if (!loadedAt && !request.error) {
    return (
      <OperatorStudioShell actions={refreshAction} description={PAGE_DESCRIPTION} title={PAGE_TITLE}>
        <AsyncContentBoundary loadingLabel="Loading finished videos…" skeletonVariant="gallery" status="loading">
          <span />
        </AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  if (request.error && !loadedAt) {
    return (
      <OperatorStudioShell actions={refreshAction} description={PAGE_DESCRIPTION} title={PAGE_TITLE}>
        <AsyncContentBoundary
          errorState={
            <OpsState
              detail={request.error.message}
              retry={() => void load("initial")}
              title="Finished videos unavailable"
            />
          }
          skeletonVariant="gallery"
          status="error"
        >
          <span />
        </AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  return (
    <OperatorStudioShell actions={refreshAction} description={PAGE_DESCRIPTION} title={PAGE_TITLE}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="gallery" status="success">
        <main className="ops-page ops-output-review-page">
          <section aria-label="QA summary" className="ops-output-review-summary">
            <header className="ops-output-review-summary__head">
              <div className="ops-output-review-summary__intro">
                <span className="ops-output-review-eyebrow">Output QA</span>
                <strong>Release readiness</strong>
              </div>
              <p className="ops-output-review-summary__freshness">
                {sourceQueueIsTruncated ? (
                  <strong title="Output Review currently scans the newest queue page">
                    Newest {items.length} of {sourceTotalCount}
                  </strong>
                ) : null}
                <span aria-hidden="true">↻</span>
                Updated {loadedAt ? <time dateTime={loadedAt}>{formatDateTime(loadedAt)}</time> : "—"}
              </p>
            </header>
            <div className="ops-output-review-pulse__body">
              <section
                aria-labelledby="output-review-deck"
                className={`ops-output-review-pulse__deck tone-${summaryTone}`}
              >
                <div className="ops-output-review-pulse__deck-signal">
                  <header>
                    <span className="ops-output-review-pulse__deck-mark">
                      <SummaryMetricIcon kind={summaryIconKind} />
                    </span>
                    <span>QA signal</span>
                  </header>
                  <strong id="output-review-deck">{summaryStatus}</strong>
                  <div className="ops-output-review-pulse__deck-count">
                    <b>{signalCount}</b>
                    <span>{signalLabel}</span>
                  </div>
                  <p>{summaryCue}</p>
                </div>

                <div className="ops-output-review-pulse__deck-analysis">
                  <header className="ops-output-review-pulse__deck-head">
                    <div>
                      <span className="ops-output-review-eyebrow">QA outcome</span>
                      <h2>Release confidence</h2>
                    </div>
                    <dl className="ops-output-review-pulse__deck-metrics is-compact">
                      <div>
                        <dt>Coverage</dt>
                        <dd>
                          <strong>{gradedPercentage}%</strong>
                          <small>{counts.ungraded > 0 ? `${counts.ungraded} awaiting` : "All graded"}</small>
                        </dd>
                      </div>
                      <div>
                        <dt>Finished</dt>
                        <dd><strong>{counts.total}</strong><small>render outputs</small></dd>
                      </div>
                    </dl>
                  </header>

                  <div className="ops-output-review-pulse__deck-chart">
                    <figure className="ops-output-review-pulse__deck-ring-figure">
                      <div
                        aria-label={`${passRatePercentage}% pass rate`}
                        className="ops-output-review-pulse__deck-ring"
                        role="img"
                        style={{ "--pass-rate": `${passRatePercentage}%` } as CSSProperties}
                      >
                        <span>
                          <strong>{passRatePercentage}<small>%</small></strong>
                          <em>Pass rate</em>
                        </span>
                      </div>
                      <figcaption><strong>{counts.passed}</strong> of {gradedCount} passed</figcaption>
                    </figure>

                    <div className="ops-output-review-pulse__deck-issues">
                      <header>
                        <span>Attention breakdown</span>
                        <strong>{attentionCount} total</strong>
                      </header>
                      <div aria-label="QA attention distribution" className="ops-output-review-pulse__deck-bars">
                        <div className="ops-output-review-pulse__deck-bar tone-danger">
                          <span><SummaryMetricIcon kind="failed" /><b>Failed</b></span>
                          <div aria-label={`${failedPercentage}% failed`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={failedPercentage} role="progressbar">
                            <i style={{ width: `${failedPercentage}%` }} />
                          </div>
                          <strong>{counts.failed}<small>{failedPercentage}%</small></strong>
                        </div>
                        <div className="ops-output-review-pulse__deck-bar tone-warning">
                          <span><SummaryMetricIcon kind="warnings" /><b>Warnings</b></span>
                          <div aria-label={`${warnedPercentage}% warnings`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={warnedPercentage} role="progressbar">
                            <i style={{ width: `${warnedPercentage}%` }} />
                          </div>
                          <strong>{counts.warned}<small>{warnedPercentage}%</small></strong>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </section>

          {queue.length === 0 ? (
            <p className="ops-output-review-empty">
              No finished renders yet. Items appear here as soon as the auto pipeline produces a final video.
            </p>
          ) : (
            <div className="ops-output-review-layout">
              <aside aria-label="Review queue" className="ops-output-review-queue-panel">
                <header className="ops-output-review-queue-panel__head">
                  <div>
                    <span className="ops-output-review-eyebrow">Worklist</span>
                    <h2>Review queue</h2>
                  </div>
                  <span>{queue.length} clips</span>
                </header>
                <ol className="ops-output-review-list">
                  {queue.map((item, index) => {
                    const verdict = parseRenderQaVerdict(item);
                    const duration = item.source_video?.duration_seconds;
                    const moment = formatReviewMoment(item.completed_at ?? item.updated_at);
                    const sourceExternalId = item.source_video?.source_video_external_id;
                    const sourceReference = sourceExternalId
                      ? `ID ${sourceExternalId.slice(0, 10)}${sourceExternalId.length > 10 ? "…" : ""}`
                      : null;
                    const meta = [
                      sourceReference,
                      duration != null ? formatRenderDuration(duration) : null,
                      moment
                    ].filter((entry): entry is string => Boolean(entry));
                    const rowMeta = index === selectedIndex
                      ? ["Now reviewing", ...meta].join(" · ")
                      : meta.join(" · ") || `Queue position ${index + 1}`;
                    return (
                      <li key={item.id}>
                        <button
                          aria-current={selected?.id === item.id ? "true" : undefined}
                          className={`ops-output-review-row${selected?.id === item.id ? " is-active" : ""}`}
                          onClick={() => setSelectedId(item.id)}
                          type="button"
                        >
                          <span aria-hidden="true" className="ops-output-review-row__index">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <span className="ops-output-review-row__copy">
                            <span className="ops-output-review-row__title" title={itemTitle(item)}>{itemTitle(item)}</span>
                            <span className="ops-output-review-row__meta" title={rowMeta}>{rowMeta}</span>
                          </span>
                          <QaBadge verdict={verdict} />
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </aside>

              {selected ? (
                <section aria-label="Selected output" className="ops-output-review-stage">
                  <header className="ops-output-review-stage__head">
                    <div>
                      <span className="ops-output-review-eyebrow">
                        Clip {selectedIndex + 1} of {queue.length}
                      </span>
                      <h2>{itemTitle(selected)}</h2>
                      <p>{selectedVerdict?.summary ?? "No automated verdict recorded for this render."}</p>
                      {renderFacts.length > 0 ? (
                        <dl className="ops-output-review-stage__facts">
                          {renderFacts.map((fact) => (
                            <div className="ops-output-review-stage__fact" key={fact.label}>
                              <dt>{fact.label}</dt>
                              <dd>{fact.value}</dd>
                            </div>
                          ))}
                        </dl>
                      ) : null}
                    </div>
                    <QaBadge quiet verdict={selectedVerdict} />
                  </header>

                  <div className={`ops-output-review-stage__body${!playback.loading && !playback.url ? " has-no-playback" : ""}`}>
                    <div className={`ops-output-review-player${!playback.loading && !playback.url ? " is-empty" : ""}`}>
                      {playback.loading ? <p className="ops-output-review-empty">Loading video…</p> : null}
                      {!playback.loading && playback.error ? (
                        <div className="ops-output-review-player-empty">
                          <span className="ops-output-review-player-empty__glyph"><PlaybackEmptyIcon /></span>
                          <span className="ops-output-review-eyebrow">Playback unavailable</span>
                          <strong>Preview cannot be loaded</strong>
                          <p>{playback.error}</p>
                          <small>
                            {selected.render_output_id
                              ? `Render ${selected.render_output_id.slice(0, 12)}${selected.render_output_id.length > 12 ? "…" : ""}`
                              : "No render output ID"}
                          </small>
                        </div>
                      ) : null}
                      {playback.url ? (
                        <video aria-label={`Rendered output for ${itemTitle(selected)}`} controls key={selected.id} preload="metadata" src={playback.url} />
                      ) : null}
                    </div>
                    <QaChecklist verdict={selectedVerdict} />
                  </div>

                  <footer className="ops-output-review-command-bar">
                    <div className="ops-output-review-command-bar__actions">
                      {fixTarget ? (
                        <Link
                          className={`ops-output-review-link ${selectedVerdict?.status === "pass" ? "is-secondary" : "is-primary"}`}
                          href={fixTarget.href}
                          title={fixTarget.reason}
                        >
                          <WorkItemActionIcon
                            className="ops-output-review-action__icon"
                            kind={outputReviewFixIconKind(fixTarget.href, fixTarget.label)}
                          />
                          {fixTarget.label}
                        </Link>
                      ) : null}
                      {actionGroups.primary.map((entry) => (
                        <AsyncButton
                          className="ops-output-review-action is-secondary"
                          disabled={pendingAction !== null}
                          key={entry.action}
                          leadingIcon={
                            <WorkItemActionIcon
                              className="ops-output-review-action__icon"
                              kind={outputReviewActionIconKind(entry.action)}
                            />
                          }
                          onClick={() => void applyAction(selected, entry.action)}
                          pending={pendingAction === `${selected.id}:${entry.action}`}
                          title={entry.description}
                        >
                          {entry.label}
                        </AsyncButton>
                      ))}
                      {actionGroups.neutral.map((entry) => (
                        <AsyncButton
                          className="ops-output-review-action is-muted"
                          disabled={pendingAction !== null}
                          key={entry.action}
                          leadingIcon={
                            <WorkItemActionIcon
                              className="ops-output-review-action__icon"
                              kind={outputReviewActionIconKind(entry.action)}
                            />
                          }
                          onClick={() => void applyAction(selected, entry.action)}
                          pending={pendingAction === `${selected.id}:${entry.action}`}
                          title={entry.description}
                        >
                          {entry.label}
                        </AsyncButton>
                      ))}
                      {actionGroups.danger.map((entry) => (
                        <AsyncButton
                          className="ops-output-review-action is-danger"
                          disabled={pendingAction !== null}
                          key={entry.action}
                          leadingIcon={
                            <WorkItemActionIcon
                              className="ops-output-review-action__icon"
                              kind={outputReviewActionIconKind(entry.action)}
                            />
                          }
                          onClick={() => void applyAction(selected, entry.action)}
                          pending={pendingAction === `${selected.id}:${entry.action}`}
                          title={entry.description}
                        >
                          {entry.label}
                        </AsyncButton>
                      ))}
                      {actionGroups.quiet.map((entry) => (
                        <AsyncButton
                          className="ops-output-review-action is-quiet"
                          disabled={pendingAction !== null}
                          key={entry.action}
                          leadingIcon={
                            <WorkItemActionIcon
                              className="ops-output-review-action__icon"
                              kind={outputReviewActionIconKind(entry.action)}
                            />
                          }
                          onClick={() => void applyAction(selected, entry.action)}
                          pending={pendingAction === `${selected.id}:${entry.action}`}
                          title={entry.description}
                        >
                          {entry.label}
                        </AsyncButton>
                      ))}
                    </div>

                    <div className="ops-output-review-command-bar__navigation">
                      <span className="ops-output-review-hint">
                        <kbd>K</kbd>/<kbd>↑</kbd> previous · <kbd>J</kbd>/<kbd>↓</kbd> next
                      </span>
                      <div className="ops-output-review-pager">
                        <button
                          aria-label="Previous clip"
                          disabled={!previousItem}
                          onClick={() => previousItem && setSelectedId(previousItem.id)}
                          title="Previous clip (K or ↑)"
                          type="button"
                        >
                          <ReviewPagerIcon direction="previous" />
                          Previous
                        </button>
                        <span aria-label={`Clip ${selectedIndex + 1} of ${queue.length}`}>
                          {selectedIndex + 1} / {queue.length}
                        </span>
                        <button
                          aria-label="Next clip"
                          disabled={!nextItem}
                          onClick={() => nextItem && setSelectedId(nextItem.id)}
                          title="Next clip (J or ↓)"
                          type="button"
                        >
                          Next
                          <ReviewPagerIcon direction="next" />
                        </button>
                      </div>
                    </div>
                  </footer>
                </section>
              ) : null}
            </div>
          )}

        </main>
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}
