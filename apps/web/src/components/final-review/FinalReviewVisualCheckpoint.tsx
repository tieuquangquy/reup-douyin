"use client";

import { useEffect, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import type { FinalReviewPrepFocus } from "../../lib/finalReviewState";
import {
  hasFinalReviewOcrRun,
  isFinalReviewDialogueTranslationApprovalPending,
  isFinalReviewOcrReviewPending,
  resolveFinalReviewOcrCheckpointMetrics
} from "../../lib/finalReviewState";
import type { OcrSummaryResponse } from "../../types/ocr";
import { fetchLocalizationArtifactObjectUrl, fetchMediaAssetObjectUrl } from "../../lib/api";
import { AsyncButton } from "../shared/AsyncButton";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";
import {
  FinalReviewActionStatus,
  type FinalReviewActionStatusState
} from "./FinalReviewActionStatus";

type Props = {
  sourceVideoId?: string;
  summary: OcrSummaryResponse | null;
  analyzeBusy: boolean;
  approveBusy: boolean;
  audioApproveBusy?: boolean;
  residualTranslationBusy?: boolean;
  status: FinalReviewActionStatusState | null;
  onAnalyze: () => void;
  onReanalyze?: () => void;
  onApproveDialogueTranslation?: () => void;
  onApprove: () => void;
  onApproveAudio?: () => void;
  onDismissStatus?: () => void;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  onSubmitOcrReview?: (
    decisions: Array<{
      content_id: string;
      decision: "APPROVE" | "EDIT" | "PRESERVE_SOURCE" | "REJECT_UI";
      ocr_text_approved?: string | null;
    }>
  ) => void;
  onSubmitTranslationReview?: (
    translations: Array<{ content_id: string; vi_text: string }>
  ) => void;
  onSubmitResidualTriage?: (
    suggestions: Array<{ content_id?: string; ocr_text: string; ocr_text_corrected: string; vi_text_suggested: string }>
  ) => void;
  onApproveResidual?: (proposalSha256: string) => void;
  onRetryResidualTranslation?: () => void;
  watchPaused?: boolean;
  pausePending?: boolean;
  cancelPending?: boolean;
  presentation?: "prep" | "prep-bar" | "rail";
  prepFocus?: FinalReviewPrepFocus;
};

type OcrReviewDecision = "" | "APPROVE" | "EDIT" | "PRESERVE_SOURCE" | "REJECT_UI";
type OcrReviewChoice = { decision: OcrReviewDecision; text: string };
type OcrReviewObject = NonNullable<OcrSummaryResponse["review_objects"]>[number];

function defaultOcrReviewChoice(row: OcrReviewObject): OcrReviewChoice {
  return {
    decision: row.provenance_classifications?.includes("UNCERTAIN")
      ? "PRESERVE_SOURCE"
      : row.ocr_text_candidate?.trim()
        ? "APPROVE"
        : "",
    text: row.ocr_text_candidate || ""
  };
}

const EVENTS_PREVIEW = 3;

function formatMs(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatOcrWarning(warning: string, t: (key: string) => string): string {
  switch (warning) {
    case "no_hardsub_detected":
      return t("finalReviewVisual.warnNoHardsub");
    case "clean_skipped_no_hardsub":
      return t("finalReviewVisual.warnCleanSkipped");
    case "no_prior_cleaned_video":
      return t("finalReviewVisual.warnNoPriorCleaned");
    case "hardsub_unstable":
      return t("finalReviewVisual.warnUnstable");
    default:
      return warning;
  }
}

const WORKFLOW_STAGE_I18N: Record<string, string> = {
  NOT_STARTED: "finalReviewVisual.stageNotStarted",
  PHASE2_READY: "finalReviewVisual.stagePhase2Ready",
  PHASE2_BLOCKED: "finalReviewVisual.stagePhase2Blocked",
  WAITING_OCR_REVIEW: "finalReviewVisual.stageWaitingOcrReview",
  WAITING_DIALOGUE_TRANSLATION_APPROVAL: "finalReviewVisual.stageWaitingDialogueTranslationApproval",
  PHASE3_PREPARING: "finalReviewVisual.stagePhase3Preparing",
  WAITING_TRANSLATION_REVIEW: "finalReviewVisual.stageWaitingTranslationReview",
  READY_FOR_VISUAL_PREVIEW: "finalReviewVisual.stageReadyForVisualPreview",
  WAITING_RESIDUAL_TRIAGE: "finalReviewVisual.stageWaitingResidualTriage",
  WAITING_RESIDUAL_REVIEW: "finalReviewVisual.stageWaitingResidualReview",
  WAITING_VISUAL_REVIEW: "finalReviewVisual.stageWaitingVisualReview",
  VISUAL_APPROVED: "finalReviewVisual.stageVisualApproved",
  WAITING_AUDIO_REVIEW: "finalReviewVisual.stageWaitingAudioReview",
  AUDIO_APPROVED: "finalReviewVisual.stageAudioApproved",
  FINAL_READY: "finalReviewVisual.stageFinalReady"
};

function workflowStageLabel(stage: string | null | undefined, t: (key: string) => string): string {
  if (!stage) return t("finalReviewVisual.stageUnknown");
  const key = WORKFLOW_STAGE_I18N[stage];
  if (key) return t(key);
  return stage.replace(/_/g, " ").toLowerCase();
}

const RESIDUAL_ACTION_I18N: Record<string, string> = {
  EXPAND_EXISTING_PHASE2_GEOMETRY: "finalReviewVisual.residualActionExpandGeometry",
  ADD_PHASE2_OCCURRENCE: "finalReviewVisual.residualActionAddOccurrence"
};

function residualActionLabel(action: string | null | undefined, t: (key: string) => string): string {
  if (!action) return "";
  const key = RESIDUAL_ACTION_I18N[action];
  if (key) return t(key);
  return action.replace(/_/g, " ").toLowerCase();
}

function pipelineFactsLine(summary: OcrSummaryResponse): string | null {
  const parts: string[] = [];
  if (summary.all_frame_proxy_size) {
    const [width, height] = summary.all_frame_proxy_size;
    const triggers =
      summary.visual_trigger_count != null ? ` · ${summary.visual_trigger_count} visual triggers` : "";
    parts.push(`Proxy ${width}×${height}${triggers}`);
  }
  if (summary.detector_frame_count) {
    const elapsed =
      summary.analysis_elapsed_s != null ? ` · ${summary.analysis_elapsed_s.toFixed(1)}s` : "";
    parts.push(
      `Detector ${summary.detector_frame_count} frame · ${summary.candidate_window_count || 0} event${elapsed}`
    );
  }
  return parts.length ? parts.join(" · ") : null;
}

export function FinalReviewVisualCheckpoint({
  sourceVideoId,
  summary,
  analyzeBusy,
  approveBusy,
  audioApproveBusy = false,
  residualTranslationBusy = false,
  status,
  onAnalyze,
  onReanalyze,
  onApproveDialogueTranslation,
  onApprove,
  onApproveAudio,
  onDismissStatus,
  onPause,
  onResume,
  onCancel,
  onSubmitOcrReview,
  onSubmitTranslationReview,
  onSubmitResidualTriage,
  onApproveResidual,
  onRetryResidualTranslation,
  watchPaused = false,
  pausePending = false,
  cancelPending = false,
  presentation = "rail",
  prepFocus = "ocr"
}: Props) {
  const t = useT();
  const events = summary?.hardsub_events ?? [];
  const cleanedAssetId = summary?.cleaned_video_asset_id ?? null;
  const objectUrlRef = useRef<string | null>(null);
  const audioObjectUrlRef = useRef<string | null>(null);
  const [cleanedPlaybackUrl, setCleanedPlaybackUrl] = useState<string | null>(null);
  const [audioMixPlaybackUrl, setAudioMixPlaybackUrl] = useState<string | null>(null);
  const [previewFrame, setPreviewFrame] = useState<{ aspect: string; orientation: "portrait" | "landscape" | "square" } | null>(
    null
  );
  const [showAllEvents, setShowAllEvents] = useState(false);
  const [ocrReview, setOcrReview] = useState<Record<string, OcrReviewChoice>>({});
  const [translationReview, setTranslationReview] = useState<Record<string, string>>({});
  const [residualReview, setResidualReview] = useState<
    Record<string, { corrected: string; vi: string }>
  >({});
  const [reviewImageUrls, setReviewImageUrls] = useState<Record<string, string>>({});
  const unstableCount = events.filter((event) => event.unstable).length;
  const visibleEvents = showAllEvents ? events : events.slice(0, EVENTS_PREVIEW);
  const operatorWarnings = (summary?.warnings || []).filter((warning) => warning !== "hardsub_unstable");
  const priorCleaned =
    Boolean(summary?.cleaned_video_asset_id) &&
    (summary?.clean_produced === false || (summary?.warnings || []).includes("clean_skipped_no_hardsub"));
  const isPrep = presentation === "prep";
  const isPrepBar = presentation === "prep-bar";
  const analyzeIsPrepFocus = isPrep && prepFocus === "ocr";
  const approveNeedsFocus =
    isPrep &&
    prepFocus === "render" &&
    Boolean(summary?.cleaned_video_asset_id) &&
    !summary?.visual_approved;
  // Prep Visual is always the content panel (hero when OCR-focused, full-width when render-focused).
  const prepRoleClass = isPrep ? " is-prep-hero" : "";
  const approveQuiet = !summary?.cleaned_video_asset_id && !summary?.visual_approved;
  const canRegenerateQualityPreview =
    summary?.workflow_version === "QUALITY_LOCALIZATION_V24_1" &&
    summary.workflow_stage === "WAITING_VISUAL_REVIEW" &&
    (summary.translation_objects || []).length > 0;

  useEffect(() => {
    let cancelled = false;

    function revoke() {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    }

    async function loadCleaned() {
      revoke();
      setCleanedPlaybackUrl(null);
      setPreviewFrame(null);
      if (!cleanedAssetId) return;
      try {
        const objectUrl = await fetchMediaAssetObjectUrl(cleanedAssetId);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        objectUrlRef.current = objectUrl;
        setCleanedPlaybackUrl(objectUrl);
      } catch {
        if (!cancelled) setCleanedPlaybackUrl(null);
      }
    }

    void loadCleaned();
    return () => {
      cancelled = true;
      revoke();
    };
  }, [cleanedAssetId]);

  useEffect(() => {
    setOcrReview(
      Object.fromEntries(
        (summary?.review_objects || []).map((row) => [
          row.content_id,
          defaultOcrReviewChoice(row)
        ])
      )
    );
    setTranslationReview(
      Object.fromEntries(
        (summary?.translation_objects || []).map((row) => [
          row.content_id,
          row.vi_text_candidate || ""
        ])
      )
    );
    setResidualReview(
      Object.fromEntries(
        (summary?.residual_review_objects || []).map((row) => [
          row.content_id,
          {
            corrected: row.ocr_text_corrected_suggested || row.text || "",
            vi: row.vi_text_suggested || ""
          }
        ])
      )
    );
  }, [
    summary?.artifact_run_id,
    summary?.workflow_stage,
    summary?.residual_translation_input_sha256,
    summary?.residual_translation_status
  ]);

  useEffect(() => {
    let cancelled = false;
    const created: string[] = [];
    async function loadReviewImages() {
      const rows = [
        ...(summary?.review_objects || []),
        ...(summary?.residual_review_objects || [])
      ].filter((row) => row.image_path && sourceVideoId);
      const entries = await Promise.all(
        rows.map(async (row) => {
          try {
            const path = String(row.image_path || "").replace(/^\/+/, "");
            // Review rows are emitted as root-relative paths (for example
            // qa/overlays/...).  Never allow a browser-supplied path to escape
            // the server-side artifact boundary.
            if (!path || path.includes("..") || path.startsWith("/")) return null;
            const objectUrl = await fetchLocalizationArtifactObjectUrl(sourceVideoId!, path);
            created.push(objectUrl);
            return [row.content_id, objectUrl] as const;
          } catch {
            return null;
          }
        })
      );
      if (cancelled) {
        created.forEach((url) => URL.revokeObjectURL(url));
        return;
      }
      setReviewImageUrls(Object.fromEntries(entries.filter((entry): entry is readonly [string, string] => Boolean(entry))));
    }
    setReviewImageUrls({});
    void loadReviewImages();
    return () => {
      cancelled = true;
      created.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [sourceVideoId, summary?.artifact_run_id, summary?.review_objects, summary?.residual_review_objects]);

  useEffect(() => {
    let cancelled = false;
    if (audioObjectUrlRef.current) {
      URL.revokeObjectURL(audioObjectUrlRef.current);
      audioObjectUrlRef.current = null;
    }
    setAudioMixPlaybackUrl(null);
    const path = summary?.audio_mix_preview_path;
    if (!path || !sourceVideoId) return;
    void fetchLocalizationArtifactObjectUrl(sourceVideoId, path)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        audioObjectUrlRef.current = url;
        setAudioMixPlaybackUrl(url);
      })
      .catch(() => setAudioMixPlaybackUrl(null));
    return () => {
      cancelled = true;
      if (audioObjectUrlRef.current) {
        URL.revokeObjectURL(audioObjectUrlRef.current);
        audioObjectUrlRef.current = null;
      }
    };
  }, [sourceVideoId, summary?.artifact_run_id, summary?.audio_mix_preview_path]);

  function onPreviewLoadedMetadata(event: { currentTarget: HTMLVideoElement }) {
    const video = event.currentTarget;
    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!(width > 0 && height > 0)) {
      setPreviewFrame(null);
      return;
    }
    const orientation = width > height * 1.05 ? "landscape" : height > width * 1.05 ? "portrait" : "square";
    setPreviewFrame({ aspect: `${width} / ${height}`, orientation });
  }

  const useShortPrepLabels = isPrep || isPrepBar || presentation === "rail";
  const useCompactMeta = useShortPrepLabels;
  const hasOcrResult = hasFinalReviewOcrRun(summary);
  const ocrReviewPending = isFinalReviewOcrReviewPending(summary);
  const ocrCheckpoint = resolveFinalReviewOcrCheckpointMetrics(summary);
  const cleanPreviewEmptyLabel = ocrReviewPending
    ? t("finalReviewVisual.cleanPreviewAfterOcrReviewShort")
    : t("finalReviewVisual.noCleaned");
  const dialogueTranslationPending =
    isFinalReviewDialogueTranslationApprovalPending(summary);
  const pipelineFacts = summary ? pipelineFactsLine(summary) : null;
  // Status strip owns Pause/Resume/Cancel — don't also show a spinning Analyze CTA.
  // Dialogue gate / Exact OCR list own their CTAs — hide the duplicate steps CTA.
  const hideAnalyzeCta =
    watchPaused ||
    status?.phase === "queued" ||
    status?.phase === "running" ||
    dialogueTranslationPending ||
    ocrReviewPending;
  const showVisualApprove =
    !summary ||
    summary.workflow_version !== "QUALITY_LOCALIZATION_V24_1" ||
    Boolean(summary.visual_approved) ||
    summary.workflow_stage === "WAITING_VISUAL_REVIEW";
  const analyzeLabel = dialogueTranslationPending
    ? t("finalReviewVisual.approveDialogueTranslation")
    : ocrReviewPending
    ? t("finalReviewVisual.reviewOcrBelow")
    : hasOcrResult
    ? t(useShortPrepLabels ? "finalReviewVisual.reanalyzeOcrShort" : "finalReviewVisual.reanalyzeOcr")
    : t(useShortPrepLabels ? "finalReviewVisual.analyzeOcrShort" : "finalReviewVisual.analyzeOcr");
  const steps = (
    <div className="final-visual-checkpoint__steps">
      {hideAnalyzeCta ? null : (
        <AsyncButton
          className={analyzeIsPrepFocus ? "primary is-prep-focus" : isPrep || isPrepBar ? "is-prep-quiet" : "primary"}
          leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind={dialogueTranslationPending ? "approve" : ocrReviewPending ? "details" : "recheck"} />}
          pending={analyzeBusy && !ocrReviewPending}
          pendingLabel={t("finalReviewVisual.analyzing")}
          onClick={
            dialogueTranslationPending
              ? onApproveDialogueTranslation
              : ocrReviewPending
              ? () => document.getElementById("final-review-ocr-review")?.scrollIntoView({ behavior: "smooth", block: "start" })
              : onAnalyze
          }
          disabled={
            approveBusy ||
            (dialogueTranslationPending && !onApproveDialogueTranslation) ||
            (ocrReviewPending && !onSubmitOcrReview)
          }
        >
          {analyzeLabel}
        </AsyncButton>
      )}
      {showVisualApprove ? (
      <AsyncButton
        className={`final-visual-checkpoint__approve${approveQuiet ? " is-approve-quiet" : ""}${
          approveNeedsFocus ? " primary is-prep-focus" : ""
        }`}
        leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="approve" />}
        pending={approveBusy}
        pendingLabel={t("finalReviewVisual.approving")}
        onClick={onApprove}
        disabled={
          analyzeBusy ||
          watchPaused ||
          !summary ||
          summary.visual_approved ||
          (summary.workflow_version === "QUALITY_LOCALIZATION_V24_1" &&
            !summary.cleaned_video_asset_id) ||
          (summary.workflow_version === "QUALITY_LOCALIZATION_V24_1" &&
            summary.workflow_stage !== "WAITING_VISUAL_REVIEW")
        }
      >
        {summary?.visual_approved
          ? t(useShortPrepLabels ? "finalReviewVisual.approvedShort" : "finalReviewVisual.approved")
          : t(useShortPrepLabels ? "finalReviewVisual.approveVisualShort" : "finalReviewVisual.approveVisual")}
      </AsyncButton>
      ) : null}
    </div>
  );

  const meta = summary ? (
    <div className={`final-visual-checkpoint__meta${isPrep || presentation === "rail" ? " final-visual-checkpoint__meta--quiet" : ""}`}>
      {ocrReviewPending ? (
        <span className={useCompactMeta ? "final-visual-checkpoint__stat is-warn" : "pill warn"}>
          {t("finalReviewVisual.ocrReviewCountShort").replace(
            "{count}",
            String(ocrCheckpoint.manual)
          )}
        </span>
      ) : (
      <span className={useCompactMeta ? "final-visual-checkpoint__stat" : "pill"}>
        {t(
          summary.workflow_version === "QUALITY_LOCALIZATION_V24_1"
            ? useCompactMeta
              ? "finalReviewVisual.objectsShort"
              : "finalReviewVisual.objects"
            : useCompactMeta
              ? "finalReviewVisual.eventsShort"
              : "finalReviewVisual.events"
        ).replace(
          "{count}",
          String(
            summary.workflow_version === "QUALITY_LOCALIZATION_V24_1"
              ? summary.phase2_content_object_count || summary.text_object_count || 0
              : events.length
          )
        )}
      </span>
      )}
      {dialogueTranslationPending && (summary.dialogue_translation_blocked_count || 0) > 0 ? (
        <span className={useCompactMeta ? "final-visual-checkpoint__stat is-warn" : "pill warn"}>
          {t(
            useCompactMeta ? "finalReviewVisual.objectsNeedViShort" : "finalReviewVisual.objectsNeedVi"
          ).replace("{count}", String(summary.dialogue_translation_blocked_count || 0))}
        </span>
      ) : null}
      {summary.cleaned_video_asset_id ? (
        priorCleaned ? (
          <span className={useCompactMeta ? "final-visual-checkpoint__stat is-warn" : "pill warn"}>
            {t("finalReviewVisual.priorCleanedKept")}
          </span>
        ) : (
          <span className={useCompactMeta ? "final-visual-checkpoint__stat is-good" : "pill good"}>
            {t(useCompactMeta ? "finalReviewVisual.cleanedReadyShort" : "finalReviewVisual.cleanedReady")}
          </span>
        )
      ) : dialogueTranslationPending ? (
        <span className={useCompactMeta ? "final-visual-checkpoint__stat is-warn" : "pill warn"}>
          {t(useCompactMeta ? "finalReviewVisual.ocrDoneWaitingShort" : "finalReviewVisual.ocrDoneWaiting")}
        </span>
      ) : !ocrReviewPending ? (
        <span className={useCompactMeta ? "final-visual-checkpoint__stat" : "pill"}>
          {t(useCompactMeta ? "finalReviewVisual.noCleanedShort" : "finalReviewVisual.noCleaned")}
        </span>
      ) : null}
      {unstableCount > 0 ? (
        <span className={useCompactMeta ? "final-visual-checkpoint__stat is-warn" : "pill warn"}>
          {t("finalReviewVisual.unstableCount").replace("{count}", String(unstableCount))}
        </span>
      ) : null}
      {operatorWarnings.map((warning) => (
        <span className={useCompactMeta ? "final-visual-checkpoint__stat is-warn" : "pill warn"} key={warning}>
          {formatOcrWarning(warning, t)}
        </span>
      ))}
    </div>
  ) : (
    <p className="muted">{t("finalReviewVisual.empty")}</p>
  );

  if (isPrepBar) {
    return (
      <section className="final-visual-checkpoint final-visual-checkpoint--prep-bar" aria-label={t("finalReviewVisual.title")}>
        <div className="final-visual-checkpoint__bar-main">
          <strong className="final-visual-checkpoint__bar-title">{t("finalReviewVisual.title")}</strong>
          {steps}
        </div>
        {meta}
      </section>
    );
  }

  const preview = cleanedPlaybackUrl ? (
    <video className="final-visual-checkpoint__preview" src={cleanedPlaybackUrl} controls playsInline preload="metadata" />
  ) : null;

  const eventsBlock =
    events.length > 0 ? (
      <div className="final-visual-checkpoint__events-wrap">
        <ul className="final-visual-checkpoint__events">
          {visibleEvents.map((event, index) => (
            <li key={`${event.start_ms}-${index}`}>
              <strong>
                {formatMs(event.start_ms)}–{formatMs(event.end_ms)}
              </strong>
              {event.unstable ? <span className="pill warn">{t("finalReviewVisual.unstable")}</span> : null}
              {event.texts?.[0] ? <span className="final-visual-checkpoint__text">{event.texts[0]}</span> : null}
            </li>
          ))}
        </ul>
        {events.length > EVENTS_PREVIEW ? (
          <button type="button" className="final-visual-checkpoint__more" onClick={() => setShowAllEvents((v) => !v)}>
            {showAllEvents
              ? t("finalReviewVisual.showFewerEvents")
              : t("finalReviewVisual.showAllEvents").replace("{count}", String(events.length))}
          </button>
        ) : null}
      </div>
    ) : null;

  const qualityReview = summary?.workflow_version === "QUALITY_LOCALIZATION_V24_1" ? (
    <div className="final-visual-checkpoint__quality-review">
      {ocrReviewPending ? (
        <section className="final-visual-checkpoint__gate is-ocr-review" role="status" aria-live="polite">
          <div className="final-visual-checkpoint__gate-icon" aria-hidden="true">
            <svg viewBox="0 0 20 20">
              <path
                d="M5 10.2 8.2 13.4 15 6.6"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="final-visual-checkpoint__gate-body">
            <h3 className="final-visual-checkpoint__gate-title">
              {t("finalReviewVisual.ocrCheckpointComplete")}
            </h3>
            <p className="final-visual-checkpoint__gate-copy">
              {t("finalReviewVisual.ocrCheckpointSummaryCompact")
                .replace("{automatic}", String(ocrCheckpoint.automatic))
                .replace("{manual}", String(ocrCheckpoint.manual))}
            </p>
          </div>
          <button
            className="final-visual-checkpoint__gate-review-cta"
            type="button"
            onClick={() => document.getElementById("final-review-ocr-review")?.scrollIntoView({ behavior: "smooth", block: "start" })}
          >
            {t("finalReviewVisual.ocrCheckpointReviewCta").replace(
              "{count}",
              String(ocrCheckpoint.manual)
            )}
          </button>
        </section>
      ) : null}
      {dialogueTranslationPending ? (
        <section className="final-visual-checkpoint__gate" role="status" aria-live="polite">
          <div className="final-visual-checkpoint__gate-icon" aria-hidden="true">
            <svg viewBox="0 0 20 20">
              <path
                d="M5 10.2 8.2 13.4 15 6.6"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="final-visual-checkpoint__gate-body">
            <h3 className="final-visual-checkpoint__gate-title">{t("finalReviewVisual.dialogueTranslationBlockedTitle")}</h3>
            <p className="final-visual-checkpoint__gate-copy">
              {t("finalReviewVisual.dialogueTranslationBlockedHint").replace(
                "{count}",
                String(summary.dialogue_translation_blocked_count || 0)
              )}
            </p>
          </div>
          <div className="final-visual-checkpoint__gate-actions">
            <AsyncButton
              className="final-visual-checkpoint__gate-cta"
              leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="approve" />}
              pending={analyzeBusy}
              pendingLabel={t("finalReviewVisual.resumingOcr")}
              disabled={!onApproveDialogueTranslation}
              onClick={onApproveDialogueTranslation}
            >
              {t("finalReviewVisual.approveAndResumeOcr")}
            </AsyncButton>
            <a
              className="final-visual-checkpoint__gate-link"
              href={`/production/transcript-editor/${sourceVideoId}`}
            >
              <WorkItemActionIcon className="fr-tool__icon" kind="transcript" />
              <span>{t("finalReviewVisual.reviewDialogueTranslation")}</span>
            </a>
          </div>
        </section>
      ) : null}
      <details className="final-visual-checkpoint__pipeline-detail">
        <summary>
          <span className="final-visual-checkpoint__pipeline-summary">
            <strong>{t("finalReviewVisual.pipelineDetail")}</strong>
            {!dialogueTranslationPending && !ocrReviewPending ? (
              <span
                className={`final-visual-checkpoint__stage-chip${
                  summary.workflow_stage === "WAITING_OCR_REVIEW" ? " is-attention" : ""
                }`}
              >
                {workflowStageLabel(summary.workflow_stage, t)}
              </span>
            ) : null}
          </span>
        </summary>
        <div className="final-visual-checkpoint__quality-stage">
        {dialogueTranslationPending ? (
          <span className="final-visual-checkpoint__stage-chip is-attention">
            {workflowStageLabel(summary.workflow_stage, t)}
          </span>
        ) : null}
        {summary.phase2_model_version ? (
          <span className="final-visual-checkpoint__pipeline-fingerprint">{summary.phase2_model_version}</span>
        ) : null}
        {(summary.local_recovery_summary?.attempted_tracks || 0) > 0 ||
        (summary.local_recovery_summary?.geometry_tracks_derived || 0) > 0 ? (
          <div className="final-visual-checkpoint__pipeline-band">
            {(summary.local_recovery_summary?.attempted_tracks || 0) > 0 ? (
              <span className="pill">
                OCR recovery: {summary.local_recovery_summary?.editor_candidates_recovered || 0} editor ·{" "}
                {summary.local_recovery_summary?.promoted_source_ui_tracks || 0} giữ source
              </span>
            ) : null}
            {(summary.local_recovery_summary?.geometry_tracks_derived || 0) > 0 ? (
              <span className="pill">
                Geometry hardsub: {summary.local_recovery_summary?.geometry_tracks_derived || 0} derived /{" "}
                {summary.local_recovery_summary?.geometry_tracks_fail_closed || 0} fail-closed
              </span>
            ) : null}
          </div>
        ) : null}
        <div className="final-visual-checkpoint__pipeline-band">
          <span className="pill">
            Editor: {summary.provenance_counts?.EDITOR_OVERLAY || 0}
          </span>
          <span className="pill">
            {summary.analysis_engine === "audio_visual_temporal_v1"
              ? "Local temporal"
              : summary.analysis_engine || "Local OCR"}
          </span>
          {summary.analysis_recipe_release ? (
            <span
              className="pill"
              title={summary.analysis_recipe_sha256 || summary.analysis_recipe_release}
            >
              {summary.analysis_recipe_release}
            </span>
          ) : null}
          {summary.pipeline_recipe_release ? (
            <span
              className="final-visual-checkpoint__pipeline-release"
              title={summary.pipeline_recipe_sha256 || summary.pipeline_recipe_release}
            >
              Pipeline {summary.pipeline_recipe_release}
            </span>
          ) : null}
          {summary.analysis_mode ? (
            <span className="pill">
              {summary.analysis_mode === "AUDIO_GUIDED_VISUAL"
                ? `Audio-guided · ${summary.audio_window_count || 0} windows`
                : "Visual-only"}
            </span>
          ) : null}
          {summary.analysis_fallback_used ? <span className="pill warn">V58 fallback</span> : null}
        </div>
        {pipelineFacts ? (
          <p className="final-visual-checkpoint__pipeline-facts">{pipelineFacts}</p>
        ) : null}
        <div className="final-visual-checkpoint__pipeline-band">
          <span className="pill">
            Giữ source: {summary.protected_source_tracks || summary.provenance_counts?.SOURCE_INTRINSIC || 0}
          </span>
          {(summary.provenance_counts?.UNCERTAIN || 0) > 0 ? (
            <span className="pill warn">Cần phân loại: {summary.provenance_counts?.UNCERTAIN}</span>
          ) : null}
        </div>
        </div>
      </details>
      {summary.workflow_stage === "WAITING_OCR_REVIEW" && (summary.review_objects || []).length > 0 ? (
        <div className="final-visual-checkpoint__review-list is-compact is-ocr" id="final-review-ocr-review">
          <div className="final-visual-checkpoint__review-head">
            <h3>{t("finalReviewVisual.ocrExactReview")}</h3>
            <span className="final-visual-checkpoint__review-count">
              {(summary.review_objects || []).length}
            </span>
          </div>
          <p className="final-visual-checkpoint__review-instruction">
            {t("finalReviewVisual.ocrReviewInstruction").replace(
              "{count}",
              String(ocrCheckpoint.manual)
            )}
          </p>
          {(summary.review_objects || []).map((row, index) => {
            const value = ocrReview[row.content_id] || defaultOcrReviewChoice(row);
            const provenance =
              row.visual_provenance?.classification || row.provenance_classifications?.[0] || "EDITOR_OVERLAY";
            const showProvenanceChip =
              provenance === "UNCERTAIN" ||
              (Boolean(provenance) && provenance !== "EDITOR_OVERLAY" && provenance !== "EDITOR_LABEL");
            const shortId = (() => {
              const digits = row.content_id.match(/(\d+)$/)?.[1];
              return digits ? `#${digits}` : `#${index + 1}`;
            })();
            return (
              <div className="final-visual-checkpoint__review-row" key={row.content_id}>
                <div className="final-visual-checkpoint__review-meta">
                  <strong title={row.content_id}>{shortId}</strong>
                  {(row.roles || []).length > 0 ? (
                    <span className="muted">{(row.roles || []).join(" · ")}</span>
                  ) : null}
                  {showProvenanceChip ? (
                    <span className={`final-visual-checkpoint__review-chip${provenance === "UNCERTAIN" ? " is-warn" : ""}`}>
                      {provenance.replace(/^EDITOR_/, "")}
                    </span>
                  ) : null}
                  {reviewImageUrls[row.content_id] ? (
                    <img
                      className="final-visual-checkpoint__review-evidence"
                      src={reviewImageUrls[row.content_id]}
                      alt={row.content_id}
                    />
                  ) : null}
                </div>
                <input
                  className="final-visual-checkpoint__review-input"
                  value={value.text}
                  disabled={value.decision === "PRESERVE_SOURCE"}
                  onChange={(event) =>
                    setOcrReview((current) => ({
                      ...current,
                      [row.content_id]: {
                        text: event.target.value,
                        decision: !event.target.value.trim()
                          ? ""
                          : event.target.value === row.ocr_text_candidate
                            ? "APPROVE"
                            : "EDIT"
                      }
                    }))
                  }
                />
                <select
                  className="final-visual-checkpoint__review-select"
                  value={value.decision}
                  onChange={(event) =>
                    setOcrReview((current) => ({
                      ...current,
                      [row.content_id]: {
                        ...value,
                        decision: event.target.value as OcrReviewDecision
                      }
                    }))
                  }
                >
                  <option value="" disabled>{t("finalReviewVisual.reviewDecisionRequired")}</option>
                  <option value="APPROVE">{t("finalReviewVisual.reviewApprove")}</option>
                  <option value="EDIT">{t("finalReviewVisual.reviewEdit")}</option>
                  <option value="PRESERVE_SOURCE">{t("finalReviewVisual.reviewSourceUi")}</option>
                  <option value="REJECT_UI">{t("finalReviewVisual.reviewRejectUi")}</option>
                </select>
              </div>
            );
          })}
          <div className="final-visual-checkpoint__review-actions">
            <AsyncButton
              className="final-visual-checkpoint__review-save"
              leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="approve" />}
              pending={analyzeBusy}
              pendingLabel={t("finalReviewVisual.analyzing")}
              disabled={
                !onSubmitOcrReview ||
                (summary.review_objects || []).some((row) => {
                  const value = ocrReview[row.content_id] || defaultOcrReviewChoice(row);
                  return (
                    !value.decision ||
                    (["APPROVE", "EDIT"].includes(value.decision) && !value.text.trim())
                  );
                })
              }
              onClick={() => {
                const decisions = (summary.review_objects || []).flatMap((row) => {
                  const value = ocrReview[row.content_id] || defaultOcrReviewChoice(row);
                  if (!value.decision) return [];
                  return [{
                    content_id: row.content_id,
                    decision: value.decision,
                    ocr_text_approved:
                      value.decision === "PRESERVE_SOURCE" || value.decision === "REJECT_UI"
                        ? null
                        : value.text.trim() || null
                  }];
                });
                if (decisions.length === (summary.review_objects || []).length) {
                  onSubmitOcrReview?.(decisions);
                }
              }}
            >
              {t("finalReviewVisual.submitOcrReview")}
            </AsyncButton>
          </div>
          <details className="final-visual-checkpoint__reanalyze-guard">
            <summary>
              <span className="final-visual-checkpoint__reanalyze-summary">
                {t("finalReviewVisual.reanalyzeAdvanced")}
              </span>
            </summary>
            <div className="final-visual-checkpoint__reanalyze-body">
              <p className="final-visual-checkpoint__reanalyze-warn">{t("finalReviewVisual.reanalyzeWarning")}</p>
              <AsyncButton
                className="final-visual-checkpoint__reanalyze-cta"
                leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="recheck" />}
                pending={analyzeBusy}
                pendingLabel={t("finalReviewVisual.analyzing")}
                disabled={approveBusy}
                onClick={() => {
                  if (window.confirm(t("finalReviewVisual.reanalyzeConfirm"))) {
                    (onReanalyze || onAnalyze)();
                  }
                }}
              >
                {t("finalReviewVisual.reanalyzeOcrShort")}
              </AsyncButton>
            </div>
          </details>
        </div>
      ) : null}
      {(summary.workflow_stage === "WAITING_TRANSLATION_REVIEW" ||
        summary.workflow_stage === "READY_FOR_VISUAL_PREVIEW" ||
        canRegenerateQualityPreview) ? (
        <div className="final-visual-checkpoint__review-list is-compact is-translation">
          <div className="final-visual-checkpoint__review-head">
            <h3>{t("finalReviewVisual.visualTranslationReview")}</h3>
            <span className="final-visual-checkpoint__review-count">
              {(summary.translation_objects || []).length}
            </span>
          </div>
          {(summary.translation_objects || []).map((row, index) => {
            const shortId = (() => {
              const digits = row.content_id.match(/(\d+)$/)?.[1];
              return digits ? `#${digits}` : `#${index + 1}`;
            })();
            const roles = row.roles || [];
            const qualityFlags = row.quality_flags || [];
            return (
              <div className="final-visual-checkpoint__review-row is-translation" key={row.content_id}>
                <div className="final-visual-checkpoint__review-meta">
                  <strong title={row.content_id}>{shortId}</strong>
                  <div className="final-visual-checkpoint__review-chips">
                    {roles.map((role) => (
                      <span className="final-visual-checkpoint__review-chip" key={`${row.content_id}-${role}`}>
                        {role}
                      </span>
                    ))}
                    {qualityFlags.map((flag) => (
                      <span
                        className="final-visual-checkpoint__review-chip is-warn"
                        key={`${row.content_id}-flag-${flag}`}
                      >
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
                <p
                  aria-label={`${t("finalReviewVisual.translationSource")} ${shortId}`}
                  className="final-visual-checkpoint__review-source"
                  title={row.zh_approved}
                >
                  {row.zh_approved}
                </p>
                <input
                  aria-label={`${t("finalReviewVisual.translationTarget")} ${shortId}`}
                  className="final-visual-checkpoint__review-input"
                  value={translationReview[row.content_id] ?? row.vi_text_candidate ?? ""}
                  onChange={(event) =>
                    setTranslationReview((current) => ({
                      ...current,
                      [row.content_id]: event.target.value
                    }))
                  }
                />
              </div>
            );
          })}
          <div className="final-visual-checkpoint__review-actions">
            <AsyncButton
              className="final-visual-checkpoint__review-save"
              leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="approve" />}
              pending={analyzeBusy}
              pendingLabel={t("finalReviewVisual.analyzing")}
              disabled={!onSubmitTranslationReview}
              onClick={() =>
                onSubmitTranslationReview?.(
                  (summary.translation_objects || []).map((row) => ({
                    content_id: row.content_id,
                    vi_text: translationReview[row.content_id] ?? row.vi_text_candidate
                  }))
                )
              }
            >
              {canRegenerateQualityPreview
                ? t("finalReviewVisual.retryPreview")
                : t("finalReviewVisual.submitTranslationReview")}
            </AsyncButton>
          </div>
        </div>
      ) : null}
      {summary.workflow_stage === "WAITING_RESIDUAL_TRIAGE" ? (
        <div className="final-visual-checkpoint__review-list is-compact is-triage" id="final-review-residual-triage">
          <div className="final-visual-checkpoint__review-head">
            <h3>{t("finalReviewVisual.residualTriage")}</h3>
            <span className="final-visual-checkpoint__review-count">
              {(summary.residual_review_objects || []).length}
            </span>
          </div>
          <p className="final-visual-checkpoint__review-instruction">
            {t("finalReviewVisual.residualTriageHint")}
          </p>
          <p className="final-visual-checkpoint__review-status" role="status">
            {residualTranslationBusy
              ? t("finalReviewVisual.residualTranslationRunning")
              : summary.residual_translation_status === "READY"
                ? t("finalReviewVisual.residualTranslationReady")
                : t("finalReviewVisual.residualTranslationUnavailable")}
          </p>
          {(summary.residual_review_objects || []).map((row) => {
            const value = residualReview[row.content_id] || {
              corrected: row.ocr_text_corrected_suggested || row.text || "",
              vi: row.vi_text_suggested || ""
            };
            return (
              <div className="final-visual-checkpoint__review-row is-triage" key={row.content_id}>
                <div className="final-visual-checkpoint__review-meta">
                  <strong title={row.text}>{row.text}</strong>
                  <span className="muted">frame {row.frame_index ?? "—"}</span>
                  {reviewImageUrls[row.content_id] ? (
                    <img className="final-visual-checkpoint__review-evidence" src={reviewImageUrls[row.content_id]} alt={row.content_id} />
                  ) : null}
                </div>
                <input
                  aria-label={t("finalReviewVisual.residualCorrectedText")}
                  className="final-visual-checkpoint__review-input"
                  placeholder={t("finalReviewVisual.residualCorrectedText")}
                  value={value.corrected}
                  onChange={(event) => setResidualReview((current) => ({
                    ...current,
                    [row.content_id]: { ...value, corrected: event.target.value }
                  }))}
                />
                <input
                  aria-label={t("finalReviewVisual.residualVietnameseText")}
                  className="final-visual-checkpoint__review-input"
                  placeholder={t("finalReviewVisual.residualVietnameseText")}
                  value={value.vi}
                  onChange={(event) => setResidualReview((current) => ({
                    ...current,
                    [row.content_id]: { ...value, vi: event.target.value }
                  }))}
                />
              </div>
            );
          })}
          <div className="final-visual-checkpoint__review-actions">
            {summary.residual_translation_status !== "READY" && onRetryResidualTranslation ? (
              <AsyncButton
                className="secondary"
                pending={residualTranslationBusy}
                pendingLabel={t("finalReviewVisual.residualTranslationRunning")}
                onClick={onRetryResidualTranslation}
              >
                {t("finalReviewVisual.retryResidualTranslation")}
              </AsyncButton>
            ) : null}
            <AsyncButton
              className="final-visual-checkpoint__review-save"
              leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="approve" />}
              pending={analyzeBusy || residualTranslationBusy}
              pendingLabel={
                residualTranslationBusy
                  ? t("finalReviewVisual.residualTranslationRunning")
                  : t("finalReviewVisual.analyzing")
              }
              disabled={
                residualTranslationBusy ||
                !onSubmitResidualTriage ||
                (summary.residual_review_objects || []).some((row) => {
                  const value = residualReview[row.content_id];
                  return !value?.corrected.trim() || !value?.vi.trim();
                })
              }
              onClick={() => onSubmitResidualTriage?.(
                (summary.residual_review_objects || []).map((row) => ({
                  content_id: row.content_id,
                  ocr_text: row.text || "",
                  ocr_text_corrected: residualReview[row.content_id]?.corrected || row.text || "",
                  vi_text_suggested: residualReview[row.content_id]?.vi || ""
                }))
              )}
            >
              {t("finalReviewVisual.buildResidualProposal")}
            </AsyncButton>
          </div>
        </div>
      ) : null}
      {summary.workflow_stage === "WAITING_RESIDUAL_REVIEW" ? (
        <div className="final-visual-checkpoint__review-list is-compact is-residual" id="final-review-residual-review">
          <div className="final-visual-checkpoint__review-head">
            <h3>{t("finalReviewVisual.residualProposalReview")}</h3>
            <span className="final-visual-checkpoint__review-count">
              {(summary.residual_proposal_objects || []).length}
            </span>
          </div>
          {(summary.residual_proposal_objects || []).map((row, index) => (
            <div className="final-visual-checkpoint__review-row is-residual" key={row.remediation_id || index}>
              <div className="final-visual-checkpoint__review-meta">
                {row.proposed_action ? (
                  <span
                    className="final-visual-checkpoint__review-chip"
                    title={row.proposed_action}
                  >
                    {residualActionLabel(row.proposed_action, t)}
                  </span>
                ) : null}
              </div>
              <p
                className="final-visual-checkpoint__review-source"
                title={row.ocr_text_suggested}
              >
                {row.ocr_text_suggested}
              </p>
              <span className="final-visual-checkpoint__review-target" title={row.render_text_suggested || undefined}>
                {row.render_text_suggested}
              </span>
            </div>
          ))}
          <div className="final-visual-checkpoint__review-actions">
            <AsyncButton
              className="final-visual-checkpoint__review-save"
              leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="approve" />}
              pending={analyzeBusy}
              pendingLabel={t("finalReviewVisual.analyzing")}
              disabled={!onApproveResidual || !summary.residual_proposal_sha256}
              onClick={() => summary.residual_proposal_sha256 && onApproveResidual?.(summary.residual_proposal_sha256)}
            >
              {t("finalReviewVisual.approveResidualProposal")}
            </AsyncButton>
          </div>
        </div>
      ) : null}
      {summary.workflow_stage === "WAITING_AUDIO_REVIEW" ? (
        <div className="final-visual-checkpoint__review-list" id="final-review-audio-review">
          <h3>{t("finalReviewVisual.audioMixReview")}</h3>
          <p className="muted">{t("finalReviewVisual.audioMixReviewHint")}</p>
          {audioMixPlaybackUrl ? (
            <audio controls preload="metadata" src={audioMixPlaybackUrl} />
          ) : (
            <p className="inline-error">{t("finalReviewVisual.audioPreviewUnavailable")}</p>
          )}
          {(summary.audio_warnings || []).length > 0 ? (
            <ul>
              {(summary.audio_warnings || []).map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          ) : null}
          <p className="muted">
            {Object.entries(summary.timing_fit_summary || {})
              .filter(([, count]) => count > 0)
              .map(([key, count]) => `${key}: ${count}`)
              .join(" · ")}
          </p>
          <div className="final-visual-checkpoint__steps">
            <AsyncButton
              className="primary"
              pending={audioApproveBusy}
              pendingLabel={t("finalReviewVisual.approvingAudio")}
              disabled={!audioMixPlaybackUrl || !onApproveAudio}
              onClick={onApproveAudio}
            >
              {t("finalReviewVisual.approveAudioMix")}
            </AsyncButton>
            <a className="button-link" href={`/production/transcript-editor/${sourceVideoId}`}>
              {t("finalReviewVisual.editTts")}
            </a>
          </div>
        </div>
      ) : null}
    </div>
  ) : null;

  const prepPreviewChrome = (
    <div className="final-visual-checkpoint__preview-chrome">
      <span className="final-visual-checkpoint__preview-label">
        <span className="final-visual-checkpoint__preview-dot" aria-hidden="true" />
        {t("finalReviewVisual.checkpointEyebrow")}
      </span>
      {cleanedPlaybackUrl ? (
        <span className="final-visual-checkpoint__preview-state">
          {t("finalReviewVisual.cleanedReadyShort")}
        </span>
      ) : null}
    </div>
  );

  if (isPrep) {
    return (
      <section
        className={`final-panel final-visual-checkpoint final-review-prep-panel is-prep-stage${prepRoleClass}`}
        aria-label={t("finalReviewVisual.title")}
      >
        <div className="final-visual-checkpoint__split">
          <div
            className={`final-visual-checkpoint__preview-stage${
              previewFrame ? ` is-${previewFrame.orientation}` : ""
            }`}
          >
            {prepPreviewChrome}
            {cleanedPlaybackUrl ? (
              <video
                className="final-visual-checkpoint__preview"
                src={cleanedPlaybackUrl}
                controls
                playsInline
                preload="metadata"
                onLoadedMetadata={onPreviewLoadedMetadata}
                style={previewFrame ? { aspectRatio: previewFrame.aspect } : undefined}
              />
            ) : (
              <p className="final-visual-checkpoint__preview-empty">
                {cleanPreviewEmptyLabel}
              </p>
            )}
          </div>
          <div className="final-visual-checkpoint__copy">
            <div className="final-visual-checkpoint__lead">
              <div className="final-visual-checkpoint__header">
                <span className="final-review-prep-panel__eyebrow">{t("finalReviewVisual.checkpointEyebrow")}</span>
                {summary ? meta : null}
              </div>
              <h2 className="final-review-prep-panel__title">{t("finalReviewVisual.titleShort")}</h2>
              <p className="final-visual-checkpoint__hint final-review-prep-panel__body">
                {prepFocus === "render" ? t("finalReviewVisual.hintReady") : t("finalReviewVisual.hintShort")}
              </p>
              {status ? (
                <FinalReviewActionStatus
                  phase={status.phase}
                  message={status.message}
                  onDismiss={onDismissStatus}
                  onPause={onPause}
                  onResume={onResume}
                  onCancel={onCancel}
                  watchPaused={watchPaused}
                  pausePending={pausePending}
                  cancelPending={cancelPending}
                />
              ) : null}
            </div>
            <div className="final-visual-checkpoint__tools">{steps}</div>
            {!summary ? <p className="muted">{t("finalReviewVisual.empty")}</p> : null}
            {eventsBlock}
            {qualityReview}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      className="final-panel final-visual-checkpoint final-visual-checkpoint--rail"
      aria-label={t("finalReviewVisual.title")}
    >
      {preview ?? (
        <div className="final-visual-checkpoint__preview-empty final-visual-checkpoint__preview-empty--rail">
          {t("finalReviewVisual.noCleaned")}
        </div>
      )}
      <div className="final-visual-checkpoint__rail-toolbar">
        <div className="final-visual-checkpoint__rail-identity">
          <h2>{t("finalReviewVisual.titleShort")}</h2>
          {summary ? meta : <p className="muted final-visual-checkpoint__rail-empty">{t("finalReviewVisual.empty")}</p>}
        </div>
        {steps}
      </div>
      {status ? (
        <FinalReviewActionStatus
          phase={status.phase}
          message={status.message}
          onDismiss={onDismissStatus}
          onPause={onPause}
          onResume={onResume}
          onCancel={onCancel}
          watchPaused={watchPaused}
          pausePending={pausePending}
          cancelPending={cancelPending}
        />
      ) : null}
      {eventsBlock}
      {qualityReview}
    </section>
  );
}
