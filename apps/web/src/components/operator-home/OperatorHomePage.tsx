"use client";

import { useEffect, useMemo, useState } from "react";
import { useT } from "../../lib/i18n";
import {
  fetchCandidates,
  fetchJobs,
  fetchOptimizationDashboard,
  fetchPublishControlQueue,
  fetchPublishHealthDashboard
} from "../../lib/api";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import {
  buildActionQueue,
  buildContinueItems,
  buildOperatorMetrics,
  buildQuickLaunchItems,
  buildRecentActivity,
  firstReadyDraftId,
  firstReadyDraftSourceVideoId,
  firstReconciliationDraftId,
  pickRecentSourceVideoId
} from "../../lib/operatorHomeState";
import { DEFAULT_FILTERS } from "../../lib/reviewBoardState";
import type { PublishHealthDashboard } from "../../types/analytics";
import type { Job } from "../../types/jobs";
import type { OptimizationDashboard } from "../../types/optimization";
import type { PublishControlQueue } from "../../types/publish-control";
import type { Candidate } from "../../types/review-board";
import { ActionQueuePanel } from "./ActionQueuePanel";
import { OverviewCards } from "./OverviewCards";
import { QuickLaunchGrid } from "./QuickLaunchGrid";
import { RecentActivityPanel } from "./RecentActivityPanel";
import { ContinuePanel } from "./ContinuePanel";

type OperatorHomeSnapshot = {
  candidates: Candidate[];
  jobs: Job[];
  health: PublishHealthDashboard | null;
  queue: PublishControlQueue | null;
  optimization: OptimizationDashboard | null;
};

export function OperatorHomePage() {
  const t = useT();
  const [snapshot, setSnapshot] = useState<OperatorHomeSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [candidateResult, jobsPayload, health, queue, optimization] = await Promise.all([
        fetchCandidates(DEFAULT_FILTERS),
        fetchJobs(undefined, { limit: 25 }),
        fetchPublishHealthDashboard("last_7_days"),
        fetchPublishControlQueue(),
        fetchOptimizationDashboard()
      ]);
      setSnapshot({ candidates: candidateResult.candidates, jobs: jobsPayload.jobs, health, queue, optimization });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("operatorHome.loadError"));
    } finally {
      setLoading(false);
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
        queue: snapshot.queue
      })
    : [];

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
      actions={<TopbarRefreshButton busy={loading && Boolean(snapshot)} disabled={loading && !snapshot} onClick={() => void load()} />}
      description={t("home.description")}
      title={t("home.title")}
    >
      {loading && !snapshot ? <div className="state-panel skeleton">{t("common.loading")} {t("home.title")}</div> : null}

      {error && !snapshot ? (
        <div className="state-panel">
          <h1>{t("operatorHome.couldNotLoad")}</h1>
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>{t("common.retry")}</button>
        </div>
      ) : null}

      {snapshot ? (
        <div className="operator-home">
          {error ? <div className="inline-error">{error}</div> : null}
          <OverviewCards metrics={metrics} />

          <section className="operator-home-layout">
            <div className="operator-home-main">
              <ActionQueuePanel items={actionQueue} />
              <QuickLaunchGrid items={quickLaunchItems} />
            </div>
            <aside className="operator-home-side">
              <ContinuePanel items={continueItems} />
              <RecentActivityPanel items={recentActivity} />
              <section className="operator-panel">
                <div className="operator-panel-heading">
                  <div>
                    <h2>{t("operatorHome.optimizationSignal")}</h2>
                    <p>{t("operatorHome.optimizationSignalDesc")}</p>
                  </div>
                </div>
                <p className="muted">{optimizationHint ?? t("operatorHome.noOptimizationHint")}</p>
                <a className="operator-inline-link" href="/optimization">{t("operatorHome.openOptimization")}</a>
              </section>
            </aside>
          </section>
        </div>
      ) : null}
    </OperatorStudioShell>
  );
}
