"use client";

import { useEffect, useMemo, useState } from "react";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import {
  fetchCandidates,
  fetchDouyinExtensionStatus,
  fetchJobs,
  fetchOptimizationDashboard,
  fetchPipelineDashboard,
  fetchPublishControlQueue,
  fetchPublishHealthDashboard
} from "../../lib/api";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import {
  buildActionQueue,
  buildContinueItems,
  buildExtensionSignal,
  buildFreshness,
  buildNextWork,
  buildOperatorMetrics,
  buildPublishSuccessMetric,
  buildQuickLaunchItems,
  buildRecentActivity,
  firstReadyDraftId,
  firstReadyDraftSourceVideoId,
  firstReconciliationDraftId,
  pickRecentSourceVideoId
} from "../../lib/operatorHomeState";
import { DEFAULT_FILTERS } from "../../lib/reviewBoardState";
import type { PublishHealthDashboard } from "../../types/analytics";
import type { DouyinExtensionStatusResponse } from "../../types/douyin-extension-setup";
import type { Job } from "../../types/jobs";
import type { OptimizationDashboard } from "../../types/optimization";
import type { PipelineDashboardResponse } from "../../types/operations";
import type { PublishControlQueue } from "../../types/publish-control";
import type { Candidate } from "../../types/review-board";
import { ActionQueuePanel } from "./ActionQueuePanel";
import { OverviewCards } from "./OverviewCards";
import { QuickLaunchGrid } from "./QuickLaunchGrid";
import { RecentActivityPanel } from "./RecentActivityPanel";
import { ContinuePanel } from "./ContinuePanel";
import { FreshnessStrip } from "./FreshnessStrip";
import { NextWorkPanel } from "./NextWorkPanel";

type OperatorHomeSnapshot = {
  candidates: Candidate[];
  jobs: Job[];
  health: PublishHealthDashboard | null;
  queue: PublishControlQueue | null;
  optimization: OptimizationDashboard | null;
  pipeline: PipelineDashboardResponse | null;
  extension: DouyinExtensionStatusResponse | null;
};

export function OperatorHomePage() {
  const t = useT();
  const [snapshot, setSnapshot] = useState<OperatorHomeSnapshot | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = snapshot ? "refresh" : "initial";
    try {
      const result = await request.run(async () => {
        const [candidateResult, jobsPayload, health, queue, optimization, pipeline, extension] = await Promise.all([
          fetchCandidates(DEFAULT_FILTERS),
          fetchJobs(undefined, { limit: 25 }),
          fetchPublishHealthDashboard("last_7_days"),
          fetchPublishControlQueue(),
          fetchOptimizationDashboard(),
          fetchPipelineDashboard().catch(() => null),
          fetchDouyinExtensionStatus().catch(() => null)
        ]);
        return { candidates: candidateResult.candidates, jobs: jobsPayload.jobs, health, queue, optimization, pipeline, extension };
      }, setSnapshot, mode);
      if (mode === "refresh" && result) notify({ id: "home-refresh", message: "Home refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "home-refresh", message: err instanceof Error ? err.message : t("operatorHome.loadError"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const recentSourceVideoId = useMemo(
    () => (snapshot ? pickRecentSourceVideoId(snapshot.candidates, snapshot.queue) : null),
    [snapshot]
  );
  const readyDraftSourceVideoId = useMemo(
    () => (snapshot ? firstReadyDraftSourceVideoId(snapshot.queue, snapshot.health) : null),
    [snapshot]
  );
  const readyDraftId = useMemo(
    () => (snapshot ? firstReadyDraftId(snapshot.queue, snapshot.health) : null),
    [snapshot]
  );
  const reconciliationDraftId = useMemo(
    () => (snapshot ? firstReconciliationDraftId(snapshot.health) : null),
    [snapshot]
  );

  const metrics = snapshot
    ? buildOperatorMetrics({
        candidates: snapshot.candidates,
        jobs: snapshot.jobs,
        health: snapshot.health,
        queue: snapshot.queue,
        pipeline: snapshot.pipeline
      })
    : [];

  const nextWork = snapshot ? buildNextWork(snapshot.pipeline) : [];
  const freshness = snapshot ? buildFreshness(snapshot.pipeline) : null;
  const extensionSignal = snapshot ? buildExtensionSignal(snapshot.extension) : null;
  const publishSuccess = snapshot ? buildPublishSuccessMetric(snapshot.health) : null;

  const actionQueue = snapshot
    ? buildActionQueue({
        candidates: snapshot.candidates,
        health: snapshot.health,
        queue: snapshot.queue,
        recentSourceVideoId
      })
    : [];

  const recentActivity = snapshot
    ? buildRecentActivity({
        candidates: snapshot.candidates,
        jobs: snapshot.jobs,
        health: snapshot.health
      })
    : [];

  const quickLaunchItems = buildQuickLaunchItems({ recentSourceVideoId, readyDraftSourceVideoId, readyDraftId });
  const continueItems = buildContinueItems({ recentSourceVideoId, readyDraftId, reconciliationDraftId });
  const optimizationHint = snapshot?.optimization?.ready_draft_routing_hints[0]?.explanation[0] ?? null;

  return (
    <OperatorStudioShell
      actions={<TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />}
      description={t("home.description")}
      title={t("home.title")}
    >
      <AsyncContentBoundary
        errorState={<div><h1>{t("operatorHome.couldNotLoad")}</h1><p>{request.error?.message}</p><button type="button" onClick={() => void load()}>{t("common.retry")}</button></div>}
        refreshing={request.refreshing}
        skeletonVariant="gallery"
        status={!snapshot ? (request.error ? "error" : "loading") : "success"}
      >
      {snapshot && freshness && extensionSignal && publishSuccess ? (
        <div className="operator-home">
          <FreshnessStrip freshness={freshness} extension={extensionSignal} publishSuccess={publishSuccess} />
          <OverviewCards metrics={metrics} />
          <NextWorkPanel items={nextWork} />
          <ContinuePanel items={continueItems} />

          <section className="operator-home-layout">
            <div className="operator-home-main">
              <ActionQueuePanel items={actionQueue} />
              <QuickLaunchGrid items={quickLaunchItems} />
            </div>
            <aside className="operator-home-side">
              <RecentActivityPanel items={recentActivity} />
              {optimizationHint ? (
                <section className="operator-home-panel operator-home-opt">
                  <div className="operator-home-panel__head">
                    <div>
                      <h2>{t("operatorHome.optimizationSignal")}</h2>
                      <p>{t("operatorHome.optimizationSignalDesc")}</p>
                    </div>
                  </div>
                  <div className="operator-home-panel__body">
                    <p className="operator-home-opt__hint">{optimizationHint}</p>
                    <a className="operator-home-panel__link" href="/optimization">
                      {t("operatorHome.openOptimization")}
                    </a>
                  </div>
                </section>
              ) : null}
            </aside>
          </section>
        </div>
      ) : null}
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}
