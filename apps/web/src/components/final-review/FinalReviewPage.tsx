"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from "react";
import { useT } from "../../lib/i18n";
import {
  approveRender,
  approveOcrVisual,
  createOcrJob,
  createRiskDecision,
  createRenderJob,
  fetchJob,
  fetchLatestRender,
  fetchOcrSummary,
  fetchRiskSummary,
  fetchSourceVideoAssetManifest,
  markRenderPublishReady,
  runRiskScan,
  updateRiskFlagStatus
} from "../../lib/api";
import { pollAnalyzeJobUntilSettled } from "../../lib/transcriptEditorReanalyze";
import { useAsyncAction } from "../../lib/useAsyncAction";
import type { OcrSummaryResponse } from "../../types/ocr";
import {
  DEFAULT_FINAL_REVIEW_CHECKLIST,
  checklistComplete,
  findCurrentSourceVideoAsset,
  getRenderWarnings,
  isApproved,
  isPublishReady,
  nextCompareMode,
  resolveFinalReviewPrepFocus
} from "../../lib/finalReviewState";
import type {
  ChecklistState,
  CompareMode,
  FinalReviewChecklistKey,
  RenderOutput,
  SourceVideoAssetManifest
} from "../../types/final-review";
import type { OperatorRiskDecisionType, RiskFlag, RiskSummary } from "../../types/risk";
import { RiskSummaryCard } from "../risk/RiskSummaryCard";
import { useNotice } from "../shared/NoticeCenter";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { FinalCompareViewer } from "./FinalCompareViewer";
import { FinalRenderMetadataPanel } from "./FinalRenderMetadataPanel";
import { FinalReviewActions } from "./FinalReviewActions";
import { FinalReviewChecklist } from "./FinalReviewChecklist";
import { FinalReviewHeader } from "./FinalReviewHeader";
import { FinalReviewEmptyState, FinalReviewErrorState } from "./FinalReviewStates";
import { FinalReviewVisualCheckpoint } from "./FinalReviewVisualCheckpoint";
import { FinalReviewWarningsPanel } from "./FinalReviewWarningsPanel";

type RailTab = "review" | "visual" | "risk" | "info";

export type FinalReviewPageHandle = {
  refresh: () => Promise<void>;
};

