"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { useNotice } from "../shared/NoticeCenter";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { AsyncButton } from "../shared/AsyncButton";
import {
  approveTranslationDraft,
  createAudioAnalysis,
  createTtsJob,
  cancelJob,
  fetchAudioAnalysisSummary,
  fetchJob,
  fetchJobs,
  fetchTranscript,
  fetchTranslationDraft,
  fetchTtsSummary,
  mergeTranscriptSegments,
  approveSourceTranscript,
  rerunTranslationDraft,
  saveTranscriptDraft,
  splitTranscriptSegment
} from "../../lib/api";
import { findJoinedTtsAssetId, indexTtsClipFitsByTranslationId, type TtsSummaryResponse } from "../../types/tts";
import {
  buildSavePayload,
  buildTranscriptEditorState,
  hasUnsavedChanges,
  mergeAdjacentSegments,
  resetSegment,
  selectSegment,
  updateSegment,
  validateTranscriptSegments
} from "../../lib/transcriptEditorState";
import {
  fingerprintVietnameseDraft,
  isSourceTranscriptReadyForTranslation,
  ttsViFingerprintStorageKey
} from "../../lib/transcriptEditorPipeline";
import {
  pickActiveTranscriptJob,
  transcriptJobKindFromType,
  type TranscriptActiveJobKind
} from "../../lib/transcriptEditorJobReattach";
import {
  pollAnalyzeJobUntilSettled,
  type AnalyzeJobPollResult
} from "../../lib/transcriptEditorReanalyze";
import type { AudioAnalysisSummaryResponse, EditableSegment, TranscriptEditorState, TranslationDraftListResponse, TranslationPreset } from "../../types/transcript-editor";
import { TranscriptActionBar } from "./TranscriptActionBar";
import { TranscriptBeatRail } from "./TranscriptBeatRail";
import { TranscriptEditorHeader } from "./TranscriptEditorHeader";
import { TranscriptFocusEditor } from "./TranscriptFocusEditor";
import { TranscriptJobBusyBanner } from "./TranscriptJobBusyBanner";
import { TranscriptInlineNotice, TRANSCRIPT_CANCELLED_NOTICE_AUTO_DISMISS_MS, TRANSCRIPT_SUCCESS_NOTICE_AUTO_DISMISS_MS } from "./TranscriptInlineNotice";
import { TranscriptMediaPreview } from "./TranscriptMediaPreview";
import { TranscriptTtsTemporalReport } from "./TranscriptTtsTemporalReport";
import { TranscriptSourceReviewNotice } from "./TranscriptSourceReviewNotice";
import {
  isNoDialogueAnalysisSummary,
  TranscriptEmptyState,
  TranscriptErrorState,
  TranscriptLoadingState,
  TranscriptNoDialogueState
} from "./TranscriptStates";
import { UnsavedChangesGuard } from "./UnsavedChangesGuard";

export type TranscriptEditorPageHandle = {
  refresh: () => Promise<void>;
};

