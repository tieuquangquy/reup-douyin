"use client";

import { useEffect, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import type { FinalReviewPrepFocus } from "../../lib/finalReviewState";
import { hasFinalReviewOcrRun, isFinalReviewOcrReviewPending } from "../../lib/finalReviewState";
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
  status: FinalReviewActionStatusState | null;
  onAnalyze: () => void;
  onReanalyze?: () => void;
  onApprove: () => void;
  onApproveAudio?: () => void;
  onDismissStatus?: () => void;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  onSubmitOcrReview?: (
    decisions: Array<{
      content_id: string;
      decision: "APPROVE" | "EDIT" | "PRESERVE_SOURCE";
      ocr_text_approved?: string | null;
    }>
  ) => void;
  onSubmitTranslationReview?: (
    translations: Array<{ content_id: string; vi_text: string }>
  ) => void;
  onSubmitResidualTriage?: (
    suggestions: Array<{ ocr_text: string; ocr_text_corrected: string; vi_text_suggested: string }>
  ) => void;
  onApproveResidual?: (proposalSha256: string) => void;
  watchPaused?: boolean;
  pausePending?: boolean;
  cancelPending?: boolean;
  presentation?: "prep" | "prep-bar" | "rail";
  prepFocus?: FinalReviewPrepFocus;
};

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

