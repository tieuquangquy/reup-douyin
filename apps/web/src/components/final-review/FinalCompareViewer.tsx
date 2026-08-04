"use client";

import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { fetchMediaAssetObjectUrl } from "../../lib/api";
import { useT } from "../../lib/i18n";
import {
  formatRenderDuration,
  type FinalReviewCompareDiff
} from "../../lib/finalReviewState";
import type { CompareMode } from "../../types/final-review";

export function FinalCompareViewer({
  mode,
  finalAssetId,
  originalAssetId,
  compareDiff = null,
  onModeChange,
  onQuickToggle
}: {
  mode: CompareMode;
  finalAssetId: string | null;
  originalAssetId: string | null;
  compareDiff?: FinalReviewCompareDiff | null;
  onModeChange: (mode: CompareMode) => void;
  onQuickToggle: () => void;
}) {
  const t = useT();
  const [syncPlay, setSyncPlay] = useState(false);
  const finalVideoRef = useRef<HTMLVideoElement | null>(null);
  const originalVideoRef = useRef<HTMLVideoElement | null>(null);
  const syncSourceRef = useRef<"final" | "original" | null>(null);

  const canSync = mode === "side_by_side" && Boolean(finalAssetId && originalAssetId);

  useEffect(() => {
    if (!canSync) setSyncPlay(false);
  }, [canSync]);

  const mirrorPlayback = useCallback(
    (source: "final" | "original") => {
      if (!syncPlay) return;
      const from = source === "final" ? finalVideoRef.current : originalVideoRef.current;
      const to = source === "final" ? originalVideoRef.current : finalVideoRef.current;
      if (!from || !to) return;
      if (Math.abs(to.currentTime - from.currentTime) > 0.35) {
        try {
          to.currentTime = from.currentTime;
        } catch {
          // Seeking may fail while metadata is still loading.
        }
      }
      if (from.paused && !to.paused) to.pause();
      if (!from.paused && to.paused) void to.play().catch(() => undefined);
    },
    [syncPlay]
  );

  function handleTimeUpdate(source: "final" | "original") {
    if (!syncPlay) return;
    if (syncSourceRef.current && syncSourceRef.current !== source) return;
    syncSourceRef.current = source;
    mirrorPlayback(source);
    window.setTimeout(() => {
      if (syncSourceRef.current === source) syncSourceRef.current = null;
    }, 120);
  }

  function handlePlayPause(source: "final" | "original") {
    if (!syncPlay) return;
    mirrorPlayback(source);
  }

  const deltaLabel =
    compareDiff?.durationDeltaSeconds == null
      ? null
      : `${compareDiff.durationDeltaSeconds > 0 ? "+" : ""}${compareDiff.durationDeltaSeconds}s`;
  const originalDurationLabel = compareDiff
    ? formatRenderDuration(compareDiff.originalDurationSeconds)
    : null;
  const finalDurationLabel = compareDiff
    ? formatRenderDuration(compareDiff.finalDurationSeconds)
    : null;
  const durationValue =
    originalDurationLabel && finalDurationLabel
      ? originalDurationLabel === finalDurationLabel
        ? `${finalDurationLabel}${deltaLabel ? ` (${deltaLabel})` : ""}`
        : `${originalDurationLabel}→${finalDurationLabel}${deltaLabel ? ` (${deltaLabel})` : ""}`
      : null;

  return (
    <section className="fr-stage compare-viewer">
      <div className="fr-stage__toolbar compare-toolbar">
        <div className="fr-stage__intro">
          <h2>{t("finalReviewStates.compareTitle")}</h2>
          <p>{t("finalReviewStates.compareBody")}</p>
        </div>
        <div className="compare-toolbar__controls">
          <div
            className="fr-segmented compare-mode-buttons compare-toolbar__modes"
            role="group"
            aria-label={t("finalReviewStates.compareModeLabel")}
          >
            <button
              type="button"
              className={mode === "side_by_side" ? "active" : ""}
              onClick={() => onModeChange("side_by_side")}
            >
              <CompareToolbarIcon kind="split" />
              {t("finalReviewStates.compareSideBySide")}
            </button>
            <button
              type="button"
              className={mode === "final_only" ? "active" : ""}
              onClick={() => onModeChange("final_only")}
            >
              <CompareToolbarIcon kind="final" />
              {t("finalReviewStates.compareFinal")}
            </button>
            <button
              type="button"
              className={mode === "original_only" ? "active" : ""}
              onClick={() => onModeChange("original_only")}
            >
              <CompareToolbarIcon kind="original" />
              {t("finalReviewStates.compareOriginal")}
            </button>
          </div>
          <div className="compare-toolbar__tools">
            <button type="button" className="compare-tool" onClick={onQuickToggle}>
              <CompareToolbarIcon kind="switch" />
              {t("finalReviewStates.compareQuickSwitch")}
            </button>
            {canSync ? (
              <button
                type="button"
                className={`compare-tool compare-sync${syncPlay ? " is-active" : ""}`}
                aria-pressed={syncPlay}
                onClick={() => setSyncPlay((current) => !current)}
              >
                <CompareToolbarIcon kind="link" />
                {syncPlay ? t("finalReviewStates.compareSyncOn") : t("finalReviewStates.compareSyncOff")}
              </button>
            ) : null}
          </div>
        </div>
      </div>
      {compareDiff ? (
        <ul className="final-review-compare-diff" aria-label={t("finalReviewStates.compareDiffLabel")}>
          <li
            className="final-review-compare-diff__item is-duration"
            title={t("finalReviewStates.compareDiffDuration")}
          >
            <CompareDiffIcon kind="duration" />
            <strong>{durationValue}</strong>
          </li>
          <li
            className="final-review-compare-diff__item is-subtitle"
            title={t("finalReviewStates.compareDiffSubtitle")}
          >
            <CompareDiffIcon kind="subtitle" />
            <strong>
              {compareDiff.subtitleBurned
                ? t("finalReviewStates.compareDiffSubtitleYes")
                : t("finalReviewStates.compareDiffSubtitleNo")}
            </strong>
          </li>
          {compareDiff.resolution ? (
            <li
              className="final-review-compare-diff__item is-resolution"
              title={t("finalReviewStates.compareDiffResolution")}
            >
              <CompareDiffIcon kind="resolution" />
              <strong>{compareDiff.resolution.replace("x", "×")}</strong>
            </li>
          ) : null}
          {compareDiff.sizeLabel ? (
            <li
              className="final-review-compare-diff__item is-size"
              title={t("finalReviewStates.compareDiffSize")}
            >
              <CompareDiffIcon kind="size" />
              <strong>{compareDiff.sizeLabel}</strong>
            </li>
          ) : null}
        </ul>
      ) : null}
      <div className={`compare-video-grid mode-${mode}`}>
        {mode !== "original_only" ? (
          <AuthenticatedVideoPane
            title={t("finalReviewStates.compareFinalPane")}
            assetId={finalAssetId}
            tone="final"
            videoRef={finalVideoRef}
            onPlay={() => handlePlayPause("final")}
            onPause={() => handlePlayPause("final")}
            onTimeUpdate={() => handleTimeUpdate("final")}
          />
        ) : null}
        {mode !== "final_only" ? (
          <AuthenticatedVideoPane
            title={t("finalReviewStates.compareOriginalPane")}
            assetId={originalAssetId}
            tone="original"
            videoRef={originalVideoRef}
            onPlay={() => handlePlayPause("original")}
            onPause={() => handlePlayPause("original")}
            onTimeUpdate={() => handleTimeUpdate("original")}
          />
        ) : null}
      </div>
    </section>
  );
}

