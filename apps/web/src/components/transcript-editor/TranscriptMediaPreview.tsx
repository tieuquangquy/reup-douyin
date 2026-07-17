"use client";

import { useEffect, useRef, useState } from "react";
import { fetchMediaAssetObjectUrl } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { resolveTranscriptPreviewSource } from "../../lib/transcriptEditorPresentation";
import { formatMs } from "../../lib/transcriptEditorState";
import type { AudioAnalysisSummaryResponse, EditableSegment } from "../../types/transcript-editor";

type Props = {
  summary: AudioAnalysisSummaryResponse | null;
  selectedSegment: EditableSegment | null;
  playRequestId: number;
  joinedTtsAssetId?: string | null;
};

export function TranscriptMediaPreview({
  summary,
  selectedSegment,
  playRequestId,
  joinedTtsAssetId = null
}: Props) {
  const t = useT();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pendingPlayRef = useRef(false);
  const objectUrlRef = useRef<string | null>(null);
  const ttsObjectUrlRef = useRef<string | null>(null);
  const previewSource = resolveTranscriptPreviewSource(summary?.manifest ?? null);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">(
    previewSource ? "loading" : "idle"
  );
  const [ttsPlaybackUrl, setTtsPlaybackUrl] = useState<string | null>(null);
  const [ttsLoadState, setTtsLoadState] = useState<"idle" | "loading" | "ready" | "error">("idle");

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

      if (!previewSource) {
        setLoadState("idle");
        return;
      }

      if (previewSource.kind === "direct") {
        if (!cancelled) {
          setPlaybackUrl(previewSource.url);
          setLoadState("ready");
        }
        return;
      }

      setLoadState("loading");
      try {
        const objectUrl = await fetchMediaAssetObjectUrl(previewSource.assetId);
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
  }, [previewSource?.kind, previewSource && previewSource.kind === "media_asset" ? previewSource.assetId : null, previewSource && previewSource.kind === "direct" ? previewSource.url : null]);

  useEffect(() => {
    let cancelled = false;

    function revokeTtsObjectUrl() {
      if (ttsObjectUrlRef.current) {
        URL.revokeObjectURL(ttsObjectUrlRef.current);
        ttsObjectUrlRef.current = null;
      }
    }

    async function loadJoinedTts() {
      revokeTtsObjectUrl();
      setTtsPlaybackUrl(null);

      if (!joinedTtsAssetId) {
        setTtsLoadState("idle");
        return;
      }

      setTtsLoadState("loading");
      try {
        const objectUrl = await fetchMediaAssetObjectUrl(joinedTtsAssetId);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        ttsObjectUrlRef.current = objectUrl;
        setTtsPlaybackUrl(objectUrl);
        setTtsLoadState("ready");
      } catch {
        if (!cancelled) {
          setTtsPlaybackUrl(null);
          setTtsLoadState("error");
        }
      }
    }

    void loadJoinedTts();
    return () => {
      cancelled = true;
      revokeTtsObjectUrl();
    };
  }, [joinedTtsAssetId]);

  useEffect(() => {
    if (playRequestId > 0) {
      void seekAndPlay();
    }
  }, [playRequestId, selectedSegment?.localId, selectedSegment?.startMs, playbackUrl]);

  function seekAndPlay() {
    const video = videoRef.current;
    if (!selectedSegment || !video || !playbackUrl) return;

    const apply = () => {
      video.currentTime = selectedSegment.startMs / 1000;
      void video.play().catch(() => {
        /* autoplay may be blocked until a later user gesture */
      });
    };

    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
      apply();
      return;
    }

    pendingPlayRef.current = true;
    const onReady = () => {
      if (!pendingPlayRef.current) return;
      pendingPlayRef.current = false;
      apply();
    };
    video.addEventListener("loadedmetadata", onReady, { once: true });
  }

  const canJump = Boolean(selectedSegment && playbackUrl && loadState === "ready");

  return (
    <div className="transcript-bench-media">
      <div className="media-box">
        {playbackUrl ? (
          <video ref={videoRef} src={playbackUrl} controls preload="metadata" />
        ) : (
          <div className="transcript-bench-media__empty">
            {loadState === "loading"
              ? t("transcriptEditorBench.previewLoading")
              : loadState === "error"
                ? t("transcriptEditorBench.previewFailed")
                : t("transcriptEditorBench.noPreview")}
          </div>
        )}
      </div>
      {joinedTtsAssetId ? (
        <div className="transcript-bench-media__tts">
          <strong>{t("transcriptEditorBench.ttsNarration")}</strong>
          {ttsPlaybackUrl ? (
            <audio controls preload="metadata" src={ttsPlaybackUrl} />
          ) : (
            <p className="transcript-bench-media__tts-status">
              {ttsLoadState === "loading"
                ? t("transcriptEditorBench.ttsLoading")
                : ttsLoadState === "error"
                  ? t("transcriptEditorBench.ttsFailed")
                  : t("transcriptEditorBench.ttsEmpty")}
            </p>
          )}
        </div>
      ) : null}
      <div className="media-now">
        <strong>{t("transcriptEditorBench.currentBeat")}</strong>
        {selectedSegment ? (
          <p>
            {formatMs(selectedSegment.startMs)} – {formatMs(selectedSegment.endMs)}
          </p>
        ) : (
          <p>{t("transcriptEditorBench.noBeatSelected")}</p>
        )}
        <button type="button" onClick={() => void seekAndPlay()} disabled={!canJump}>
          {t("transcriptEditorBench.jumpToBeat")}
        </button>
      </div>
    </div>
  );
}
