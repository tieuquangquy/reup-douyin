"use client";

import { useEffect, useRef, useState } from "react";
import { fetchMediaAssetObjectUrl } from "../../lib/api";
import type { CompareMode } from "../../types/final-review";

export function FinalCompareViewer({
  mode,
  finalAssetId,
  originalAssetId,
  onModeChange,
  onQuickToggle
}: {
  mode: CompareMode;
  finalAssetId: string | null;
  originalAssetId: string | null;
  onModeChange: (mode: CompareMode) => void;
  onQuickToggle: () => void;
}) {
  return (
    <section className="fr-stage compare-viewer">
      <div className="fr-stage__toolbar compare-toolbar">
        <div className="fr-stage__intro">
          <h2>Compare output</h2>
          <p>Check narration, burned-in subtitles, and timing before approving.</p>
        </div>
        <div className="fr-segmented compare-mode-buttons" role="group" aria-label="Compare mode">
          <button type="button" className={mode === "side_by_side" ? "active" : ""} onClick={() => onModeChange("side_by_side")}>
            Side by side
          </button>
          <button type="button" className={mode === "final_only" ? "active" : ""} onClick={() => onModeChange("final_only")}>
            Final
          </button>
          <button type="button" className={mode === "original_only" ? "active" : ""} onClick={() => onModeChange("original_only")}>
            Original
          </button>
          <button type="button" onClick={onQuickToggle}>
            Quick switch
          </button>
        </div>
      </div>
      <div className={`compare-video-grid mode-${mode}`}>
        {mode !== "original_only" ? (
          <AuthenticatedVideoPane title="Final render" assetId={finalAssetId} tone="final" />
        ) : null}
        {mode !== "final_only" ? (
          <AuthenticatedVideoPane title="Original source" assetId={originalAssetId} tone="original" />
        ) : null}
      </div>
    </section>
  );
}

function AuthenticatedVideoPane({
  title,
  assetId,
  tone
}: {
  title: string;
  assetId: string | null;
  tone: "final" | "original";
}) {
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
        <video controls preload="metadata" src={playbackUrl} />
      ) : (
        <div className="video-unavailable">
          <strong>
            {loadState === "loading" ? "Loading preview…" : loadState === "error" ? "Preview failed to load" : "Preview unavailable"}
          </strong>
          <span>
            {loadState === "loading"
              ? "Fetching protected media with your session…"
              : loadState === "error"
                ? "Could not authorize or download this media asset. Refresh and try again."
                : "This asset is not streamable yet. Check the asset manifest or rerun the related pipeline."}
          </span>
        </div>
      )}
    </div>
  );
}