export const TranscriptEditorPage = forwardRef<TranscriptEditorPageHandle, { sourceVideoId: string }>(
  function TranscriptEditorPage({ sourceVideoId }, ref) {
  const t = useT();
  const asyncAction = useAsyncAction();
  const { notify } = useNotice();
  const [state, setState] = useState<TranscriptEditorState | null>(null);
  const [savedState, setSavedState] = useState<TranscriptEditorState | null>(null);
  const [summary, setSummary] = useState<AudioAnalysisSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [synthesizingTts, setSynthesizingTts] = useState(false);
  const [approvingSource, setApprovingSource] = useState(false);
  const [joinedTtsAssetId, setJoinedTtsAssetId] = useState<string | null>(null);
  const [ttsSourceFingerprint, setTtsSourceFingerprint] = useState<string | null>(null);
  const [ttsSummary, setTtsSummary] = useState<TtsSummaryResponse | null>(null);
  const [translationRecipeVersion, setTranslationRecipeVersion] = useState<string | null>(null);
  const [translationQualityContract, setTranslationQualityContract] = useState<TranslationDraftListResponse["quality_contract"]>(null);
  const [analyzeJobId, setAnalyzeJobId] = useState<string | null>(null);
  const [jobProgressPercent, setJobProgressPercent] = useState<number | null>(null);
  const [cancellingJob, setCancellingJob] = useState(false);
  const cancelRequestedRef = useRef(false);
  const resumeAttemptedRef = useRef(false);
  const jobBusyRef = useRef(false);
  const ttsPendingFingerprintRef = useRef<string | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [cancelledMessage, setCancelledMessage] = useState<string | null>(null);
  const [playRequestId, setPlayRequestId] = useState(0);
  const [pauseRequestId, setPauseRequestId] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const clearDownstreamAuthorityUi = useCallback(() => {
    setTranslationRecipeVersion(null);
    setTranslationQualityContract(null);
    setTtsSummary(null);
    setJoinedTtsAssetId(null);
    setTtsSourceFingerprint(null);
    ttsPendingFingerprintRef.current = null;
    try {
      sessionStorage.removeItem(ttsViFingerprintStorageKey(sourceVideoId));
    } catch {
      // Best effort; server-side current authority remains the source of truth.
    }
  }, [sourceVideoId]);

  const loadData = useCallback(async (mode: "initial" | "refresh" = "initial") => {
    if (mode === "initial") setLoading(true);
    setError(null);
    try {
      const [transcript, translation, nextSummary] = await Promise.all([
        fetchTranscript(sourceVideoId),
        fetchTranslationDraft(sourceVideoId),
        fetchAudioAnalysisSummary(sourceVideoId)
      ]);
      const rawState = buildTranscriptEditorState(transcript, translation);
      const sourceTranscriptApproved = isSourceTranscriptReadyForTranslation(
        rawState,
        nextSummary.dialogue_phase
      );
      const translationMatchesCurrentTranscript = translation.segments.every((segment) =>
        transcript.segments.some((source) => source.id === segment.transcript_segment_id)
      );
      const downstreamAuthorityValid = sourceTranscriptApproved && translationMatchesCurrentTranscript;
      // Never paint a Translation/TTS projection that belongs to an older ASR
      // run.  The backend invalidates it transactionally; this guard protects
      // reconnects against a stale compatibility response as well.
      const effectiveTranslation = downstreamAuthorityValid
        ? translation
        : { ...translation, segments: [], recipe_version: null, quality_contract: null };
      const nextState = buildTranscriptEditorState(transcript, effectiveTranslation);
      setState(nextState);
      setSavedState(nextState);
      setSummary(nextSummary);
      if (!downstreamAuthorityValid || effectiveTranslation.segments.length === 0) {
        clearDownstreamAuthorityUi();
      } else {
        setTranslationRecipeVersion(effectiveTranslation.recipe_version ?? null);
        setTranslationQualityContract(effectiveTranslation.quality_contract ?? null);
        try {
          const nextTtsSummary = await fetchTtsSummary(sourceVideoId);
          setTtsSummary(nextTtsSummary);
          setJoinedTtsAssetId(findJoinedTtsAssetId(nextTtsSummary));
        } catch {
          setTtsSummary(null);
          setJoinedTtsAssetId(null);
        }
        try {
          const storedFp = sessionStorage.getItem(ttsViFingerprintStorageKey(sourceVideoId));
          setTtsSourceFingerprint(storedFp);
        } catch {
          setTtsSourceFingerprint(null);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.loadError"));
    } finally {
      if (mode === "initial") setLoading(false);
    }
  }, [clearDownstreamAuthorityUi, sourceVideoId, t]);

  useImperativeHandle(
    ref,
    () => ({
      refresh: async () => {
        if (state && hasUnsavedChanges(state) && !window.confirm(t("transcriptEditorPage.refreshUnsavedConfirm"))) {
          return;
        }
        await loadData("refresh");
      }
    }),
    [loadData, state, t]
  );

  useEffect(() => {
    void loadData("initial");
  }, [loadData]);

  useEffect(() => {
    resumeAttemptedRef.current = false;
  }, [sourceVideoId]);

  const warnings = useMemo(() => validateTranscriptSegments(state?.segments ?? []), [state]);
  const clipFitsByTranslationId = useMemo(
    () => indexTtsClipFitsByTranslationId(ttsSummary),
    [ttsSummary]
  );
  const selectedSegment = useMemo(
    () => state?.segments.find((segment) => segment.localId === state.selectedSegmentId) ?? null,
    [state]
  );
  const selectedWarnings = selectedSegment
    ? warnings.filter((warning) => warning.segmentId === selectedSegment.localId)
    : [];
  const dirtyCount = state?.segments.filter((segment) => segment.isDirty).length ?? 0;
  const blockingWarnings = warnings.filter((warning) =>
    ["negative_timing", "invalid_timing", "overlapping_timing"].includes(warning.code)
  );
  const jobBusyKind = synthesizingTts
    ? ("tts" as const)
    : translating
      ? ("translate" as const)
      : reanalyzing
        ? ("reanalyze" as const)
        : null;
  const jobBusy = jobBusyKind !== null;
  jobBusyRef.current = jobBusy;

  async function saveDraft() {
    if (!state) return;
    const payload = buildSavePayload(state);
    if (payload.segments.length === 0) return;
    if (blockingWarnings.length > 0) {
      setError(t("transcriptEditorPage.fixTimingErrors"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveTranscriptDraft(sourceVideoId, payload);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.saveError"));
    } finally {
      setSaving(false);
    }
  }

  function discardChanges() {
    if (savedState) setState(savedState);
  }

  async function mergeSegment(segmentId: string, direction: "previous" | "next") {
    if (!state) return;
    const index = state.segments.findIndex((segment) => segment.localId === segmentId);
    const otherIndex = direction === "previous" ? index - 1 : index + 1;
    if (index < 0 || otherIndex < 0 || otherIndex >= state.segments.length) return;
    if (hasUnsavedChanges(state) && !window.confirm(t("transcriptEditorPage.mergeConfirm"))) {
      return;
    }
    const left = state.segments[Math.min(index, otherIndex)];
    const right = state.segments[Math.max(index, otherIndex)];
    setState(mergeAdjacentSegments(state, segmentId, direction));
    try {
      await mergeTranscriptSegments(sourceVideoId, left.transcriptId, right.transcriptId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.mergeError"));
      await loadData();
    }
  }

  async function splitSegment(segment: EditableSegment) {
    const splitMs = Math.floor((segment.startMs + segment.endMs) / 2);
    const [leftSource, rightSource] = splitText(segment.sourceText);
    const [leftTranslated, rightTranslated] = splitText(segment.translatedText);
    if (!window.confirm(t("transcriptEditorPage.splitConfirm"))) return;
    setSaving(true);
    try {
      await splitTranscriptSegment(sourceVideoId, {
        transcript_segment_id: segment.transcriptId,
        split_ms: splitMs,
        left_source_text: leftSource,
        right_source_text: rightSource,
        left_translated_text: leftTranslated,
        right_translated_text: rightTranslated
      });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.splitError"));
    } finally {
      setSaving(false);
    }
  }

  async function pollJob(jobId: string) {
    return pollAnalyzeJobUntilSettled({
      fetchStatus: async () => {
        const job = await fetchJob(jobId);
        return {
          status: job.status,
          progress_percent: job.progress_percent,
          error_message: job.error_message,
          error_code: job.error_code
        };
      },
      onSnapshot: (snapshot) => {
        if (typeof snapshot.progress_percent === "number") {
          setJobProgressPercent(Math.max(0, Math.min(100, Math.round(snapshot.progress_percent))));
        }
      },
      shouldStop: () => cancelRequestedRef.current
    });
  }

  function beginJobRun(existingJobId?: string | null, existingProgress?: number | null) {
    setError(null);
    setSuccessMessage(null);
    setCancelledMessage(null);
    setAnalyzeJobId(existingJobId ?? null);
    setJobProgressPercent(
      typeof existingProgress === "number" ? Math.max(0, Math.min(100, Math.round(existingProgress))) : 0
    );
    setCancellingJob(false);
    cancelRequestedRef.current = false;
  }

  function endJobRun() {
    setAnalyzeJobId(null);
    setJobProgressPercent(null);
    setCancellingJob(false);
    cancelRequestedRef.current = false;
  }

  function setBusyForKind(kind: TranscriptActiveJobKind, busy: boolean) {
    if (kind === "tts") setSynthesizingTts(busy);
    else if (kind === "translate") setTranslating(busy);
    else setReanalyzing(busy);
  }

  async function applySettledJob(kind: TranscriptActiveJobKind, settled: AnalyzeJobPollResult) {
    if (settled.outcome === "success") {
      setError(null);
      if (kind === "tts") {
        const nextTtsSummary = await fetchTtsSummary(sourceVideoId);
        setTtsSummary(nextTtsSummary);
        setJoinedTtsAssetId(findJoinedTtsAssetId(nextTtsSummary));
        const fp =
          ttsPendingFingerprintRef.current ??
          (stateRef.current ? fingerprintVietnameseDraft(stateRef.current.segments) : null);
        ttsPendingFingerprintRef.current = null;
        if (fp) {
          setTtsSourceFingerprint(fp);
          try {
            sessionStorage.setItem(ttsViFingerprintStorageKey(sourceVideoId), fp);
          } catch {
            // Best-effort freshness marker; UI still works without persistence.
          }
        }
        setSuccessMessage(t("transcriptEditorPage.ttsSuccess"));
        notify({ id: `transcript-tts-${sourceVideoId}`, message: t("transcriptEditorPage.ttsSuccess"), tone: "success" });
        return;
      }
      if (kind === "translate") {
        const [transcript, translation, nextSummary] = await Promise.all([
          fetchTranscript(sourceVideoId),
          fetchTranslationDraft(sourceVideoId),
          fetchAudioAnalysisSummary(sourceVideoId)
        ]);
        const nextState = buildTranscriptEditorState(transcript, translation);
        setState(nextState);
        setSavedState(nextState);
        setSummary(nextSummary);
        const filled = nextState.segments.filter((segment) => segment.translatedText.trim()).length;
        if (filled === 0) {
          setError(t("transcriptEditorPage.translateEmptyAfterJob"));
        } else if (filled < nextState.segments.length) {
          setError(
            `${t("transcriptEditorPage.translatePartialAfterJob")} (${filled}/${nextState.segments.length})`
          );
        } else {
          setSuccessMessage(t("transcriptEditorPage.translateSuccess"));
          notify({ id: `transcript-translate-${sourceVideoId}`, message: t("transcriptEditorPage.translateSuccess"), tone: "success" });
        }
        return;
      }
      clearDownstreamAuthorityUi();
      await loadData();
      setSuccessMessage(t("transcriptEditorPage.reanalyzeSuccess"));
      notify({ id: `transcript-reanalyze-${sourceVideoId}`, message: t("transcriptEditorPage.reanalyzeSuccess"), tone: "success" });
      return;
    }
    if (settled.outcome === "cancelled") {
      setCancelledMessage(t("transcriptEditorPage.jobCancelled"));
      notify({ id: `transcript-cancel-${sourceVideoId}`, message: t("transcriptEditorPage.jobCancelled"), tone: "info" });
      return;
    }
    if (settled.outcome === "failed") {
      const prefix =
        kind === "tts"
          ? t("transcriptEditorPage.ttsFailed")
          : kind === "translate"
            ? t("transcriptEditorPage.translateFailed")
            : t("transcriptEditorPage.reanalyzeFailed");
      setError(`${prefix}: ${settled.errorMessage ?? settled.status}`);
      return;
    }
    setError(
      kind === "tts"
        ? t("transcriptEditorPage.ttsTimeout")
        : kind === "translate"
          ? t("transcriptEditorPage.translateTimeout")
          : t("transcriptEditorPage.reanalyzeTimeout")
    );
  }

  async function trackJob(kind: TranscriptActiveJobKind, jobId: string, progressPercent?: number | null) {
    setBusyForKind(kind, true);
    beginJobRun(jobId, progressPercent);
    try {
      const settled = await pollJob(jobId);
      await applySettledJob(kind, settled);
    } catch (err) {
      const fallback =
        kind === "tts"
          ? t("transcriptEditorPage.ttsError")
          : kind === "translate"
            ? t("transcriptEditorPage.translateError")
            : t("transcriptEditorPage.reanalyzeError");
      setError(err instanceof Error ? err.message : fallback);
    } finally {
      setBusyForKind(kind, false);
      endJobRun();
    }
  }

  async function resumeActiveTranscriptJob() {
    if (jobBusyRef.current) return;
    try {
      const listed = await fetchJobs(undefined, { sourceVideoId, limit: 30 });
      const active = pickActiveTranscriptJob(listed.jobs);
      if (!active) return;
      const kind = transcriptJobKindFromType(active.job_type);
      if (!kind || jobBusyRef.current) return;
      await trackJob(kind, active.id, active.progress_percent);
    } catch {
      // Re-attach is best-effort; page remains usable without the banner.
    }
  }

  async function cancelRunningJob() {
    if (!analyzeJobId || cancellingJob) return;
    setCancellingJob(true);
    cancelRequestedRef.current = true;
    try {
      await cancelJob(analyzeJobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.jobCancelError"));
      setCancellingJob(false);
      cancelRequestedRef.current = false;
    }
  }

  async function translateLiteral(preset: TranslationPreset) {
    if (!summary || !state || !isSourceTranscriptReadyForTranslation(state, summary.dialogue_phase)) {
      setError(t("transcriptEditorPage.translateRequiresSourceApproval"));
      return;
    }
    if (state && hasUnsavedChanges(state) && !window.confirm(t("transcriptEditorPage.translateUnsavedConfirm"))) {
      return;
    }
    try {
      const created = await rerunTranslationDraft(sourceVideoId, preset);
      await trackJob("translate", created.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.translateError"));
    }
  }

  async function reanalyzeAudio(preset: TranslationPreset) {
    if (state && hasUnsavedChanges(state) && !window.confirm(t("transcriptEditorPage.reanalyzeUnsavedConfirm"))) {
      return;
    }
    try {
      const created = await createAudioAnalysis(sourceVideoId, preset, true, true);
      await trackJob("reanalyze", created.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.reanalyzeError"));
    }
  }

  async function approveCurrentSourceTranscript() {
    if (!state || !summary) return;
    if (blockingWarnings.length > 0) {
      setError(t("transcriptEditorPage.fixTimingErrors"));
      return;
    }
    setApprovingSource(true);
    setError(null);
    try {
      if (hasUnsavedChanges(state)) {
        const payload = buildSavePayload(state);
        if (payload.segments.length > 0) await saveTranscriptDraft(sourceVideoId, payload);
      }
      await approveSourceTranscript(sourceVideoId);
      await loadData("refresh");
      setSuccessMessage(t("transcriptEditorPage.sourceApprovalSuccess"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.sourceApprovalError"));
    } finally {
      setApprovingSource(false);
    }
  }

  async function generateTts() {
    if (!state) return;
    const filled = state.segments.filter((segment) => segment.translatedText.trim()).length;
    if (filled === 0) {
      setError(t("transcriptEditorPage.ttsEmptyVi"));
      return;
    }
    const hasDirtyDraft = hasUnsavedChanges(state);
    const forceRefresh = Boolean(joinedTtsAssetId);
    // Generate TTS is idempotent and dirty rows are persisted immediately below
    // before approval/job creation, so a blocking native dialog is unnecessary.
    ttsPendingFingerprintRef.current = fingerprintVietnameseDraft(state.segments);
    setError(null);
    setSuccessMessage(null);
    try {
      if (hasDirtyDraft) {
        const payload = buildSavePayload(state);
        if (payload.segments.length > 0) {
          await saveTranscriptDraft(sourceVideoId, payload);
        }
      }
      const approval = await approveTranslationDraft(sourceVideoId);
      const jobId = approval.job_id;
      // Approval can resume the first auto-pipeline TTS job. An explicit
      // Regenerate command must always create a fresh force_refresh job instead
      // of reattaching a historical/auto job returned by the checkpoint.
      if (jobId && !forceRefresh) {
        await trackJob("tts", jobId);
      } else {
        const created = await createTtsJob(sourceVideoId, { forceRefresh });
        await trackJob("tts", created.job_id);
      }
    } catch (err) {
      ttsPendingFingerprintRef.current = null;
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.ttsError"));
    }
  }

  useEffect(() => {
    if (loading || !state || state.segments.length === 0 || resumeAttemptedRef.current) return;
    resumeAttemptedRef.current = true;
    void resumeActiveTranscriptJob();
  }, [loading, state, sourceVideoId]);

  if (loading) {
    return (
      <main className="transcript-editor">
        <AsyncContentBoundary status="loading" skeleton={<TranscriptLoadingState />} loadingLabel={t("transcriptEditorStates.loading")}>
          {null}
        </AsyncContentBoundary>
      </main>
    );
  }
  if (error && !state) return <TranscriptErrorState message={error} onRetry={loadData} />;
  if (!state || state.segments.length === 0) {
    if (isNoDialogueAnalysisSummary(summary)) {
      return <TranscriptNoDialogueState />;
    }
    return <TranscriptEmptyState />;
  }

  const sourceTranscriptApproved = isSourceTranscriptReadyForTranslation(state, summary?.dialogue_phase);
  const explicitlyFlaggedSourceSegments = state.segments.filter((segment) =>
    segment.difficultyFlags.some((flag) =>
      ["needs_operator_review", "likely_mistranscribed", "asr_low_confidence"].includes(flag)
    )
  );
  const sourceReviewSegments =
    explicitlyFlaggedSourceSegments.length > 0
      ? explicitlyFlaggedSourceSegments
      : state.segments.filter((segment) => segment.status !== "APPROVED");

  return (
    <main className="transcript-editor">
      <UnsavedChangesGuard enabled={dirtyCount > 0 || jobBusy} />
      <TranscriptEditorHeader
        state={state}
        dirtyCount={dirtyCount}
        blockingCount={blockingWarnings.length}
        saving={saving || asyncAction.isPending("save")}
        reanalyzing={reanalyzing || asyncAction.isPending("reanalyze")}
        translating={translating || asyncAction.isPending("translate")}
        synthesizingTts={synthesizingTts || asyncAction.isPending("tts")}
        approvingSource={approvingSource}
        sourceTranscriptApproved={sourceTranscriptApproved}
        hasJoinedTts={Boolean(joinedTtsAssetId)}
        ttsSourceFingerprint={ttsSourceFingerprint}
        audioRecipeVersion={summary?.audio_recipe_version}
        translationRecipeVersion={translationRecipeVersion}
        translationQualityContract={translationQualityContract}
        onSave={() => void asyncAction.run("save", saveDraft)}
        onDiscard={discardChanges}
        onTranslateLiteral={(preset) => void asyncAction.run("translate", () => translateLiteral(preset))}
        onReanalyze={(preset) => void asyncAction.run("reanalyze", () => reanalyzeAudio(preset))}
        onGenerateTts={() => void asyncAction.run("tts", generateTts)}
      />
      {!sourceTranscriptApproved ? (
        <TranscriptSourceReviewNotice
          reviewSegmentIndexes={sourceReviewSegments.map((segment) => segment.segmentIndex)}
          approving={approvingSource || asyncAction.isPending("approve-source")}
          disabled={jobBusy || dirtyCount > 0 || blockingWarnings.length > 0}
          onApprove={() => void asyncAction.run("approve-source", approveCurrentSourceTranscript)}
        />
      ) : null}
      {jobBusyKind ? (
        <div className="transcript-job-strip">
          <TranscriptJobBusyBanner
            kind={jobBusyKind}
            jobId={analyzeJobId}
            progressPercent={jobProgressPercent}
            cancelling={cancellingJob}
            onCancel={() => void asyncAction.run("cancel-job", cancelRunningJob)}
          />
        </div>
      ) : null}
      {successMessage ? (
        <TranscriptInlineNotice
          tone="success"
          onDismiss={() => setSuccessMessage(null)}
          autoDismissMs={TRANSCRIPT_SUCCESS_NOTICE_AUTO_DISMISS_MS}
        >
          {successMessage}
        </TranscriptInlineNotice>
      ) : null}
      {cancelledMessage ? (
        <TranscriptInlineNotice
          tone="cancelled"
          onDismiss={() => setCancelledMessage(null)}
          autoDismissMs={TRANSCRIPT_CANCELLED_NOTICE_AUTO_DISMISS_MS}
        >
          {cancelledMessage}
        </TranscriptInlineNotice>
      ) : null}
      {error ? <TranscriptInlineNotice tone="error">{error}</TranscriptInlineNotice> : null}
      <TranscriptTtsTemporalReport summary={ttsSummary} />
      <section
        className={`transcript-bench${jobBusy ? " is-job-busy" : ""}`}
        aria-busy={jobBusy}
      >
        <aside className="transcript-bench__side">
          <TranscriptMediaPreview
            summary={summary}
            selectedSegment={selectedSegment}
            playRequestId={playRequestId}
            pauseRequestId={pauseRequestId}
            joinedTtsAssetId={joinedTtsAssetId}
            onPlayingChange={setIsPlaying}
          />
          <TranscriptBeatRail
            segments={state.segments}
            selectedSegmentId={state.selectedSegmentId}
            clipFitsByTranslationId={clipFitsByTranslationId}
            onSelect={(segmentId) => setState((current) => (current ? selectSegment(current, segmentId) : current))}
          />
        </aside>
        <div className="transcript-bench__main">
          {selectedSegment ? (
            <TranscriptFocusEditor
              segment={selectedSegment}
              sourceVideoId={state.sourceVideoId}
              analysisVersion={state.analysisVersion}
              translationPreset={state.translationPreset}
              allSegments={state.segments}
              warnings={selectedWarnings}
              canMergePrevious={state.segments.findIndex((s) => s.localId === selectedSegment.localId) > 0}
              canMergeNext={
                state.segments.findIndex((s) => s.localId === selectedSegment.localId) < state.segments.length - 1
              }
              ttsClipFit={
                selectedSegment.translationId
                  ? clipFitsByTranslationId.get(selectedSegment.translationId) ?? null
                  : null
              }
              onChange={(patch) =>
                setState((current) =>
                  current ? updateSegment(current, selectedSegment.localId, patch) : current
                )
              }
              onPlay={() => {
                if (isPlaying) {
                  setPauseRequestId((current) => current + 1);
                  return;
                }
                setState((current) => (current ? selectSegment(current, selectedSegment.localId) : current));
                setPlayRequestId((current) => current + 1);
              }}
              isPlaying={isPlaying}
              onMergePrevious={() => void mergeSegment(selectedSegment.localId, "previous")}
              onMergeNext={() => void mergeSegment(selectedSegment.localId, "next")}
              onSplit={() => void splitSegment(selectedSegment)}
              onReset={() => setState((current) => (current ? resetSegment(current, selectedSegment.localId) : current))}
            />
          ) : (
            <p className="transcript-bench__empty">{t("transcriptEditorBench.noBeatSelected")}</p>
          )}
        </div>
      </section>
      <TranscriptActionBar
        dirtyCount={dirtyCount}
        warningCount={warnings.length}
        blockingCount={blockingWarnings.length}
        saving={saving || asyncAction.isPending("save")}
        jobBusy={jobBusy}
        onSave={() => void asyncAction.run("save", saveDraft)}
        onDiscard={discardChanges}
      />
    </main>
  );
});

function splitText(text: string): [string, string] {
  const trimmed = text.trim();
  if (!trimmed) return ["", ""];
  const midpoint = Math.floor(trimmed.length / 2);
  const splitAt = trimmed.indexOf(" ", midpoint);
  const index = splitAt > 0 ? splitAt : midpoint;
  return [trimmed.slice(0, index).trim(), trimmed.slice(index).trim()];
}
