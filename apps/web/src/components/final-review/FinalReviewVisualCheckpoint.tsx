"use client";

import { useEffect, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import type { OcrSummaryResponse } from "../../types/ocr";
import { fetchMediaAssetObjectUrl } from "../../lib/api";

type Props = {
  summary: OcrSummaryResponse | null;
  analyzeBusy: boolean;
  approveBusy: boolean;
  message: string | null;
  onAnalyze: () => void;
  onApprove: () => void;
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
  onApprove
}: Props) {
  const t = useT();
  const stepsBusy = analyzeBusy || approveBusy;
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
    <section className="final-panel final-visual-checkpoint" aria-label={t("finalReviewVisual.title")}>
      <h2>{t("finalReviewVisual.title")}</h2>
      <p className="final-visual-checkpoint__hint">{t("finalReviewVisual.hintShort")}</p>
      {message ? <p className="action-message">{message}</p> : null}

      <div className="final-visual-checkpoint__steps">
        <button type="button" className="primary" onClick={onAnalyze} disabled={stepsBusy}>
          {analyzeBusy ? t("finalReviewVisual.analyzing") : t("finalReviewVisual.analyzeOcr")}
        </button>
        <button
          type="button"
          onClick={onApprove}
          disabled={stepsBusy || !summary || summary.visual_approved}
        >
          {summary?.visual_approved
            ? t("finalReviewVisual.approved")
            : approveBusy
              ? t("finalReviewVisual.approving")
              : t("finalReviewVisual.approveVisual")}
        </button>
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
