"use client";

import { useEffect, useState } from "react";
import { useT } from "../../lib/i18n";
import { fetchMediaAssetObjectUrl } from "../../lib/api";
import { buildPostPreview, validatePublishDraft } from "../../lib/publishDraftState";
import type { EditablePublishDraft, PublishTarget } from "../../types/publish-draft";

export function PublishPreviewPanel({
  editable,
  target,
  mediaAssetId,
  platformLabel,
  accountLabel,
  accountHint
}: {
  editable: EditablePublishDraft;
  target: PublishTarget | null;
  mediaAssetId?: string | null;
  platformLabel?: string;
  accountLabel: string;
  accountHint?: string | null;
}) {
  const t = useT();
  const preview = buildPostPreview(editable);
  const errors = validatePublishDraft(editable, target);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const pageInitial = (accountLabel.trim().charAt(0) || "?").toUpperCase();

  useEffect(() => {
    let cancelled = false;
    let loadedUrl: string | null = null;
    setPlaybackUrl(null);
    if (!mediaAssetId) return undefined;
    void fetchMediaAssetObjectUrl(mediaAssetId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        loadedUrl = url;
        setPlaybackUrl(url);
      })
      .catch(() => {
        if (!cancelled) setPlaybackUrl(null);
      });
    return () => {
      cancelled = true;
      if (loadedUrl) URL.revokeObjectURL(loadedUrl);
    };
  }, [mediaAssetId]);

  return (
    <section className="publish-draft-desk__compose" aria-label={t("publishPreviewPanel.title")}>
      <header className="publish-draft-desk__phone-meta">
        <span className="publish-draft-desk__phone-avatar" aria-hidden="true">
          {pageInitial}
        </span>
        <div className="publish-draft-desk__phone-page">
          <span className="publish-draft-desk__phone-page-name">{accountLabel}</span>
          <span className="publish-draft-desk__phone-page-id">
            {t("publishPreviewPanel.justNow")}
            <span aria-hidden="true"> · </span>
            {t("publishPreviewPanel.visibilityPublic")}
            {accountHint ? ` · ${accountHint}` : ""}
          </span>
        </div>
        {platformLabel ? <span className="visually-hidden">{platformLabel}</span> : null}
        <span className={`publish-draft-desk__chip${errors.length > 0 ? " is-warn" : " is-quiet"}`}>
          {preview.length} {t("publishPreviewPanel.chars")}
        </span>
      </header>
      <pre className="publish-draft-desk__phone-copy">{preview || t("publishPreviewPanel.placeholder")}</pre>
      <div className="publish-draft-desk__phone">
        {playbackUrl ? (
          <video
            className="publish-draft-desk__compose-video"
            src={playbackUrl}
            controls
            playsInline
            preload="metadata"
          />
        ) : (
          <div className="publish-draft-desk__phone-empty">{t("publishMediaSummary.notLoaded")}</div>
        )}
      </div>
      <div className="publish-draft-desk__phone-react" aria-hidden="true">
        <span>
          <svg className="publish-draft-desk__phone-react-icon" viewBox="0 0 20 20">
            <path
              d="M7.4 17.2V9L11.8 4.2a1.6 1.6 0 0 1 2.8 1.5L13.8 9h3.2a1.7 1.7 0 0 1 1.7 2l-1 5.1a1.9 1.9 0 0 1-1.9 1.5H8.6a1.2 1.2 0 0 1-1.2-1.4ZM4.4 9h2.4v8.2H5.2A.8.8 0 0 1 4.4 16.4Z"
              fill="none"
              stroke="currentColor"
              strokeLinejoin="round"
              strokeWidth="1.6"
            />
          </svg>
          {t("publishPreviewPanel.like")}
        </span>
        <span>
          <svg className="publish-draft-desk__phone-react-icon" viewBox="0 0 20 20">
            <path
              d="M5.2 4.6h9.6A2.2 2.2 0 0 1 17 6.8v5.2a2.2 2.2 0 0 1-2.2 2.2H9.4L5.2 17V14.2H5A2.2 2.2 0 0 1 2.8 12V6.8A2.2 2.2 0 0 1 5 4.6Z"
              fill="none"
              stroke="currentColor"
              strokeLinejoin="round"
              strokeWidth="1.6"
            />
          </svg>
          {t("publishPreviewPanel.comment")}
        </span>
        <span>
          <svg className="publish-draft-desk__phone-react-icon" viewBox="0 0 20 20">
            <path
              d="M11.2 4.6H16v4.8M16 4.6 8.8 11.8M7.2 6.4H5.6A1.6 1.6 0 0 0 4 8v6.6A1.6 1.6 0 0 0 5.6 16.2h7.2A1.6 1.6 0 0 0 14.4 14.6v-2"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.6"
            />
          </svg>
          {t("publishPreviewPanel.share")}
        </span>
      </div>
      {errors.length > 0 ? (
        <ul className="warning-list">
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
