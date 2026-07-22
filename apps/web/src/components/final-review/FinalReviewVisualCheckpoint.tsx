"use client";

import { useEffect, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import type { FinalReviewPrepFocus } from "../../lib/finalReviewState";
import type { OcrSummaryResponse } from "../../types/ocr";
import { fetchMediaAssetObjectUrl } from "../../lib/api";
import { AsyncButton } from "../shared/AsyncButton";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";

type Props = {
  summary: OcrSummaryResponse | null;
  analyzeBusy: boolean;
  approveBusy: boolean;
  message: string | null;
  onAnalyze: () => void;
  onApprove: () => void;
  presentation?: "prep" | "rail";
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
  summary,
  analyzeBusy,
  approveBusy,
  message,
  onAnalyze,
  onApprove,
  presentation = "rail",
  prepFocus = "ocr"
}: Props) {
  const t = useT();
  const events = summary?.hardsub_events ?? [];
  const cleanedAssetId = summary?.cleaned_video_asset_id ?? null;
  const objectUrlRef = useRef<string | null>(null);
  const [cleanedPlaybackUrl, setCleanedPlaybackUrl] = useState<string | null>(null);
  const [showAllEvents, setShowAllEvents] = useState(false);
  const unstableCount = events.filter((event) => event.unstable).length;
  const visibleEvents = showAllEvents ? events : events.slice(0, EVENTS_PREVIEW);
  const operatorWarnings = (summary?.warnings || []).filter((warning) => warning !== "hardsub_unstable");
  const priorCleaned =
    Boolean(summary?.cleaned_video_asset_id) &&
    (summary?.clean_produced === false || (summary?.warnings || []).includes("clean_skipped_no_hardsub"));
  const isPrep = presentation === "prep";
  const analyzeIsPrepFocus = isPrep && prepFocus === "ocr";

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

  return (
    <section
      className={`final-panel final-visual-checkpoint${isPrep ? " final-review-prep-panel" : ""}`}
      aria-label={t("finalReviewVisual.title")}
    >
      {isPrep ? <span className="final-review-prep-panel__eyebrow">{t("finalReviewVisual.checkpointEyebrow")}</span> : null}
      <h2 className={isPrep ? "final-review-prep-panel__title" : undefined}>{t("finalReviewVisual.title")}</h2>
      <p className={`final-visual-checkpoint__hint${isPrep ? " final-review-prep-panel__body" : ""}`}>
        {t("finalReviewVisual.hintShort")}
      </p>
      {message ? <p className="action-message">{message}</p> : null}

      <div className="final-visual-checkpoint__steps">
        <AsyncButton
          className={analyzeIsPrepFocus ? "primary is-prep-focus" : "primary"}
          leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="recheck" />}
          pending={analyzeBusy}
          pendingLabel={t("finalReviewVisual.analyzing")}
          onClick={onAnalyze}
          disabled={approveBusy}
        >
          {t("finalReviewVisual.analyzeOcr")}
        </AsyncButton>
        <AsyncButton
          className="final-visual-checkpoint__approve"
          leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="approve" />}
          pending={approveBusy}
          pendingLabel={t("finalReviewVisual.approving")}
          onClick={onApprove}
          disabled={analyzeBusy || !summary || summary.visual_approved}
        >
          {summary?.visual_approved ? t("finalReviewVisual.approved") : t("finalReviewVisual.approveVisual")}
        </AsyncButton>
      </div>

      {summary ? (
        <div className="final-visual-checkpoint__meta">
          <span className="pill">{t("finalReviewVisual.events").replace("{count}", String(events.length))}</span>
          {summary.cleaned_video_asset_id ? (
            priorCleaned ? (
              <span className="pill warn">{t("finalReviewVisual.priorCleanedKept")}</span>
            ) : (
              <span className="pill good">{t("finalReviewVisual.cleanedReady")}</span>
            )
          ) : (
            <span className="pill warn">{t("finalReviewVisual.noCleaned")}</span>
          )}
          {unstableCount > 0 ? (
            <span className="pill warn">
              {t("finalReviewVisual.unstableCount").replace("{count}", String(unstableCount))}
            </span>
          ) : null}
          {operatorWarnings.map((warning) => (
            <span className="pill warn" key={warning}>
              {formatOcrWarning(warning, t)}
            </span>
          ))}
        </div>
      ) : (
        <p className="muted">{t("finalReviewVisual.empty")}</p>
      )}

      {cleanedPlaybackUrl ? (
        <video className="final-visual-checkpoint__preview" src={cleanedPlaybackUrl} controls playsInline preload="metadata" />
      ) : null}

      {events.length > 0 ? (
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
      ) : null}
    </section>
  );
}
