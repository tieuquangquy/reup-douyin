"use client";

import type { Candidate } from "../../types/review-board";
import { getReviewCandidateMetadata } from "../../lib/reviewCandidateMetadata";
import { humanizeStatus } from "../../lib/statusLabels";
import { CandidateMetricsRow } from "./CandidateMetricsRow";
import { CandidateRiskFlags } from "./CandidateRiskFlags";
import { CandidateScoreBadge } from "./CandidateScoreBadge";

type Props = {
  candidate: Candidate;
  selected: boolean;
  onToggleSelection: () => void;
  onOpenDetails: () => void;
  onKeep: () => void;
  onReject: () => void;
  t: (key: string) => string;
};

export function CandidateCard({
  candidate,
  selected,
  onToggleSelection,
  onOpenDetails,
  onKeep,
  onReject,
  t
}: Props) {
  const source = candidate.source_video;
  const reviewMetadata = getReviewCandidateMetadata(candidate);
  const metadata = source?.metadata_json ?? {};
  const thumbnailUrl = stringValue(metadata.thumbnail_url);
  const title = source?.caption || stringValue(metadata.title) || t("reviewBoardPage.untitled");
  const hashtags = arrayValue(metadata.hashtags).slice(0, 3);

  return (
    <article className={`candidate-card${selected ? " selected" : ""}`}>
      <div className="thumb-wrap">
        <input
          aria-label={t("reviewBoardPage.selectCandidate")}
          className="card-select"
          type="checkbox"
          checked={selected}
          onChange={onToggleSelection}
        />
        {thumbnailUrl ? (
          <img src={thumbnailUrl} alt="" />
        ) : (
          <div className="thumb-fallback">{t("reviewBoardPage.previewUnavailableCard")}</div>
        )}
        <CandidateScoreBadge score={candidate.score} label={candidate.score_label} t={t} />
      </div>

      <div className="card-content">
        <div>
          <h2 className="card-title">{truncate(title, 96)}</h2>
          <p className="card-meta">
            {reviewMetadata.postedDisplay ?? "No date"} / {reviewMetadata.durationText ?? formatDuration(source?.duration_seconds)} / {humanizeStatus(candidate.status)}
          </p>
        </div>

        <CandidateMetricsRow candidate={candidate} t={t} />

        <div className="signal-row">
          <span className={signalClass(metadata.has_speech)}>{t("reviewBoardPage.metricSpeech")}: {signalText(metadata.has_speech, t)}</span>
          <span className="pill">{t("reviewBoardPage.metricText")}: {stringValue(metadata.text_density) || t("reviewBoardPage.unknown")}</span>
          {hashtags.map((tag) => (
            <span className="pill" key={tag}>#{tag}</span>
          ))}
        </div>

        <CandidateRiskFlags candidate={candidate} t={t} />

        <div className="reason-list">
          {(candidate.inclusion_reasons_json ?? []).slice(0, 2).map((reason) => (
            <div key={reason}>{t("reviewBoardPage.included")}: {reason}</div>
          ))}
          {(candidate.warnings_json ?? []).slice(0, 1).map((warning) => (
            <div key={warning}>{t("reviewBoardPage.warnings")}: {warning}</div>
          ))}
        </div>

        <div className="card-actions">
          <button className="primary" onClick={onKeep}>{t("reviewBoardPage.keep")}</button>
          <button className="danger" onClick={onReject}>{t("reviewBoardPage.reject")}</button>
          <button onClick={onOpenDetails}>{t("reviewBoardPage.details")}</button>
          <a href={`/production/transcript-editor/${candidate.source_video_id}`}>
            <button>{t("reviewBoardPage.transcript")}</button>
          </a>
          <a href={`/production/final-review/${candidate.source_video_id}`}>
            <button>{t("reviewBoardPage.finalReview")}</button>
          </a>
          {source?.source_url ? (
            <a href={source.source_url} target="_blank" rel="noreferrer">
              <button>{t("reviewBoardPage.preview")}</button>
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function signalText(value: unknown, t: (key: string) => string): string {
  if (value === true) return t("reviewBoardPage.yes");
  if (value === false) return t("reviewBoardPage.no");
  return t("reviewBoardPage.unknown");
}

function signalClass(value: unknown): string {
  if (value === true) return "pill good";
  if (value === false) return "pill warn";
  return "pill";
}

function formatDuration(value: number | null | undefined): string {
  if (!value) return "No duration";
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}