export function FinalReviewVisualCheckpoint({
  sourceVideoId,
  summary,
  analyzeBusy,
  approveBusy,
  audioApproveBusy = false,
  status,
  onAnalyze,
  onReanalyze,
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
  const [ocrReview, setOcrReview] = useState<
    Record<string, { decision: "APPROVE" | "EDIT" | "PRESERVE_SOURCE"; text: string }>
  >({});
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
  const canRetryQualityPreview =
    summary?.workflow_version === "QUALITY_LOCALIZATION_V24_1" &&
    summary.workflow_stage === "WAITING_VISUAL_REVIEW" &&
    !summary.cleaned_video_asset_id &&
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
          {
            decision: row.provenance_classifications?.includes("UNCERTAIN")
              ? ("PRESERVE_SOURCE" as const)
              : ("APPROVE" as const),
            text: row.ocr_text_candidate || ""
          }
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
          { corrected: row.text || "", vi: "" }
        ])
      )
    );
  }, [summary?.artifact_run_id, summary?.workflow_stage]);

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
  // Status strip owns Pause/Resume/Cancel — don't also show a spinning Analyze CTA.
  const hideAnalyzeCta =
    watchPaused ||
    status?.phase === "queued" ||
    status?.phase === "running";
  const hasOcrResult = hasFinalReviewOcrRun(summary);
  const ocrReviewPending = isFinalReviewOcrReviewPending(summary);
  const analyzeLabel = ocrReviewPending
    ? t("finalReviewVisual.reviewOcrBelow")
    : hasOcrResult
    ? t(useShortPrepLabels ? "finalReviewVisual.reanalyzeOcrShort" : "finalReviewVisual.reanalyzeOcr")
    : t(useShortPrepLabels ? "finalReviewVisual.analyzeOcrShort" : "finalReviewVisual.analyzeOcr");
  const steps = (
    <div className="final-visual-checkpoint__steps">
      {hideAnalyzeCta ? null : (
        <AsyncButton
          className={analyzeIsPrepFocus ? "primary is-prep-focus" : isPrep || isPrepBar ? "is-prep-quiet" : "primary"}
          leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind={ocrReviewPending ? "details" : "recheck"} />}
          pending={analyzeBusy && !ocrReviewPending}
          pendingLabel={t("finalReviewVisual.analyzing")}
          onClick={
            ocrReviewPending
              ? () => document.getElementById("final-review-ocr-review")?.scrollIntoView({ behavior: "smooth", block: "start" })
              : onAnalyze
          }
          disabled={approveBusy || (ocrReviewPending && !onSubmitOcrReview)}
        >
          {analyzeLabel}
        </AsyncButton>
      )}
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
    </div>
  );

  const meta = summary ? (
    <div className={`final-visual-checkpoint__meta${isPrep || presentation === "rail" ? " final-visual-checkpoint__meta--quiet" : ""}`}>
      <span className={useCompactMeta ? "final-visual-checkpoint__stat" : "pill"}>
        {t(useCompactMeta ? "finalReviewVisual.eventsShort" : "finalReviewVisual.events").replace(
          "{count}",
          String(events.length)
        )}
      </span>
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
      ) : (
        <span className={useCompactMeta ? "final-visual-checkpoint__stat" : "pill"}>
          {t(useCompactMeta ? "finalReviewVisual.noCleanedShort" : "finalReviewVisual.noCleaned")}
        </span>
      )}
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
      <div className="final-visual-checkpoint__quality-stage">
        <strong>{t("finalReviewVisual.qualityWorkflow")}</strong>
        <span className="pill">{summary.workflow_stage}</span>
        {summary.phase2_model_version ? <span className="muted">{summary.phase2_model_version}</span> : null}
        <span className="pill">
          Editor: {summary.provenance_counts?.EDITOR_OVERLAY || 0}
        </span>
        <span className="pill">
          Giữ source: {summary.protected_source_tracks || summary.provenance_counts?.SOURCE_INTRINSIC || 0}
        </span>
        {(summary.provenance_counts?.UNCERTAIN || 0) > 0 ? (
          <span className="pill warn">Cần phân loại: {summary.provenance_counts?.UNCERTAIN}</span>
        ) : null}
      </div>
      {summary.workflow_stage === "WAITING_OCR_REVIEW" && (summary.review_objects || []).length > 0 ? (
        <div className="final-visual-checkpoint__review-list" id="final-review-ocr-review">
          <h3>{t("finalReviewVisual.ocrExactReview")}</h3>
          {(summary.review_objects || []).map((row) => {
            const value = ocrReview[row.content_id] || {
              decision: row.provenance_classifications?.includes("UNCERTAIN")
                ? ("PRESERVE_SOURCE" as const)
                : ("APPROVE" as const),
              text: row.ocr_text_candidate || ""
            };
            return (
              <div className="final-visual-checkpoint__review-row" key={row.content_id}>
                <div>
                  <strong>{row.content_id}</strong>
                  <span className="muted">{(row.roles || []).join(", ")}</span>
                  <span className="pill">
                    {row.visual_provenance?.classification || row.provenance_classifications?.[0] || "EDITOR_OVERLAY"}
                  </span>
                  {reviewImageUrls[row.content_id] ? (
                    <img
                      className="final-visual-checkpoint__review-evidence"
                      src={reviewImageUrls[row.content_id]}
                      alt={row.content_id}
                    />
                  ) : null}
                </div>
                <input
                  value={value.text}
                  disabled={value.decision === "PRESERVE_SOURCE"}
                  onChange={(event) =>
                    setOcrReview((current) => ({
                      ...current,
                      [row.content_id]: {
                        text: event.target.value,
                        decision: event.target.value === row.ocr_text_candidate ? "APPROVE" : "EDIT"
                      }
                    }))
                  }
                />
                <select
                  value={value.decision}
                  onChange={(event) =>
                    setOcrReview((current) => ({
                      ...current,
                      [row.content_id]: {
                        ...value,
                        decision: event.target.value as "APPROVE" | "EDIT" | "PRESERVE_SOURCE"
                      }
                    }))
                  }
                >
                  <option value="APPROVE">{t("finalReviewVisual.reviewApprove")}</option>
                  <option value="EDIT">{t("finalReviewVisual.reviewEdit")}</option>
                  <option value="PRESERVE_SOURCE">{t("finalReviewVisual.reviewSourceUi")}</option>
                </select>
              </div>
            );
          })}
          <AsyncButton
            className="primary"
            pending={analyzeBusy}
            pendingLabel={t("finalReviewVisual.analyzing")}
            disabled={!onSubmitOcrReview}
            onClick={() =>
              onSubmitOcrReview?.(
                (summary.review_objects || []).map((row) => {
                  const value = ocrReview[row.content_id];
                  return {
                    content_id: row.content_id,
                    decision: value?.decision || "APPROVE",
                    ocr_text_approved:
                      value?.decision === "PRESERVE_SOURCE" ? null : value?.text || row.ocr_text_candidate
                  };
                })
              )
            }
          >
            {t("finalReviewVisual.submitOcrReview")}
          </AsyncButton>
          <details className="final-visual-checkpoint__reanalyze-guard">
            <summary>{t("finalReviewVisual.reanalyzeAdvanced")}</summary>
            <p className="muted">{t("finalReviewVisual.reanalyzeWarning")}</p>
            <AsyncButton
              className="is-prep-quiet"
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
          </details>
        </div>
      ) : null}
      {(summary.workflow_stage === "WAITING_TRANSLATION_REVIEW" ||
        summary.workflow_stage === "READY_FOR_VISUAL_PREVIEW" ||
        canRetryQualityPreview) ? (
        <div className="final-visual-checkpoint__review-list">
          <h3>{t("finalReviewVisual.visualTranslationReview")}</h3>
          {(summary.translation_objects || []).map((row) => (
            <div className="final-visual-checkpoint__review-row" key={row.content_id}>
              <div>
                <strong>{row.zh_approved}</strong>
                <span className="muted">{(row.roles || []).join(", ")}</span>
              </div>
              <input
                value={translationReview[row.content_id] ?? row.vi_text_candidate ?? ""}
                onChange={(event) =>
                  setTranslationReview((current) => ({
                    ...current,
                    [row.content_id]: event.target.value
                  }))
                }
              />
            </div>
          ))}
          <AsyncButton
            className="primary"
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
            {canRetryQualityPreview
              ? t("finalReviewVisual.retryPreview")
              : t("finalReviewVisual.submitTranslationReview")}
          </AsyncButton>
        </div>
      ) : null}
      {summary.workflow_stage === "WAITING_RESIDUAL_TRIAGE" ? (
        <div className="final-visual-checkpoint__review-list" id="final-review-residual-triage">
          <h3>{t("finalReviewVisual.residualTriage")}</h3>
          <p className="muted">{t("finalReviewVisual.residualTriageHint")}</p>
          {(summary.residual_review_objects || []).map((row) => {
            const value = residualReview[row.content_id] || { corrected: row.text || "", vi: "" };
            return (
              <div className="final-visual-checkpoint__review-row" key={row.content_id}>
                <div>
                  <strong>{row.text}</strong>
                  <span className="muted">frame {row.frame_index ?? "—"}</span>
                  {reviewImageUrls[row.content_id] ? (
                    <img className="final-visual-checkpoint__review-evidence" src={reviewImageUrls[row.content_id]} alt={row.content_id} />
                  ) : null}
                </div>
                <input
                  aria-label={t("finalReviewVisual.residualCorrectedText")}
                  value={value.corrected}
                  onChange={(event) => setResidualReview((current) => ({
                    ...current,
                    [row.content_id]: { ...value, corrected: event.target.value }
                  }))}
                />
                <input
                  aria-label={t("finalReviewVisual.residualVietnameseText")}
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
          <AsyncButton
            className="primary"
            pending={analyzeBusy}
            pendingLabel={t("finalReviewVisual.analyzing")}
            disabled={
              !onSubmitResidualTriage ||
              (summary.residual_review_objects || []).some((row) => {
                const value = residualReview[row.content_id];
                return !value?.corrected.trim() || !value?.vi.trim();
              })
            }
            onClick={() => onSubmitResidualTriage?.(
              (summary.residual_review_objects || []).map((row) => ({
                ocr_text: row.text || "",
                ocr_text_corrected: residualReview[row.content_id]?.corrected || row.text || "",
                vi_text_suggested: residualReview[row.content_id]?.vi || ""
              }))
            )}
          >
            {t("finalReviewVisual.buildResidualProposal")}
          </AsyncButton>
        </div>
      ) : null}
      {summary.workflow_stage === "WAITING_RESIDUAL_REVIEW" ? (
        <div className="final-visual-checkpoint__review-list" id="final-review-residual-review">
          <h3>{t("finalReviewVisual.residualProposalReview")}</h3>
          {(summary.residual_proposal_objects || []).map((row, index) => (
            <div className="final-visual-checkpoint__review-row" key={row.remediation_id || index}>
              <div>
                <strong>{row.ocr_text_suggested}</strong>
                <span className="muted">{row.proposed_action}</span>
              </div>
              <span>{row.render_text_suggested}</span>
            </div>
          ))}
          <AsyncButton
            className="primary"
            pending={analyzeBusy}
            pendingLabel={t("finalReviewVisual.analyzing")}
            disabled={!onApproveResidual || !summary.residual_proposal_sha256}
            onClick={() => summary.residual_proposal_sha256 && onApproveResidual?.(summary.residual_proposal_sha256)}
          >
            {t("finalReviewVisual.approveResidualProposal")}
          </AsyncButton>
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
              <p className="final-visual-checkpoint__preview-empty">{t("finalReviewVisual.noCleaned")}</p>
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
