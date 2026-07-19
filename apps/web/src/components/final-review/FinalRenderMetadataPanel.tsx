"use client";

import { useT } from "../../lib/i18n";
import { humanizeStatus } from "../../lib/statusLabels";
import type { RenderOutput, SourceVideoAssetManifest } from "../../types/final-review";
import {
  formatBytes,
  formatFps,
  formatRenderDuration,
  formatResolution,
  resolveRenderTechSpecs
} from "../../lib/finalReviewState";

export function FinalRenderMetadataPanel({
  render,
  manifest = null
}: {
  render: RenderOutput;
  manifest?: SourceVideoAssetManifest | null;
}) {
  const t = useT();
  const specs = resolveRenderTechSpecs(render, manifest);

  return (
    <section className="final-panel fr-info" aria-label={t("finalReviewInfo.title")}>
      <div className="fr-info__head">
        <h2>{t("finalReviewInfo.title")}</h2>
        <span className="pill">{specs.output_format ?? "—"}</span>
      </div>
      <p className="fr-info__hint">{t("finalReviewInfo.hintShort")}</p>
      <dl className="metadata-list fr-info__list">
        <InfoRow label={t("finalReviewInfo.status")} value={humanizeStatus(specs.status)} />
        <InfoRow
          label={t("finalReviewInfo.resolution")}
          value={formatResolution(specs.width, specs.height)}
        />
        <InfoRow label={t("finalReviewInfo.fps")} value={formatFps(specs.fps)} />
        <InfoRow
          label={t("finalReviewInfo.duration")}
          value={specs.duration_seconds != null ? formatRenderDuration(specs.duration_seconds) : null}
        />
        <InfoRow label={t("finalReviewInfo.size")} value={formatBytes(specs.size_bytes)} />
        <InfoRow label={t("finalReviewInfo.audioStrategy")} value={specs.audio_strategy} />
        <InfoRow
          label={t("finalReviewInfo.subtitleBurned")}
          value={specs.subtitle_burned ? t("finalReviewInfo.yes") : t("finalReviewInfo.no")}
        />
        <InfoRow label={t("finalReviewInfo.renderVersion")} value={specs.render_version} />
        <InfoRow label={t("finalReviewInfo.videoCodec")} value={specs.video_codec} />
        <InfoRow label={t("finalReviewInfo.audioCodec")} value={specs.audio_codec} />
        <InfoRow
          label={t("finalReviewInfo.jobId")}
          value={specs.job_id}
          emptyHint={t("finalReviewInfo.jobIdMissing")}
        />
        <InfoRow label={t("finalReviewInfo.startedAt")} value={formatDate(specs.started_at)} />
        <InfoRow label={t("finalReviewInfo.finishedAt")} value={formatDate(specs.finished_at)} />
        <InfoRow label={t("finalReviewInfo.approvedAt")} value={formatDate(specs.approved_at)} />
        <InfoRow
          label={t("finalReviewInfo.publishReadyAt")}
          value={formatDate(specs.publish_ready_at)}
          emptyHint={t("finalReviewInfo.publishReadyNotSet")}
        />
      </dl>
    </section>
  );
}

function InfoRow({
  label,
  value,
  emptyHint
}: {
  label: string;
  value: string | null | undefined;
  emptyHint?: string;
}) {
  const display = value && value.trim().length > 0 ? value : emptyHint ?? "—";
  return (
    <div>
      <dt>{label}</dt>
      <dd>{display}</dd>
    </div>
  );
}

function formatDate(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
