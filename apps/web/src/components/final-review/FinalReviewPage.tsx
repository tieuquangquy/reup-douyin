"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import {
  approveRender,
  approveTranslationDraft,
  approveResidualReview,
  approveQualityAudioReview,
  approveOcrVisual,
  createOcrJob,
  createRiskDecision,
  createRenderJob,
  cancelJob,
  fetchJob,
  fetchJobs,
  fetchLatestRender,
  fetchOcrSummary,
  fetchRiskSummary,
  fetchSourceVideoAssetManifest,
  markRenderPublishReady,
  requestResidualTranslationSuggestions,
  runRiskScan,
  submitOcrReview,
  submitResidualTriage,
  submitVisualTranslationReview,
  updateRiskFlagStatus
} from "../../lib/api";
import { pickActiveOcrJob, pickActiveRenderJob } from "../../lib/finalReviewJobReattach";
import { pollAnalyzeJobUntilSettled } from "../../lib/transcriptEditorReanalyze";
import { useAsyncAction } from "../../lib/useAsyncAction";
import type { OcrSummaryResponse } from "../../types/ocr";
import { loadFinalReviewChecklist, saveFinalReviewChecklist } from "../../lib/finalReviewChecklistStorage";
import {
  DEFAULT_FINAL_REVIEW_CHECKLIST,
  checklistComplete,
  findCurrentSourceVideoAsset,
  getRenderWarnings,
  hasCurrentQualityVisualAuthority,
  isApproved,
  isPublishReady,
  isFinalReviewDialogueTranslationApprovalPending,
  isFinalReviewOcrReviewPending,
  nextCompareMode,
  resolveFinalReviewCompareDiff,
  resolveFinalReviewPrepFocus,
  resolveFinalReviewReadiness,
  resolveFinalReviewWorkspaceRender,
  formatFinalReviewFailedRenderDetail
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
import {
  FinalReviewActionStatus,
  type FinalReviewActionStatusState
} from "./FinalReviewActionStatus";
import { FinalReviewChecklist } from "./FinalReviewChecklist";
import { FinalReviewHeader } from "./FinalReviewHeader";
import { FinalReviewReadinessStrip } from "./FinalReviewReadinessStrip";
import { FinalReviewEmptyState, FinalReviewErrorState, FinalReviewLoadingState, FinalReviewPrepBriefing, FinalReviewPrepJourney } from "./FinalReviewStates";
import { FinalReviewVisualCheckpoint } from "./FinalReviewVisualCheckpoint";
import { FinalReviewWarningsPanel } from "./FinalReviewWarningsPanel";
import { QualityHandoffPanel } from "./QualityHandoffPanel";
import { FinalReviewRailIcon, type FinalReviewRailIconKind } from "./FinalReviewRailIcon";

type RailTab = "review" | "visual" | "risk" | "info" | "handoff";

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
  const [renderBusy, setRenderBusy] = useState(false);
  const [approveBusy, setApproveBusy] = useState(false);
  const [audioApproveBusy, setAudioApproveBusy] = useState(false);
  const [residualTranslationBusy, setResidualTranslationBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<FinalReviewActionStatusState | null>(null);
  const [ocrStatus, setOcrStatus] = useState<FinalReviewActionStatusState | null>(null);
  const [ocrProgressPercent, setOcrProgressPercent] = useState<number | null>(null);
  const [renderProgressPercent, setRenderProgressPercent] = useState<number | null>(null);
  const [ocrJobId, setOcrJobId] = useState<string | null>(null);
  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const [ocrWatchPaused, setOcrWatchPaused] = useState(false);
  const [renderWatchPaused, setRenderWatchPaused] = useState(false);
  const [ocrPausePending, setOcrPausePending] = useState(false);
  const [ocrCancelPending, setOcrCancelPending] = useState(false);
  const [renderPausePending, setRenderPausePending] = useState(false);
  const [renderCancelPending, setRenderCancelPending] = useState(false);
  const [riskSummary, setRiskSummary] = useState<RiskSummary | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const ocrBusyRef = useRef(false);
  const ocrResumeAttemptedRef = useRef(false);
  const renderResumeAttemptedRef = useRef(false);
  const ocrCancelRequestedRef = useRef(false);
  const ocrWatchPausedRef = useRef(false);
  const renderBusyRef = useRef(false);
  const renderCancelRequestedRef = useRef(false);
  const renderWatchPausedRef = useRef(false);
  const residualTranslationAttemptedRef = useRef<string | null>(null);

  const loadData = useCallback(async (mode: "initial" | "refresh" = "initial") => {
    if (mode === "initial") setLoading(true);
    setError(null);
    try {
      const [latestRender, assetManifest] = await Promise.all([
        fetchLatestRender(sourceVideoId),
        fetchSourceVideoAssetManifest(sourceVideoId)
      ]);
      const workspaceRender = resolveFinalReviewWorkspaceRender(latestRender);
      setRender(workspaceRender);
      setManifest(assetManifest);
      try {
        const nextOcrSummary = await fetchOcrSummary(sourceVideoId);
        setOcrSummary(nextOcrSummary);
        if (hasCurrentQualityVisualAuthority(nextOcrSummary)) {
          // The current hash-bound artifact is newer authority than any error
          // retained in this mounted page from a previous terminal job.
          setOcrStatus(null);
        }
      } catch {
        setOcrSummary(null);
      }
      if (workspaceRender) {
        setRiskSummary(await fetchRiskSummary("RENDER_OUTPUT", workspaceRender.id));
      } else {
        setRiskSummary(null);
        if (latestRender?.status === "FAILED") {
          const detail = formatFinalReviewFailedRenderDetail(latestRender.error_message);
          const message = detail
            ? `${t("finalReviewStates.renderFailed")}: ${detail}`
            : t("finalReviewStates.renderFailed");
          setActionStatus({ phase: "error", message });
        }
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

  useEffect(() => {
    ocrResumeAttemptedRef.current = false;
    renderResumeAttemptedRef.current = false;
    residualTranslationAttemptedRef.current = null;
  }, [sourceVideoId]);

  useEffect(() => {
    if (!render?.id) {
      setChecklist(DEFAULT_FINAL_REVIEW_CHECKLIST);
      return;
    }
    setChecklist(loadFinalReviewChecklist(render.id) ?? DEFAULT_FINAL_REVIEW_CHECKLIST);
  }, [render?.id]);

  const finalAssetId = render?.media_asset_id ?? null;
  const originalAssetId = useMemo(() => findCurrentSourceVideoAsset(manifest)?.id ?? null, [manifest]);
  const canPublishReady = render ? checklistComplete(checklist) && isApproved(render) : false;
  const readiness = useMemo(
    () => (render ? resolveFinalReviewReadiness({ checklist, render, riskSummary }) : null),
    [checklist, render, riskSummary]
  );
  const compareDiff = useMemo(
    () => (render ? resolveFinalReviewCompareDiff(render, manifest) : null),
    [manifest, render]
  );

  function persistChecklist(next: ChecklistState) {
    if (render?.id) saveFinalReviewChecklist(render.id, next);
    setChecklist(next);
  }

  function toggleChecklist(key: FinalReviewChecklistKey) {
    persistChecklist({ ...checklist, [key]: !checklist[key] });
  }

  function setAllChecklist(checked: boolean) {
    persistChecklist({
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
    setActionStatus(null);
    try {
      const approved = await approveRender(render.id);
      setRender(approved);
      setActionStatus({ phase: "success", message: t("finalReviewPage.approveSuccess") });
      notify({ id: `final-review-approve-${render.id}`, message: t("finalReviewPage.approveSuccess"), tone: "success" });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewPage.approveError");
      setActionStatus({ phase: "error", message });
      setError(message);
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
    setActionStatus(null);
    try {
      const updated = await markRenderPublishReady(render.id);
      setRender(updated);
      setRailTab("handoff");
      setActionStatus({ phase: "success", message: t("finalReviewPage.publishReadySuccess") });
      notify({ id: `final-review-ready-${render.id}`, message: t("finalReviewPage.publishReadySuccess"), tone: "success" });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewPage.publishReadyError");
      setActionStatus({ phase: "error", message });
      setError(message);
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
    setRenderJobId(jobId);
    renderCancelRequestedRef.current = false;
    renderWatchPausedRef.current = false;
    setRenderWatchPaused(false);
    return pollAnalyzeJobUntilSettled({
      fetchStatus: async () => {
        const next = await fetchJob(jobId);
        return {
          status: next.status,
          error_message: next.error_message,
          progress_percent: next.progress_percent
        };
      },
      onSnapshot: (snapshot) => {
        if (typeof snapshot.progress_percent === "number") {
          setRenderProgressPercent(snapshot.progress_percent);
        }
      },
      shouldStop: () => renderCancelRequestedRef.current || renderWatchPausedRef.current,
      // Adaptive Phase 4 can spend ~10–15 minutes encoding lossless
      // intermediates before NVENC and final Output QA.  Keep polling long
      // enough to observe the durable job instead of showing a false timeout
      // while the worker is healthy.
      maxAttempts: 1800
    });
  }

  function clearRenderWatchSession() {
    renderBusyRef.current = false;
    setRenderBusy(false);
    setActionBusy(false);
    setRenderJobId(null);
    setRenderWatchPaused(false);
    renderWatchPausedRef.current = false;
    setRenderPausePending(false);
    setRenderCancelPending(false);
    setRenderProgressPercent(null);
    renderCancelRequestedRef.current = false;
  }

  function finishRenderPollSession() {
    if (renderWatchPausedRef.current && !renderCancelRequestedRef.current) {
      renderBusyRef.current = false;
      setRenderBusy(false);
      setActionBusy(false);
      setRenderPausePending(false);
      setRenderCancelPending(false);
      return;
    }
    clearRenderWatchSession();
  }

  async function settleRenderOutcome(
    settled: Awaited<ReturnType<typeof pollRenderJob>>,
    noticeId: string,
    options?: { reloadOnFail?: boolean }
  ) {
    if (settled.outcome === "success") {
      await loadData();
      setActionStatus({ phase: "success", message: t("finalReviewStates.renderSuccess") });
      notify({ id: noticeId, message: t("finalReviewStates.renderSuccess"), tone: "success" });
      return;
    }
    if (settled.outcome === "cancelled") {
      if (renderWatchPausedRef.current && !renderCancelRequestedRef.current) {
        const message = t("finalReviewStates.renderWatchPaused");
        setRenderWatchPaused(true);
        setActionStatus({ phase: "warning", message });
        return;
      }
      const message = t("finalReviewStates.renderCancelled");
      setActionStatus({ phase: "warning", message });
      notify({ id: `${noticeId}-cancel`, message, tone: "info" });
      return;
    }
    if (settled.outcome === "failed") {
      if (options?.reloadOnFail) await loadData();
      const message = `${t("finalReviewStates.renderFailed")}: ${settled.errorMessage ?? settled.status}`;
      setActionStatus({ phase: "error", message });
      notify({ id: noticeId, message, tone: "error" });
      return;
    }
    const timeoutMessage = t("finalReviewStates.renderTimeout");
    setActionStatus({ phase: "error", message: timeoutMessage });
    notify({ id: noticeId, message: timeoutMessage, tone: "error" });
  }

  async function announceRenderLifecycle(jobId: string) {
    const noticeId = `final-review-render-${sourceVideoId}`;
    const queued = t("finalReviewStates.renderQueued").replace("{jobId}", jobId);
    setActionStatus({ phase: "queued", message: queued });
    notify({ id: `${noticeId}-queued`, message: queued, tone: "info" });
    setActionStatus({ phase: "running", message: t("finalReviewStates.renderInProgress") });
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
    renderBusyRef.current = true;
    renderCancelRequestedRef.current = false;
    renderWatchPausedRef.current = false;
    setRenderWatchPaused(false);
    setRenderBusy(true);
    setActionBusy(true);
    setRenderPausePending(false);
    setRenderCancelPending(false);
    setRenderProgressPercent(0);
    setActionStatus({ phase: "queued", message: t("finalReviewStates.renderQueued").replace("{jobId}", "…") });
    setError(null);
    const noticeId = `final-review-render-${sourceVideoId}`;
    try {
      const job = await createRenderJob(sourceVideoId, true);
      await announceRenderLifecycle(job.job_id);
      const settled = await pollRenderJob(job.job_id);
      await settleRenderOutcome(settled, noticeId);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewStates.renderFailed");
      setActionStatus({ phase: "error", message });
      notify({ id: noticeId, message, tone: "error" });
    } finally {
      finishRenderPollSession();
    }
  }

  async function handleRerender() {
    if (!window.confirm(t("finalReviewPage.rerenderConfirm"))) return;
    renderBusyRef.current = true;
    renderCancelRequestedRef.current = false;
    renderWatchPausedRef.current = false;
    setRenderWatchPaused(false);
    setRenderBusy(true);
    setActionBusy(true);
    setRenderPausePending(false);
    setRenderCancelPending(false);
    setRenderProgressPercent(0);
    setActionStatus({ phase: "queued", message: t("finalReviewStates.renderQueued").replace("{jobId}", "…") });
    setError(null);
    const noticeId = `final-review-render-${sourceVideoId}`;
    try {
      const job = await createRenderJob(sourceVideoId, true);
      await announceRenderLifecycle(job.job_id);
      const settled = await pollRenderJob(job.job_id);
      await settleRenderOutcome(settled, noticeId, { reloadOnFail: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewPage.rerenderError");
      setActionStatus({ phase: "error", message });
      notify({ id: noticeId, message, tone: "error" });
    } finally {
      finishRenderPollSession();
    }
  }

  function pauseRenderWatch() {
    if (!renderJobId || renderWatchPausedRef.current || renderCancelPending) return;
    renderWatchPausedRef.current = true;
    setRenderWatchPaused(true);
    setActionStatus({ phase: "warning", message: t("finalReviewStates.renderWatchPaused") });
  }

  async function resumeRenderWatch() {
    if (!renderJobId || renderBusyRef.current || renderCancelPending) return;
    const jobId = renderJobId;
    renderWatchPausedRef.current = false;
    setRenderWatchPaused(false);
    renderBusyRef.current = true;
    setRenderBusy(true);
    setActionBusy(true);
    setRenderPausePending(true);
    setError(null);
    const noticeId = `final-review-render-${sourceVideoId}`;
    try {
      setActionStatus({ phase: "running", message: t("finalReviewStates.renderInProgress") });
      const settled = await pollRenderJob(jobId);
      await settleRenderOutcome(settled, noticeId);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewStates.renderFailed");
      setActionStatus({ phase: "error", message });
      notify({ id: noticeId, message, tone: "error" });
    } finally {
      setRenderPausePending(false);
      finishRenderPollSession();
    }
  }

  async function cancelRenderJob() {
    if (!renderJobId || renderCancelPending) return;
    const jobId = renderJobId;
    const wasWatchPaused = renderWatchPausedRef.current;
    setRenderCancelPending(true);
    renderCancelRequestedRef.current = true;
    try {
      await cancelJob(jobId);
      if (wasWatchPaused) {
        renderWatchPausedRef.current = false;
        setRenderWatchPaused(false);
        const message = t("finalReviewStates.renderCancelled");
        setActionStatus({ phase: "warning", message });
        notify({ id: `final-review-render-cancel-${sourceVideoId}`, message, tone: "info" });
        clearRenderWatchSession();
      }
    } catch (err) {
      renderCancelRequestedRef.current = false;
      const message = err instanceof Error ? err.message : t("finalReviewStates.renderFailed");
      setActionStatus({ phase: "error", message });
      notify({ id: `final-review-render-cancel-${sourceVideoId}`, message, tone: "error" });
      setRenderCancelPending(false);
    }
  }

  function clearOcrWatchSession() {
    ocrBusyRef.current = false;
    setOcrBusy(false);
    setOcrJobId(null);
    setOcrWatchPaused(false);
    ocrWatchPausedRef.current = false;
    setOcrPausePending(false);
    setOcrCancelPending(false);
    setOcrProgressPercent(null);
    ocrCancelRequestedRef.current = false;
  }

  function finishOcrPollSession() {
    if (ocrWatchPausedRef.current && !ocrCancelRequestedRef.current) {
      // Keep job id so Resume / Cancel stay available; stop the busy spinner.
      ocrBusyRef.current = false;
      setOcrBusy(false);
      setOcrPausePending(false);
      setOcrCancelPending(false);
      return;
    }
    clearOcrWatchSession();
  }

  async function settleOcrJob(jobId: string) {
    setOcrJobId(jobId);
    ocrCancelRequestedRef.current = false;
    ocrWatchPausedRef.current = false;
    setOcrWatchPaused(false);
    setOcrStatus({ phase: "running", message: t("finalReviewVisual.analyzeInProgress") });
    const settled = await pollAnalyzeJobUntilSettled({
      fetchStatus: async () => {
        const job = await fetchJob(jobId);
        return {
          status: job.status,
          error_message: job.error_message,
          progress_percent: job.progress_percent
        };
      },
      onSnapshot: (snapshot) => {
        if (typeof snapshot.progress_percent === "number") {
          setOcrProgressPercent(snapshot.progress_percent);
        }
      },
      shouldStop: () => ocrCancelRequestedRef.current || ocrWatchPausedRef.current,
      // Durable OCR can outlive short media poll budgets. Keep the checkpoint
      // attached for long-form inputs so completion refreshes without Reload.
      intervalMs: 2000,
      maxAttempts: 10_800
    });
    if (settled.outcome === "success") {
      const summary = await fetchOcrSummary(sourceVideoId);
      setOcrSummary(summary);
      const isQualityWorkflow = summary.workflow_version === "QUALITY_LOCALIZATION_V24_1";
      const noFreshClean =
        !isQualityWorkflow && (summary.clean_produced === false ||
        (summary.warnings || []).some(
          (warning) => warning === "clean_skipped_no_hardsub" || warning === "no_hardsub_detected"
        ));
      const message = isQualityWorkflow
        ? t("finalReviewVisual.reviewCompleted")
        : noFreshClean
          ? t("finalReviewVisual.analyzeNoOutput")
          : t("finalReviewVisual.analyzeSuccess");
      setOcrStatus({ phase: noFreshClean ? "warning" : "success", message });
      notify({
        id: `final-review-ocr-${sourceVideoId}`,
        message,
        tone: noFreshClean ? "warning" : "success"
      });
      return;
    }
    if (settled.outcome === "cancelled") {
      if (ocrWatchPausedRef.current && !ocrCancelRequestedRef.current) {
        const message = t("finalReviewVisual.ocrWatchPaused");
        setOcrWatchPaused(true);
        setOcrStatus({ phase: "warning", message });
        return;
      }
      const message = t("finalReviewVisual.ocrCancelled");
      setOcrStatus({ phase: "warning", message });
      notify({ id: `final-review-ocr-cancel-${sourceVideoId}`, message, tone: "info" });
      return;
    }
    if (settled.outcome === "failed") {
      const message = `${t("finalReviewVisual.analyzeFailed")}: ${settled.errorMessage ?? settled.status}`;
      setOcrStatus({ phase: "error", message });
      setError(message);
      return;
    }
    const timeoutMessage = settled.status
      ? `${t("finalReviewVisual.analyzeTimeout")} (${settled.status})`
      : t("finalReviewVisual.analyzeTimeout");
    setOcrStatus({ phase: "error", message: timeoutMessage });
    setError(timeoutMessage);
  }

  async function handleAnalyzeOcr(forceRefresh = false) {
    ocrBusyRef.current = true;
    ocrCancelRequestedRef.current = false;
    ocrWatchPausedRef.current = false;
    setOcrWatchPaused(false);
    setOcrBusy(true);
    setOcrPausePending(false);
    setOcrCancelPending(false);
    setOcrProgressPercent(0);
    setOcrStatus({ phase: "queued", message: t("finalReviewVisual.analyzeQueued") });
    setError(null);
    try {
      const created = await createOcrJob(sourceVideoId, { forceRefresh, cleanHardsub: true });
      await settleOcrJob(created.job_id);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewVisual.analyzeFailed");
      setOcrStatus({ phase: "error", message });
      setError(message);
    } finally {
      finishOcrPollSession();
    }
  }

  async function handleApproveDialogueTranslation() {
    ocrBusyRef.current = true;
    ocrCancelRequestedRef.current = false;
    ocrWatchPausedRef.current = false;
    setOcrWatchPaused(false);
    setOcrBusy(true);
    setOcrPausePending(false);
    setOcrCancelPending(false);
    setOcrProgressPercent(0);
    setOcrStatus({ phase: "queued", message: t("finalReviewVisual.approvingDialogueTranslation") });
    setError(null);
    try {
      const approval = await approveTranslationDraft(sourceVideoId);
      if (approval.ocr_resume_job_id) {
        await settleOcrJob(approval.ocr_resume_job_id);
      } else {
        const summary = await fetchOcrSummary(sourceVideoId);
        setOcrSummary(summary);
        setOcrStatus({ phase: "success", message: t("finalReviewVisual.dialogueTranslationApproved") });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewVisual.dialogueTranslationApprovalFailed");
      setOcrStatus({ phase: "error", message });
      setError(message);
    } finally {
      finishOcrPollSession();
    }
  }

  async function runLocalizationReviewJob(createJob: () => Promise<{ job_id: string }>) {
    ocrBusyRef.current = true;
    ocrCancelRequestedRef.current = false;
    ocrWatchPausedRef.current = false;
    setOcrWatchPaused(false);
    setOcrBusy(true);
    setOcrPausePending(false);
    setOcrCancelPending(false);
    setOcrProgressPercent(0);
    setOcrStatus({ phase: "queued", message: t("finalReviewVisual.reviewQueued") });
    setError(null);
    try {
      const created = await createJob();
      await settleOcrJob(created.job_id);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewVisual.analyzeFailed");
      setOcrStatus({ phase: "error", message });
      setError(message);
    } finally {
      finishOcrPollSession();
    }
  }

  function handleOcrJourneyAction() {
    if (isFinalReviewDialogueTranslationApprovalPending(ocrSummary)) {
      void asyncAction.run("approve-dialogue-translation", handleApproveDialogueTranslation);
      return;
    }
    if (isFinalReviewOcrReviewPending(ocrSummary)) {
      document
        .getElementById("final-review-ocr-review")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    void asyncAction.run("analyze-ocr", () => handleAnalyzeOcr(false));
  }

  async function handleSubmitOcrReview(
    decisions: Array<{
      content_id: string;
      decision: "APPROVE" | "EDIT" | "PRESERVE_SOURCE" | "REJECT_UI";
      ocr_text_approved?: string | null;
    }>
  ) {
    await runLocalizationReviewJob(() => submitOcrReview(sourceVideoId, decisions));
  }

  async function handleSubmitTranslationReview(
    translations: Array<{ content_id: string; vi_text: string }>
  ) {
    await runLocalizationReviewJob(() =>
      submitVisualTranslationReview(sourceVideoId, translations)
    );
  }

  async function handleSubmitResidualTriage(
    suggestions: Array<{ content_id?: string; ocr_text: string; ocr_text_corrected: string; vi_text_suggested: string }>
  ) {
    await runLocalizationReviewJob(() => submitResidualTriage(sourceVideoId, suggestions));
  }

  async function handleApproveResidual(proposalSha256: string) {
    await runLocalizationReviewJob(() => approveResidualReview(sourceVideoId, proposalSha256));
  }

  async function handleRequestResidualTranslationSuggestions() {
    setResidualTranslationBusy(true);
    try {
      await runLocalizationReviewJob(() =>
        requestResidualTranslationSuggestions(sourceVideoId)
      );
    } finally {
      setResidualTranslationBusy(false);
    }
  }

  async function resumeActiveOcrJob() {
    if (ocrBusyRef.current) return;
    try {
      const [ocrJobs, previewJobs] = await Promise.all([
        fetchJobs(undefined, { sourceVideoId, jobType: "ANALYZE_OCR", limit: 30 }),
        fetchJobs(undefined, { sourceVideoId, jobType: "RENDER_PREVIEW", limit: 30 })
      ]);
      const active = pickActiveOcrJob([...ocrJobs.jobs, ...previewJobs.jobs]);
      if (!active || ocrBusyRef.current) return;
      ocrBusyRef.current = true;
      ocrCancelRequestedRef.current = false;
      ocrWatchPausedRef.current = false;
      setOcrWatchPaused(false);
      setOcrBusy(true);
      setOcrPausePending(false);
      setOcrCancelPending(false);
      setOcrProgressPercent(
        typeof active.progress_percent === "number" ? active.progress_percent : 0
      );
      setError(null);
      try {
        const phase = active.status.toUpperCase() === "QUEUED" ? "queued" : "running";
        setOcrStatus({
          phase,
          message:
            phase === "queued"
              ? t("finalReviewVisual.analyzeQueued")
              : t("finalReviewVisual.analyzeInProgress")
        });
        await settleOcrJob(active.id);
      } finally {
        finishOcrPollSession();
      }
    } catch {
      // Re-attach is best-effort; page remains usable without the banner.
    }
  }

  async function resumeActiveRenderJob() {
    if (renderBusyRef.current) return;
    try {
      const listed = await fetchJobs(undefined, { sourceVideoId, jobType: "RENDER_FINAL", limit: 30 });
      const active = pickActiveRenderJob(listed.jobs);
      if (!active || renderBusyRef.current) return;
      renderBusyRef.current = true;
      renderCancelRequestedRef.current = false;
      renderWatchPausedRef.current = false;
      setRenderWatchPaused(false);
      setRenderBusy(true);
      setActionBusy(true);
      setRenderPausePending(false);
      setRenderCancelPending(false);
      setRenderProgressPercent(
        typeof active.progress_percent === "number" ? active.progress_percent : 0
      );
      setError(null);
      const noticeId = `final-review-render-${sourceVideoId}`;
      try {
        const phase = active.status.toUpperCase() === "QUEUED" ? "queued" : "running";
        const message =
          phase === "queued"
            ? t("finalReviewStates.renderQueued").replace("{jobId}", active.id)
            : t("finalReviewStates.renderInProgress");
        setActionStatus({ phase, message });
        notify({
          id: noticeId,
          message: t("finalReviewStates.renderInProgress"),
          tone: "info",
          durationMs: null
        });
        const settled = await pollRenderJob(active.id);
        await settleRenderOutcome(settled, noticeId, { reloadOnFail: true });
      } finally {
        finishRenderPollSession();
      }
    } catch {
      // Re-attach is best-effort; page remains usable without the banner.
    }
  }

  function pauseOcrWatch() {
    if (!ocrJobId || ocrWatchPausedRef.current || ocrCancelPending) return;
    ocrWatchPausedRef.current = true;
    setOcrWatchPaused(true);
    setOcrStatus({ phase: "warning", message: t("finalReviewVisual.ocrWatchPaused") });
  }

  async function resumeOcrWatch() {
    if (!ocrJobId || ocrBusyRef.current || ocrCancelPending) return;
    const jobId = ocrJobId;
    ocrWatchPausedRef.current = false;
    setOcrWatchPaused(false);
    ocrBusyRef.current = true;
    setOcrBusy(true);
    setOcrPausePending(true);
    setError(null);
    try {
      await settleOcrJob(jobId);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewVisual.analyzeFailed");
      setOcrStatus({ phase: "error", message });
      setError(message);
    } finally {
      setOcrPausePending(false);
      finishOcrPollSession();
    }
  }

  async function cancelOcrJob() {
    if (!ocrJobId || ocrCancelPending) return;
    const jobId = ocrJobId;
    const wasWatchPaused = ocrWatchPausedRef.current;
    setOcrCancelPending(true);
    ocrCancelRequestedRef.current = true;
    try {
      await cancelJob(jobId);
      if (wasWatchPaused) {
        // No active poll loop — settle the strip here.
        ocrWatchPausedRef.current = false;
        setOcrWatchPaused(false);
        const message = t("finalReviewVisual.ocrCancelled");
        setOcrStatus({ phase: "warning", message });
        notify({ id: `final-review-ocr-cancel-${sourceVideoId}`, message, tone: "info" });
        clearOcrWatchSession();
      }
    } catch (err) {
      ocrCancelRequestedRef.current = false;
      const message = err instanceof Error ? err.message : t("finalReviewVisual.analyzeFailed");
      setOcrStatus({ phase: "error", message });
      setError(message);
      setOcrCancelPending(false);
    }
  }

  async function handleApproveVisual() {
    setApproveBusy(true);
    setOcrStatus({ phase: "queued", message: t("finalReviewVisual.approveQueued") });
    try {
      setOcrStatus({ phase: "running", message: t("finalReviewVisual.approving") });
      setOcrSummary(await approveOcrVisual(sourceVideoId));
      setOcrStatus({ phase: "success", message: t("finalReviewVisual.approveSuccess") });
      notify({ id: `final-review-visual-${sourceVideoId}`, message: t("finalReviewVisual.approveSuccess"), tone: "success" });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewVisual.approveFailed");
      setOcrStatus({ phase: "error", message });
      setError(message);
    } finally {
      setApproveBusy(false);
    }
  }

  async function handleApproveAudio() {
    setAudioApproveBusy(true);
    setOcrStatus({ phase: "running", message: t("finalReviewVisual.approvingAudio") });
    try {
      setOcrSummary(await approveQualityAudioReview(sourceVideoId));
      setOcrStatus({ phase: "success", message: t("finalReviewVisual.audioApproveSuccess") });
      notify({
        id: `final-review-audio-${sourceVideoId}`,
        message: t("finalReviewVisual.audioApproveSuccess"),
        tone: "success"
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("finalReviewVisual.audioApproveFailed");
      setOcrStatus({ phase: "error", message });
      setError(message);
    } finally {
      setAudioApproveBusy(false);
    }
  }

  useEffect(() => {
    if (loading || ocrResumeAttemptedRef.current) return;
    ocrResumeAttemptedRef.current = true;
    void resumeActiveOcrJob();
  }, [loading, sourceVideoId]);

  useEffect(() => {
    if (loading || renderResumeAttemptedRef.current) return;
    renderResumeAttemptedRef.current = true;
    void resumeActiveRenderJob();
  }, [loading, sourceVideoId]);

  useEffect(() => {
    const authority = ocrSummary?.residual_authority_sha256;
    if (
      loading ||
      ocrBusy ||
      ocrSummary?.workflow_stage !== "WAITING_RESIDUAL_TRIAGE" ||
      !authority ||
      ocrSummary.residual_translation_status === "READY"
    ) {
      return;
    }
    const attemptKey = `${sourceVideoId}:${authority}`;
    if (residualTranslationAttemptedRef.current === attemptKey) return;
    residualTranslationAttemptedRef.current = attemptKey;
    void handleRequestResidualTranslationSuggestions();
  }, [
    loading,
    ocrBusy,
    sourceVideoId,
    ocrSummary?.workflow_stage,
    ocrSummary?.residual_authority_sha256,
    ocrSummary?.residual_translation_status
  ]);

  if (loading) {
    return (
      <main className="final-review final-review--prep">
        <AsyncContentBoundary status="loading" skeleton={<FinalReviewLoadingState />} loadingLabel={t("finalReviewStates.loading")}>
          {null}
        </AsyncContentBoundary>
      </main>
    );
  }
  if (error && !render && !ocrSummary) return <FinalReviewErrorState message={error} onRetry={loadData} />;
  if (!render) {
    const prepFocus = resolveFinalReviewPrepFocus(ocrSummary);
    const ocrSessionOpen = ocrBusy || ocrWatchPaused;
    const visualCard = (
      <FinalReviewVisualCheckpoint
        sourceVideoId={sourceVideoId}
        summary={ocrSummary}
        analyzeBusy={ocrBusy}
        approveBusy={approveBusy}
        audioApproveBusy={audioApproveBusy}
        residualTranslationBusy={residualTranslationBusy}
        status={ocrStatus}
        presentation="prep"
        prepFocus={prepFocus}
        onAnalyze={() => void asyncAction.run("analyze-ocr", () => handleAnalyzeOcr(false))}
        onReanalyze={() => void asyncAction.run("reanalyze-ocr", () => handleAnalyzeOcr(true))}
        onApproveDialogueTranslation={() =>
          void asyncAction.run("approve-dialogue-translation", handleApproveDialogueTranslation)
        }
        onApprove={() => void asyncAction.run("approve-visual", handleApproveVisual)}
        onApproveAudio={() => void asyncAction.run("approve-audio", handleApproveAudio)}
        onSubmitOcrReview={(decisions) =>
          void asyncAction.run("submit-ocr-review", () => handleSubmitOcrReview(decisions))
        }
        onSubmitTranslationReview={(translations) =>
          void asyncAction.run("submit-translation-review", () =>
            handleSubmitTranslationReview(translations)
          )
        }
        onSubmitResidualTriage={(suggestions) =>
          void asyncAction.run("submit-residual-triage", () => handleSubmitResidualTriage(suggestions))
        }
        onApproveResidual={(proposalSha256) =>
          void asyncAction.run("approve-residual", () => handleApproveResidual(proposalSha256))
        }
        onRetryResidualTranslation={() => {
          residualTranslationAttemptedRef.current = null;
          void asyncAction.run(
            "suggest-residual-translation",
            handleRequestResidualTranslationSuggestions
          );
        }}
        onDismissStatus={() => setOcrStatus(null)}
        onPause={ocrJobId && !ocrWatchPaused ? () => pauseOcrWatch() : undefined}
        onResume={ocrJobId && ocrWatchPaused ? () => void resumeOcrWatch() : undefined}
        onCancel={ocrJobId ? () => void cancelOcrJob() : undefined}
        watchPaused={ocrWatchPaused}
        pausePending={ocrPausePending}
        cancelPending={ocrCancelPending}
      />
    );
    const emptyCard = (
      <FinalReviewEmptyState
        sourceVideoId={sourceVideoId}
        actionBusy={actionBusy || ocrSessionOpen || approveBusy}
        startRenderPending={asyncAction.isPending("start-render") || renderBusy}
        prepFocus={prepFocus}
        presentation={prepFocus === "render" ? "bar" : "side"}
        actionStatus={actionStatus}
        hideTranscriptLink={isFinalReviewDialogueTranslationApprovalPending(ocrSummary)}
        onStartRender={() => void asyncAction.run("start-render", handleStartFirstRender)}
        onDismissStatus={() => setActionStatus(null)}
        onPause={renderJobId && !renderWatchPaused ? () => pauseRenderWatch() : undefined}
        onResume={renderJobId && renderWatchPaused ? () => void resumeRenderWatch() : undefined}
        onCancel={renderJobId ? () => void cancelRenderJob() : undefined}
        watchPaused={renderWatchPaused}
        pausePending={renderPausePending}
        cancelPending={renderCancelPending}
      />
    );
    return (
      <main className="final-review final-review--prep">
        <FinalReviewPrepBriefing
          sourceVideoId={sourceVideoId}
          manifest={manifest}
          ocrSummary={ocrSummary}
          ocrBusy={ocrBusy}
          startRenderPending={asyncAction.isPending("start-render") || renderBusy}
          prepFocus={prepFocus}
        />
        {error ? <div className="inline-error">{error}</div> : null}
        <section className="final-review-layout final-review-layout--prep">
          <FinalReviewPrepJourney
            prepFocus={prepFocus}
            ocrSummary={ocrSummary}
            ocrBusy={ocrBusy}
            ocrWatchPaused={ocrWatchPaused}
            approveBusy={approveBusy}
            actionBusy={actionBusy || ocrSessionOpen || approveBusy}
            startRenderPending={asyncAction.isPending("start-render") || renderBusy}
            renderWatchPaused={renderWatchPaused}
            ocrProgressPercent={ocrProgressPercent}
            renderProgressPercent={renderProgressPercent}
            onAnalyze={handleOcrJourneyAction}
            onStartRender={() => void asyncAction.run("start-render", handleStartFirstRender)}
          />
          <div className={`final-review-prep-stage is-focus-${prepFocus}`}>
            {prepFocus === "ocr" ? (
              <>
                <div className="final-review-prep-col is-hero">{visualCard}</div>
                <div className="final-review-prep-col is-side">{emptyCard}</div>
              </>
            ) : (
              <>
                <div className="final-review-prep-col final-review-prep-col--span">{emptyCard}</div>
                <div className="final-review-prep-col final-review-prep-col--span is-hero">{visualCard}</div>
              </>
            )}
          </div>
        </section>
      </main>
    );
  }

  const tabs: { id: RailTab; label: string; icon: FinalReviewRailIconKind }[] = [
    { id: "review", label: t("finalReviewTabs.review"), icon: "review" },
    { id: "visual", label: t("finalReviewTabs.visual"), icon: "visual" },
    { id: "risk", label: t("finalReviewTabs.risk"), icon: "risk" },
    { id: "info", label: t("finalReviewTabs.info"), icon: "info" },
    { id: "handoff", label: "Export", icon: "info" }
  ];

  return (
    <main className={`final-review final-review--workspace${railTab === "review" ? "" : " final-review--focus-rail"}`}>
      <div className="fr-review-chrome fr-review-ribbon">
        <FinalReviewHeader
          render={render}
          manifest={manifest}
          actionBusy={actionBusy}
          rerenderPending={renderBusy || asyncAction.isPending("rerender")}
          onRerender={() => void asyncAction.run("rerender", handleRerender)}
        />
        {readiness ? <FinalReviewReadinessStrip readiness={readiness} /> : null}
      </div>
      {error ? <div className="inline-error fr-inline-error">{error}</div> : null}
      {actionStatus && railTab !== "review" ? (
        <div className="fr-action-status-slot">
          <FinalReviewActionStatus
            phase={actionStatus.phase}
            message={actionStatus.message}
            onDismiss={() => setActionStatus(null)}
            onPause={renderJobId && !renderWatchPaused ? () => pauseRenderWatch() : undefined}
            onResume={renderJobId && renderWatchPaused ? () => void resumeRenderWatch() : undefined}
            onCancel={renderJobId ? () => void cancelRenderJob() : undefined}
            watchPaused={renderWatchPaused}
            pausePending={renderPausePending}
            cancelPending={renderCancelPending}
          />
        </div>
      ) : null}
      <section className="fr-workspace">
        <FinalCompareViewer
          mode={compareMode}
          finalAssetId={finalAssetId}
          originalAssetId={originalAssetId}
          compareDiff={compareDiff}
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
                <FinalReviewRailIcon kind={tab.icon} />
                <span>{tab.label}</span>
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
                sourceVideoId={sourceVideoId}
                summary={ocrSummary}
                analyzeBusy={ocrBusy}
                approveBusy={approveBusy}
                audioApproveBusy={audioApproveBusy}
                residualTranslationBusy={residualTranslationBusy}
                status={ocrStatus}
                  onAnalyze={() => void asyncAction.run("analyze-ocr", () => handleAnalyzeOcr(false))}
                  onReanalyze={() => void asyncAction.run("reanalyze-ocr", () => handleAnalyzeOcr(true))}
                  onApproveDialogueTranslation={() =>
                    void asyncAction.run("approve-dialogue-translation", handleApproveDialogueTranslation)
                  }
                onApprove={() => void asyncAction.run("approve-visual", handleApproveVisual)}
                onApproveAudio={() => void asyncAction.run("approve-audio", handleApproveAudio)}
                onSubmitOcrReview={(decisions) =>
                  void asyncAction.run("submit-ocr-review", () => handleSubmitOcrReview(decisions))
                }
                onSubmitTranslationReview={(translations) =>
                  void asyncAction.run("submit-translation-review", () =>
                    handleSubmitTranslationReview(translations)
                  )
                }
                onSubmitResidualTriage={(suggestions) =>
                  void asyncAction.run("submit-residual-triage", () => handleSubmitResidualTriage(suggestions))
                }
                onApproveResidual={(proposalSha256) =>
                  void asyncAction.run("approve-residual", () => handleApproveResidual(proposalSha256))
                }
                onRetryResidualTranslation={() => {
                  residualTranslationAttemptedRef.current = null;
                  void asyncAction.run(
                    "suggest-residual-translation",
                    handleRequestResidualTranslationSuggestions
                  );
                }}
                onDismissStatus={() => setOcrStatus(null)}
                onPause={ocrJobId && !ocrWatchPaused ? () => pauseOcrWatch() : undefined}
                onResume={ocrJobId && ocrWatchPaused ? () => void resumeOcrWatch() : undefined}
                onCancel={ocrJobId ? () => void cancelOcrJob() : undefined}
                watchPaused={ocrWatchPaused}
                pausePending={ocrPausePending}
                cancelPending={ocrCancelPending}
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
            {railTab === "handoff" ? (
              <QualityHandoffPanel
                sourceVideoId={sourceVideoId}
                publishReady={Boolean(render && isPublishReady(render))}
                defaultTitle={manifest?.source_video?.caption || ""}
                defaultCaption={manifest?.source_video?.caption || ""}
              />
            ) : null}
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
          actionStatus={railTab === "review" ? actionStatus : null}
          onApprove={() => void asyncAction.run("approve-render", handleApprove)}
          onPublishReady={() => void asyncAction.run("publish-ready", handlePublishReady)}
          onDismissStatus={() => setActionStatus(null)}
          onPause={renderJobId && !renderWatchPaused ? () => pauseRenderWatch() : undefined}
          onResume={renderJobId && renderWatchPaused ? () => void resumeRenderWatch() : undefined}
          onCancel={renderJobId ? () => void cancelRenderJob() : undefined}
          watchPaused={renderWatchPaused}
          pausePending={renderPausePending}
          cancelPending={renderCancelPending}
        />
      ) : null}
    </main>
  );
  }
);