function CompareDiffIcon({ kind }: { kind: "duration" | "subtitle" | "resolution" | "size" }) {
  if (kind === "duration") {
    return (
      <svg aria-hidden="true" className="compare-diff__icon" viewBox="0 0 24 24">
        <path
          d="M12 3.6a8.4 8.4 0 1 1 0 16.8 8.4 8.4 0 0 1 0-16.8Zm0 2a1 1 0 0 0-1 1V12a1 1 0 0 0 .5.9l3.4 2a1 1 0 1 0 1-1.7L13 11.4V6.6a1 1 0 0 0-1-1Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (kind === "subtitle") {
    return (
      <svg aria-hidden="true" className="compare-diff__icon" viewBox="0 0 24 24">
        <path
          d="M5.2 5.5h13.6A1.8 1.8 0 0 1 20.6 7.3v9.4a1.8 1.8 0 0 1-1.8 1.8H5.2a1.8 1.8 0 0 1-1.8-1.8V7.3a1.8 1.8 0 0 1 1.8-1.8Zm1.6 8.2h4.2a.9.9 0 1 1 0 1.8H6.8a.9.9 0 1 1 0-1.8Zm5.8 0h4.6a.9.9 0 1 1 0 1.8h-4.6a.9.9 0 1 1 0-1.8ZM6.8 10.2h10.4a.9.9 0 1 1 0 1.8H6.8a.9.9 0 1 1 0-1.8Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (kind === "resolution") {
    return (
      <svg aria-hidden="true" className="compare-diff__icon" viewBox="0 0 24 24">
        <path
          d="M4.8 6.2h14.4A1.6 1.6 0 0 1 20.8 7.8v8.4a1.6 1.6 0 0 1-1.6 1.6H4.8A1.6 1.6 0 0 1 3.2 16.2V7.8A1.6 1.6 0 0 1 4.8 6.2Zm1.5 2v6.8h11.4V8.2H6.3Zm3.2 9.4h5a.9.9 0 1 1 0 1.8h-5a.9.9 0 1 1 0-1.8Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="compare-diff__icon" viewBox="0 0 24 24">
      <path
        d="M7.2 4.6h6.1l4.5 4.5v10.3a1.6 1.6 0 0 1-1.6 1.6H7.2a1.6 1.6 0 0 1-1.6-1.6V6.2a1.6 1.6 0 0 1 1.6-1.6Zm5.4 1.7v3.2h3.2l-3.2-3.2ZM8.4 13.2h7.2a.9.9 0 1 1 0 1.8H8.4a.9.9 0 1 1 0-1.8Zm0 3.1h5.2a.9.9 0 1 1 0 1.8H8.4a.9.9 0 1 1 0-1.8Z"
        fill="currentColor"
      />
    </svg>
  );
}

function CompareToolbarIcon({ kind }: { kind: "split" | "final" | "original" | "switch" | "link" }) {
  if (kind === "split") {
    return (
      <svg aria-hidden="true" className="compare-mode__icon" viewBox="0 0 24 24">
        <path
          d="M4.8 5.5h5.4a1.2 1.2 0 0 1 1.2 1.2v10.6a1.2 1.2 0 0 1-1.2 1.2H4.8a1.2 1.2 0 0 1-1.2-1.2V6.7a1.2 1.2 0 0 1 1.2-1.2Zm9 0h5.4a1.2 1.2 0 0 1 1.2 1.2v10.6a1.2 1.2 0 0 1-1.2 1.2h-5.4a1.2 1.2 0 0 1-1.2-1.2V6.7a1.2 1.2 0 0 1 1.2-1.2Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (kind === "final") {
    return (
      <svg aria-hidden="true" className="compare-mode__icon" viewBox="0 0 24 24">
        <path
          d="M12 3.8a8.2 8.2 0 1 1 0 16.4A8.2 8.2 0 0 1 12 3.8Zm3.6 5.6a1 1 0 0 0-1.4-.1l-3.9 3.5-1.4-1.4a1 1 0 1 0-1.4 1.4l2.1 2.1a1 1 0 0 0 1.4 0l4.6-4.2a1 1 0 0 0 0-1.3Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (kind === "original") {
    return (
      <svg aria-hidden="true" className="compare-mode__icon" viewBox="0 0 24 24">
        <path
          d="M6.2 4.8h11.6A1.8 1.8 0 0 1 19.6 6.6v10.8a1.8 1.8 0 0 1-1.8 1.8H6.2a1.8 1.8 0 0 1-1.8-1.8V6.6a1.8 1.8 0 0 1 1.8-1.8Zm1.6 2.2v10h8.4v-10H7.8Zm1.7 2.2h5a.9.9 0 1 1 0 1.8h-5a.9.9 0 1 1 0-1.8Zm0 3.2h5a.9.9 0 1 1 0 1.8h-5a.9.9 0 1 1 0-1.8Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (kind === "switch") {
    return (
      <svg aria-hidden="true" className="compare-mode__icon" viewBox="0 0 24 24">
        <path
          d="M7.2 7.2h7.1l-1.5-1.5a1 1 0 1 1 1.4-1.4l3.2 3.2a1 1 0 0 1 0 1.4l-3.2 3.2a1 1 0 1 1-1.4-1.4l1.5-1.5H7.2a1 1 0 1 1 0-2Zm9.6 9.6H9.7l1.5 1.5a1 1 0 1 1-1.4 1.4l-3.2-3.2a1 1 0 0 1 0-1.4l3.2-3.2a1 1 0 1 1 1.4 1.4l-1.5 1.5h7.1a1 1 0 1 1 0 2Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="compare-mode__icon" viewBox="0 0 24 24">
      <path
        d="M9.4 8.2a2.8 2.8 0 0 1 4 0l.7.7a1 1 0 1 1-1.4 1.4l-.7-.7a.8.8 0 0 0-1.2 0l-3.2 3.2a.8.8 0 0 0 0 1.2l.7.7a1 1 0 1 1-1.4 1.4l-.7-.7a2.8 2.8 0 0 1 0-4l3.2-3.2Zm5.2 1.1a1 1 0 0 1 1.4 0l.7.7a2.8 2.8 0 0 1 0 4l-3.2 3.2a2.8 2.8 0 0 1-4 0l-.7-.7a1 1 0 1 1 1.4-1.4l.7.7a.8.8 0 0 0 1.2 0l3.2-3.2a.8.8 0 0 0 0-1.2l-.7-.7a1 1 0 0 1 0-1.4Z"
        fill="currentColor"
      />
    </svg>
  );
}

function AuthenticatedVideoPane({
  title,
  assetId,
  tone,
  videoRef,
  onPlay,
  onPause,
  onTimeUpdate
}: {
  title: string;
  assetId: string | null;
  tone: "final" | "original";
  videoRef?: MutableRefObject<HTMLVideoElement | null>;
  onPlay?: () => void;
  onPause?: () => void;
  onTimeUpdate?: () => void;
}) {
  const t = useT();
  const objectUrlRef = useRef<string | null>(null);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">(assetId ? "loading" : "idle");

  useEffect(() => {
    let cancelled = false;

    function revokeCurrentObjectUrl() {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    }

    async function loadPreview() {
      revokeCurrentObjectUrl();
      setPlaybackUrl(null);

      if (!assetId) {
        setLoadState("idle");
        return;
      }

      setLoadState("loading");
      try {
        const objectUrl = await fetchMediaAssetObjectUrl(assetId);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        objectUrlRef.current = objectUrl;
        setPlaybackUrl(objectUrl);
        setLoadState("ready");
      } catch {
        if (!cancelled) {
          setPlaybackUrl(null);
          setLoadState("error");
        }
      }
    }

    void loadPreview();
    return () => {
      cancelled = true;
      revokeCurrentObjectUrl();
    };
  }, [assetId]);

  return (
    <div className={`compare-pane ${tone}`}>
      <div className="compare-pane-title">{title}</div>
      {playbackUrl && loadState === "ready" ? (
        <video
          ref={(node) => {
            if (videoRef) videoRef.current = node;
          }}
          controls
          preload="metadata"
          src={playbackUrl}
          onPlay={onPlay}
          onPause={onPause}
          onTimeUpdate={onTimeUpdate}
          onSeeked={onTimeUpdate}
        />
      ) : (
        <div className="video-unavailable">
          <span className="video-unavailable__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <rect x="3.5" y="5" width="13" height="14" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="m16.5 9 4-2v10l-4-2V9Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.5" />
              <path d="M7.2 16.8 13.8 7.2" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
            </svg>
          </span>
          <strong>
            {loadState === "loading"
              ? t("finalReviewStates.compareLoading")
              : loadState === "error"
                ? t("finalReviewStates.compareFailed")
                : t("finalReviewStates.compareUnavailable")}
          </strong>
          <span>
            {loadState === "loading"
              ? t("finalReviewStates.compareLoadingHint")
              : loadState === "error"
                ? t("finalReviewStates.compareFailedHint")
                : t("finalReviewStates.compareUnavailableHint")}
          </span>
        </div>
      )}
    </div>
  );
}