export const FinalReviewPage = forwardRef<FinalReviewPageHandle, { sourceVideoId: string }>(
  function FinalReviewPage({ sourceVideoId }, ref) {
  const t = useT();
  const asyncAction = useAsyncAction();
  const { notify } = useNotice();
  const [render, setRender] = useState<RenderOutput | null>(null);
  const [manifest, setManifest] = useState<SourceVideoAssetManifest | null>(null);
  const [ocrSummary, setOcrSummary] = useState<OcrSummaryResponse | null>(null);
  const [compareMode, setCompareMode] = useState<CompareMode>("side_by_side");
  const [checklist, setChecklist] = useState<ChecklistState>(DEFAULT_FINAL_REVIEW_CHECKLIST);
  const [railTab, setRailTab] = useState<RailTab>("review");
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [ocrBusy, setOcrBusy] = useState(false);
  const [approveBusy, setApproveBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [ocrMessage, setOcrMessage] = useState<string | null>(null);
  const [riskSummary, setRiskSummary] = useState<RiskSummary | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);

  const loadData = useCallback(async (mode: "initial" | "refresh" = "initial") => {
    if (mode === "initial") setLoading(true);
    setError(null);
    try {
      const [latestRender, assetManifest] = await Promise.all([
        fetchLatestRender(sourceVideoId),
        fetchSourceVideoAssetManifest(sourceVideoId)
      ]);
      setRender(latestRender);
      setManifest(assetManifest);
      try {
        setOcrSummary(await fetchOcrSummary(sourceVideoId));
      } catch {
        setOcrSummary(null);
      }
      if (latestRender) {
        setRiskSummary(await fetchRiskSummary("RENDER_OUTPUT", latestRender.id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("finalReviewPage.loadError"));
    } finally {
      if (mode === "initial") setLoading(false);
    }
  }, [sourceVideoId, t]);

  useImperativeHandle(
    ref,
    () => ({
      refresh: async () => {
        await loadData("refresh");
      }
    }),
    [loadData]
  );

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const finalAssetId = render?.media_asset_id ?? null;
  const originalAssetId = useMemo(() => findCurrentSourceVideoAsset(manifest)?.id ?? null, [manifest]);
  const canPublishReady = render ? checklistComplete(checklist) && isApproved(render) : false;

  function toggleChecklist(key: FinalReviewChecklistKey) {
    setChecklist((current) => ({ ...current, [key]: !current[key] }));
  }

  function setAllChecklist(checked: boolean) {
    setChecklist({
      narration_clear: checked,
      subtitle_ok: checked,
      timing_ok: checked,
      render_clean: checked,
      playable: checked,
      warnings_checked: checked
    });
  }

  async function handleApprove() {
    if (!render) return;
    setActionBusy(true);
    setActionMessage(null);
    try {
      const approved = await approveRender(render.id);
      setRender(approved);
      setActionMessage(t("finalReviewPage.approveSuccess"));
      notify({ id: `final-review-approve-${render.id}`, message: t("finalReviewPage.approveSuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("finalReviewPage.approveError"));
    } finally {
      setActionBusy(false);
    }
  }

  async function handlePublishReady() {
    if (!render) return;
    if (!canPublishReady) {
      setError(t("finalReviewPage.publishReadyChecklist"));
      return;
    }
    const warnings = getRenderWarnings(render);
    if (riskSummary && !riskSummary.gate.can_continue) {
      setError(t("finalReviewPage.publishReadyRisk"));
      return;
    }
    if (riskSummary?.gate.requires_operator_decision && !riskSummary.latest_decision) {
      setError(t("finalReviewPage.publishReadyDecision"));
      return;
    }
    if (warnings.length > 0 && !window.confirm(t("finalReviewPage.warningsConfirm"))) return;
    if (!window.confirm(t("finalReviewPage.publishReadyConfirm"))) return;
    setActionBusy(true);
    setActionMessage(null);
    try {
      const updated = await markRenderPublishReady(render.id);
      setRender(updated);
      setActionMessage(t("finalReviewPage.publishReadySuccess"));
      notify({ id: `final-review-ready-${render.id}`, message: t("finalReviewPage.publishReadySuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("finalReviewPage.publishReadyError"));
    } finally {
      setActionBusy(false);
    }
  }

  async function handleRiskScan() {
    if (!render) return;
    setRiskLoading(true);
    try {
      setRiskSummary(await runRiskScan("RENDER_OUTPUT", render.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("finalReviewPage.riskScanError"));
    } finally {
      setRiskLoading(false);
    }
  }

  async function handleRiskFlagAction(flag: RiskFlag, action: "acknowledge" | "resolve" | "waive") {
    if (!render) return;
    setRiskLoading(true);
    try {
      await updateRiskFlagStatus(flag.id, action);
      setRiskSummary(await fetchRiskSummary("RENDER_OUTPUT", render.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("finalReviewPage.riskFlagError"));
    } finally {
      setRiskLoading(false);
    }
  }

  async function handleRiskDecision(decision: OperatorRiskDecisionType) {
    if (!render) return;
    setRiskLoading(true);
    try {
      setRiskSummary(await createRiskDecision("RENDER_OUTPUT", render.id, decision));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("finalReviewPage.riskDecisionError"));
    } finally {
      setRiskLoading(false);
    }
  }

  async function pollRenderJob(jobId: string) {
    return pollAnalyzeJobUntilSettled({
      fetchStatus: async () => {
        const next = await fetchJob(jobId);
        return { status: next.status, error_message: next.error_message };
      },
      maxAttempts: 240
    });
  }

  async function announceRenderLifecycle(jobId: string) {
    const noticeId = `final-review-render-${sourceVideoId}`;
    const queued = t("finalReviewStates.renderQueued").replace("{jobId}", jobId);
    notify({ id: `${noticeId}-queued`, message: queued, tone: "info" });
    notify({
      id: noticeId,
      message: t("finalReviewStates.renderInProgress"),
      tone: "info",
      durationMs: null
    });
    return noticeId;
  }

  async function handleStartFirstRender() {
    if (!window.confirm(t("finalReviewStates.startRenderConfirm"))) return;
    setActionBusy(true);
    setActionMessage(null);
    setError(null);
    const noticeId = `final-review-render-${sourceVideoId}`;
    try {
      const job = await createRenderJob(sourceVideoId, true);
      await announceRenderLifecycle(job.job_id);
      const settled = await pollRenderJob(job.job_id);
      if (settled.outcome === "success") {
        await loadData();
        notify({ id: noticeId, message: t("finalReviewStates.renderSuccess"), tone: "success" });
        return;
      }
      if (settled.outcome === "failed") {
        const message = `${t("finalReviewStates.renderFailed")}: ${settled.errorMessage ?? settled.status}`;
        notify({ id: noticeId, message, tone: "error" });
        return;
      }
      notify({ id: noticeId, message: t("finalReviewStates.renderTimeout"), tone: "error" });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewStates.renderFailed");
      notify({ id: noticeId, message, tone: "error" });
    } finally {
      setActionBusy(false);
    }
  }

  async function handleRerender() {
    if (!window.confirm(t("finalReviewPage.rerenderConfirm"))) return;
    setActionBusy(true);
    setActionMessage(null);
    setError(null);
    const noticeId = `final-review-render-${sourceVideoId}`;
    try {
      const job = await createRenderJob(sourceVideoId, true);
      await announceRenderLifecycle(job.job_id);
      const settled = await pollRenderJob(job.job_id);
      if (settled.outcome === "success") {
        await loadData();
        notify({ id: noticeId, message: t("finalReviewStates.renderSuccess"), tone: "success" });
        return;
      }
      if (settled.outcome === "failed") {
        await loadData();
        const message = `${t("finalReviewStates.renderFailed")}: ${settled.errorMessage ?? settled.status}`;
        notify({ id: noticeId, message, tone: "error" });
        return;
      }
      notify({ id: noticeId, message: t("finalReviewStates.renderTimeout"), tone: "error" });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewPage.rerenderError");
      notify({ id: noticeId, message, tone: "error" });
    } finally {
      setActionBusy(false);
    }
  }

  async function handleAnalyzeOcr() {
    setOcrBusy(true);
    setOcrMessage(null);
    setError(null);
    try {
      const created = await createOcrJob(sourceVideoId, { forceRefresh: true, cleanHardsub: true });
      const settled = await pollAnalyzeJobUntilSettled({
        fetchStatus: async () => {
          const job = await fetchJob(created.job_id);
          return { status: job.status, error_message: job.error_message };
        },
        // PaddleOCR CPU on Windows can exceed the default ~6–8 min audio poll budget.
        intervalMs: 2000,
        maxAttempts: 900
      });
      if (settled.outcome === "success") {
        const summary = await fetchOcrSummary(sourceVideoId);
        setOcrSummary(summary);
        const noFreshClean =
          summary.clean_produced === false ||
          (summary.warnings || []).some(
            (warning) => warning === "clean_skipped_no_hardsub" || warning === "no_hardsub_detected"
          );
        const message = noFreshClean ? t("finalReviewVisual.analyzeNoOutput") : t("finalReviewVisual.analyzeSuccess");
        setOcrMessage(message);
        notify({
          id: `final-review-ocr-${sourceVideoId}`,
          message,
          tone: noFreshClean ? "warning" : "success"
        });
        return;
      }
      if (settled.outcome === "failed") {
        setError(`${t("finalReviewVisual.analyzeFailed")}: ${settled.errorMessage ?? settled.status}`);
        return;
      }
      setError(
        settled.status
          ? `${t("finalReviewVisual.analyzeTimeout")} (${settled.status})`
          : t("finalReviewVisual.analyzeTimeout")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t("finalReviewVisual.analyzeFailed"));
    } finally {
      setOcrBusy(false);
    }
  }

  async function handleApproveVisual() {
    setApproveBusy(true);
    setOcrMessage(null);
    try {
      setOcrSummary(await approveOcrVisual(sourceVideoId));
      setOcrMessage(t("finalReviewVisual.approveSuccess"));
      notify({ id: `final-review-visual-${sourceVideoId}`, message: t("finalReviewVisual.approveSuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("finalReviewVisual.approveFailed"));
    } finally {
      setApproveBusy(false);
    }
  }

  if (loading) {
    return (
      <main className="final-review">
        <AsyncContentBoundary status="loading" skeletonVariant="detail" loadingLabel={t("finalReviewStates.loading")}>
          {null}
        </AsyncContentBoundary>
      </main>
    );
  }
  if (error && !render && !ocrSummary) return <FinalReviewErrorState message={error} onRetry={loadData} />;
  if (!render) {
    return (
      <main className="final-review final-review--prep">
        <header className="final-review-preheader final-review-preheader--studio">
          <div className="final-review-preheader__copy">
            <span className="fr-topbar__kicker">{t("finalReviewStates.prepKicker")}</span>
            <h1>{t("finalReviewHeader.title")}</h1>
            <p>{t("finalReviewStates.emptyPrepHint")}</p>
          </div>
        </header>
        {error ? <div className="inline-error">{error}</div> : null}
        {ocrMessage ? <p className="action-message">{ocrMessage}</p> : null}
        {actionMessage ? <p className="action-message">{actionMessage}</p> : null}
        <section className="final-review-layout final-review-layout--prep">
          <FinalReviewEmptyState
            sourceVideoId={sourceVideoId}
            actionBusy={actionBusy || ocrBusy || approveBusy}
            startRenderPending={asyncAction.isPending("start-render")}
            prepFocus={resolveFinalReviewPrepFocus(ocrSummary)}
            onStartRender={() => void asyncAction.run("start-render", handleStartFirstRender)}
          />
          <aside className="final-review-side">
            <FinalReviewVisualCheckpoint
              summary={ocrSummary}
              analyzeBusy={ocrBusy}
              approveBusy={approveBusy}
              message={ocrMessage}
              presentation="prep"
              prepFocus={resolveFinalReviewPrepFocus(ocrSummary)}
              onAnalyze={() => void asyncAction.run("analyze-ocr", handleAnalyzeOcr)}
              onApprove={() => void asyncAction.run("approve-visual", handleApproveVisual)}
            />
          </aside>
        </section>
      </main>
    );
  }

  const tabs: { id: RailTab; label: string }[] = [
    { id: "review", label: t("finalReviewTabs.review") },
    { id: "visual", label: t("finalReviewTabs.visual") },
    { id: "risk", label: t("finalReviewTabs.risk") },
    { id: "info", label: t("finalReviewTabs.info") }
  ];

  return (
    <main className={`final-review final-review--workspace${railTab === "review" ? "" : " final-review--focus-rail"}`}>
      <FinalReviewHeader
        render={render}
        manifest={manifest}
        actionBusy={actionBusy}
        rerenderPending={asyncAction.isPending("rerender")}
        onRerender={() => void asyncAction.run("rerender", handleRerender)}
      />
      {error ? <div className="inline-error fr-inline-error">{error}</div> : null}
      {isPublishReady(render) ? <div className="publish-ready-banner">{t("finalReviewPage.isPublishReady")}</div> : null}
      <section className="fr-workspace">
        <FinalCompareViewer
          mode={compareMode}
          finalAssetId={finalAssetId}
          originalAssetId={originalAssetId}
          onModeChange={setCompareMode}
          onQuickToggle={() => setCompareMode((current) => nextCompareMode(current))}
        />
        <aside className="fr-rail" aria-label={t("finalReviewTabs.railLabel")}>
          <div className="fr-rail__tabs" role="tablist">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={railTab === tab.id}
                className={railTab === tab.id ? "active" : ""}
                onClick={() => setRailTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="fr-rail__panel" role="tabpanel">
            {railTab === "review" ? (
              <div className="fr-rail__stack">
                <FinalReviewChecklist
                  checklist={checklist}
                  onToggle={toggleChecklist}
                  onSetAll={setAllChecklist}
                />
                <FinalReviewWarningsPanel render={render} />
              </div>
            ) : null}
            {railTab === "visual" ? (
              <FinalReviewVisualCheckpoint
                summary={ocrSummary}
                analyzeBusy={ocrBusy}
                approveBusy={approveBusy}
                message={ocrMessage}
                onAnalyze={() => void asyncAction.run("analyze-ocr", handleAnalyzeOcr)}
                onApprove={() => void asyncAction.run("approve-visual", handleApproveVisual)}
              />
            ) : null}
            {railTab === "risk" ? (
              <RiskSummaryCard
                summary={riskSummary}
                loading={riskLoading}
                onScan={() => void handleRiskScan()}
                onFlagAction={(flag, action) => void handleRiskFlagAction(flag, action)}
                onDecision={(decision) => void handleRiskDecision(decision)}
              />
            ) : null}
            {railTab === "info" ? <FinalRenderMetadataPanel render={render} manifest={manifest} /> : null}
          </div>
        </aside>
      </section>
      {railTab === "review" ? (
        <FinalReviewActions
          render={render}
          checklist={checklist}
          actionBusy={actionBusy}
          approvePending={asyncAction.isPending("approve-render")}
          publishReadyPending={asyncAction.isPending("publish-ready")}
          actionMessage={actionMessage}
          onApprove={() => void asyncAction.run("approve-render", handleApprove)}
          onPublishReady={() => void asyncAction.run("publish-ready", handlePublishReady)}
        />
      ) : null}
    </main>
  );
  }
);
