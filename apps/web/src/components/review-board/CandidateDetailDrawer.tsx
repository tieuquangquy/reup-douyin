"use client";

import { useT } from "../../lib/i18n";
import type { Candidate } from "../../types/review-board";
import { humanizeStatus } from "../../lib/statusLabels";
import { CandidateMetricsRow } from "./CandidateMetricsRow";
import { ScoreBreakdownPanel } from "./ScoreBreakdownPanel";

type Props = {
  candidate: Candidate | null;
  onClose: () => void;
  onKeep: (candidate: Candidate) => void;
  onReject: (candidate: Candidate) => void;
  onSendToReupQueue: (candidate: Candidate) => void;
  t: (key: string) => string;
};

export function CandidateDetailDrawer({ candidate, onClose, onKeep, onReject, onSendToReupQueue, t }: Props) {
  if (!candidate) return null;

  const source = candidate.source_video;
  const metadata = source?.metadata_json ?? {};
  const thumbnailUrl = typeof metadata.thumbnail_url === "string" ? metadata.thumbnail_url : null;
  const sourceUrl = source?.source_url;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="detail-drawer" aria-label="Candidate details">
        <div className="drawer-header">
          <div>
            <h2>{source?.caption || t("reviewBoardPage.candidateDetail")}</h2>
            <p className="card-meta">
              {t("reviewBoardPage.candidateScore")} {candidate.score ?? "--"} / {candidate.score_label ?? t("reviewBoardPage.unscored")} / {humanizeStatus(candidate.status)}
            </p>
          </div>
          <button onClick={onClose}>{t("reviewBoardPage.close")}</button>
        </div>

        <div className="preview-box">
          {thumbnailUrl ? (
            <img src={thumbnailUrl} alt="" />
          ) : sourceUrl ? (
            <iframe title="Source preview" src={sourceUrl} />
          ) : (
            <div className="thumb-fallback">{t("reviewBoardPage.previewUnavailable")}</div>
          )}
        </div>

        <CandidateMetricsRow candidate={candidate} t={t} />

        <section>
          <h3>{t("reviewBoardPage.actions")}</h3>
          <div className="card-actions">
            <button className="primary" onClick={() => onKeep(candidate)}>{t("reviewBoardPage.keep")}</button>
            <button className="danger" onClick={() => onReject(candidate)}>{t("reviewBoardPage.reject")}</button>
            <button disabled={candidate.status !== "APPROVED"} onClick={() => onSendToReupQueue(candidate)}>Send to Reup Queue</button>
            <a href={`/production/transcript-editor/${candidate.source_video_id}`}>
              <button>{t("reviewBoardPage.transcriptEditor")}</button>
            </a>
            <a href={`/production/final-review/${candidate.source_video_id}`}>
              <button>{t("reviewBoardPage.finalReview")}</button>
            </a>
            {sourceUrl ? (
              <a href={sourceUrl} target="_blank" rel="noreferrer">
                <button>{t("reviewBoardPage.openSource")}</button>
              </a>
            ) : null}
          </div>
        </section>

        <section>
          <h3>{t("reviewBoardPage.included")}</h3>
          <ReasonList title={t("reviewBoardPage.included")} items={candidate.inclusion_reasons_json ?? []} />
          <ReasonList title={t("reviewBoardPage.excluded")} items={candidate.exclusion_reasons_json ?? []} />
          <ReasonList title={t("reviewBoardPage.warnings")} items={candidate.warnings_json ?? []} />
        </section>

        <section>
          <h3>{t("reviewBoardPage.scoreBreakdown")}</h3>
          <ScoreBreakdownPanel breakdown={candidate.score_breakdown_json} t={t} />
        </section>

        <section>
          <h3>{t("reviewBoardPage.metadata")}</h3>
          <div className="metrics-row">
            <span className="pill">{t("reviewBoardPage.metricSpeech")} {formatSignal(metadata.has_speech, t)}</span>
            <span className="pill">{t("reviewBoardPage.metricText")} {typeof metadata.text_density === "string" ? metadata.text_density : t("reviewBoardPage.unknown")}</span>
            <span className="pill">{t("reviewBoardPage.noDuration")} {source?.duration_seconds ? `${Math.round(source.duration_seconds)}s` : t("reviewBoardPage.unknown")}</span>
          </div>
        </section>
      </aside>
    </>
  );
}

function ReasonList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="reason-list">
      <strong>{title}</strong>
      {items.map((item) => (
        <div key={item}>{item}</div>
      ))}
    </div>
  );
}

function formatSignal(value: unknown, t: (key: string) => string): string {
  if (value === true) return t("reviewBoardPage.yes");
  if (value === false) return t("reviewBoardPage.no");
  return t("reviewBoardPage.unknown");
}
