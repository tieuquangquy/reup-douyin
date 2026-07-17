"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useT } from "../../lib/i18n";
import {
  createAudioAnalysis,
  createTtsJob,
  fetchAudioAnalysisSummary,
  fetchJob,
  fetchTranscript,
  fetchTranslationDraft,
  fetchTtsSummary,
  mergeTranscriptSegments,
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
import { pollAnalyzeJobUntilSettled } from "../../lib/transcriptEditorReanalyze";
import type { AudioAnalysisSummaryResponse, EditableSegment, TranscriptEditorState, TranslationPreset } from "../../types/transcript-editor";
import { TranscriptActionBar } from "./TranscriptActionBar";
import { TranscriptBeatRail } from "./TranscriptBeatRail";
import { TranscriptEditorHeader } from "./TranscriptEditorHeader";
import { TranscriptFocusEditor } from "./TranscriptFocusEditor";
import { TranscriptMediaPreview } from "./TranscriptMediaPreview";
import {
  isNoDialogueAnalysisSummary,
  TranscriptEmptyState,
  TranscriptErrorState,
  TranscriptLoadingState,
  TranscriptNoDialogueState
} from "./TranscriptStates";
import { UnsavedChangesGuard } from "./UnsavedChangesGuard";

export function TranscriptEditorPage({ sourceVideoId }: { sourceVideoId: string }) {
  const t = useT();
  const [state, setState] = useState<TranscriptEditorState | null>(null);
  const [savedState, setSavedState] = useState<TranscriptEditorState | null>(null);
  const [summary, setSummary] = useState<AudioAnalysisSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [synthesizingTts, setSynthesizingTts] = useState(false);
  const [joinedTtsAssetId, setJoinedTtsAssetId] = useState<string | null>(null);
  const [ttsSummary, setTtsSummary] = useState<TtsSummaryResponse | null>(null);
  const [analyzeJobId, setAnalyzeJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playRequestId, setPlayRequestId] = useState(0);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [transcript, translation, nextSummary] = await Promise.all([
        fetchTranscript(sourceVideoId),
        fetchTranslationDraft(sourceVideoId),
        fetchAudioAnalysisSummary(sourceVideoId)
      ]);
      const nextState = buildTranscriptEditorState(transcript, translation);
      setState(nextState);
      setSavedState(nextState);
      setSummary(nextSummary);
      try {
        const nextTtsSummary = await fetchTtsSummary(sourceVideoId);
        setTtsSummary(nextTtsSummary);
        setJoinedTtsAssetId(findJoinedTtsAssetId(nextTtsSummary));
      } catch {
        setTtsSummary(null);
        setJoinedTtsAssetId(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.loadError"));
    } finally {
      setLoading(false);
    }
  }, [sourceVideoId, t]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

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
          error_message: job.error_message,
          error_code: job.error_code
        };
      }
    });
  }

  async function translateLiteral(preset: TranslationPreset) {
    if (state && hasUnsavedChanges(state) && !window.confirm(t("transcriptEditorPage.translateUnsavedConfirm"))) {
      return;
    }
    setTranslating(true);
    setError(null);
    setAnalyzeJobId(null);
    try {
      const created = await rerunTranslationDraft(sourceVideoId, preset);
      setAnalyzeJobId(created.job_id);
      const settled = await pollJob(created.job_id);
      if (settled.outcome === "success") {
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
        }
        return;
      }
      if (settled.outcome === "failed") {
        setError(`${t("transcriptEditorPage.translateFailed")}: ${settled.errorMessage ?? settled.status}`);
        return;
      }
      setError(t("transcriptEditorPage.translateTimeout"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.translateError"));
    } finally {
      setTranslating(false);
    }
  }

  async function reanalyzeAudio(preset: TranslationPreset) {
    if (state && hasUnsavedChanges(state) && !window.confirm(t("transcriptEditorPage.reanalyzeUnsavedConfirm"))) {
      return;
    }
    setReanalyzing(true);
    setError(null);
    setAnalyzeJobId(null);
    try {
      const created = await createAudioAnalysis(sourceVideoId, preset, true, true);
      setAnalyzeJobId(created.job_id);
      const settled = await pollJob(created.job_id);
      if (settled.outcome === "success") {
        await loadData();
        return;
      }
      if (settled.outcome === "failed") {
        setError(`${t("transcriptEditorPage.reanalyzeFailed")}: ${settled.errorMessage ?? settled.status}`);
        return;
      }
      setError(t("transcriptEditorPage.reanalyzeTimeout"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.reanalyzeError"));
    } finally {
      setReanalyzing(false);
    }
  }

  async function generateTts() {
    if (!state) return;
    const filled = state.segments.filter((segment) => segment.translatedText.trim()).length;
    if (filled === 0) {
      setError(t("transcriptEditorPage.ttsEmptyVi"));
      return;
    }
    if (hasUnsavedChanges(state) && !window.confirm(t("transcriptEditorPage.ttsUnsavedConfirm"))) {
      return;
    }
    setSynthesizingTts(true);
    setError(null);
    setAnalyzeJobId(null);
    try {
      const created = await createTtsJob(sourceVideoId);
      setAnalyzeJobId(created.job_id);
      const settled = await pollJob(created.job_id);
      if (settled.outcome === "success") {
        const nextTtsSummary = await fetchTtsSummary(sourceVideoId);
        setTtsSummary(nextTtsSummary);
        setJoinedTtsAssetId(findJoinedTtsAssetId(nextTtsSummary));
        return;
      }
      if (settled.outcome === "failed") {
        setError(`${t("transcriptEditorPage.ttsFailed")}: ${settled.errorMessage ?? settled.status}`);
        return;
      }
      setError(t("transcriptEditorPage.ttsTimeout"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("transcriptEditorPage.ttsError"));
    } finally {
      setSynthesizingTts(false);
    }
  }

  if (loading) return <TranscriptLoadingState />;
  if (error && !state) return <TranscriptErrorState message={error} onRetry={loadData} />;
  if (!state || state.segments.length === 0) {
    if (isNoDialogueAnalysisSummary(summary)) {
      return <TranscriptNoDialogueState />;
    }
    return <TranscriptEmptyState />;
  }

  return (
    <main className="transcript-editor">
      <UnsavedChangesGuard enabled={dirtyCount > 0 && !reanalyzing && !translating && !synthesizingTts} />
      <TranscriptEditorHeader
        state={state}
        summary={summary}
        dirtyCount={dirtyCount}
        blockingCount={blockingWarnings.length}
        saving={saving}
        reanalyzing={reanalyzing}
        translating={translating}
        synthesizingTts={synthesizingTts}
        analyzeJobId={analyzeJobId}
        onSave={() => void saveDraft()}
        onDiscard={discardChanges}
        onTranslateLiteral={(preset) => void translateLiteral(preset)}
        onReanalyze={(preset) => void reanalyzeAudio(preset)}
        onGenerateTts={() => void generateTts()}
      />
      {error ? <div className="inline-error">{error}</div> : null}
      <section className="transcript-bench">
        <aside className="transcript-bench__side">
          <TranscriptMediaPreview
            summary={summary}
            selectedSegment={selectedSegment}
            playRequestId={playRequestId}
            joinedTtsAssetId={joinedTtsAssetId}
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
                setState((current) => (current ? selectSegment(current, selectedSegment.localId) : current));
                setPlayRequestId((current) => current + 1);
              }}
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
        saving={saving}
        onSave={() => void saveDraft()}
        onDiscard={discardChanges}
      />
    </main>
  );
}

function splitText(text: string): [string, string] {
  const trimmed = text.trim();
  if (!trimmed) return ["", ""];
  const midpoint = Math.floor(trimmed.length / 2);
  const splitAt = trimmed.indexOf(" ", midpoint);
  const index = splitAt > 0 ? splitAt : midpoint;
  return [trimmed.slice(0, index).trim(), trimmed.slice(index).trim()];
}
