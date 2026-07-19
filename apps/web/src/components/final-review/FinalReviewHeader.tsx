"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { RenderOutput, SourceVideoAssetManifest } from "../../types/final-review";
import { getRenderWarnings, isApproved, isPublishReady } from "../../lib/finalReviewState";
import { humanizeStatus } from "../../lib/statusLabels";

export function FinalReviewHeader({
  render,
  manifest,
  actionBusy,
  onRerender
}: {
  render: RenderOutput;
  manifest: SourceVideoAssetManifest | null;
  actionBusy: boolean;
  onRerender: () => void;
}) {
  const t = useT();
  const title =
    manifest?.source_video?.caption ||
    manifest?.source_video?.external_id ||
    manifest?.source_video?.source_video_external_id ||
    render.source_video_id;
  const warnings = getRenderWarnings(render);
  const approved = isApproved(render);
  const publishReady = isPublishReady(render);
  const versionLabel = render.render_version ?? `v${render.version}`;
  const readinessLabel = publishReady
    ? t("finalReviewHeader.mediaPublishReady")
    : approved
      ? t("finalReviewHeader.exportApproved")
      : t("finalReviewHeader.needsExportApproval");
  const readinessTone = publishReady || approved ? "fr-chip--good" : "fr-chip--warn";

  return (
    <header className="fr-topbar fr-topbar--compact">
      <div className="fr-topbar__main">
        <div className="fr-topbar__identity">
          <div className="fr-topbar__kicker-row">
            <span className="fr-topbar__kicker">{t("finalReviewHeader.title")}</span>
            <span className="fr-chip fr-chip--quiet">{versionLabel}</span>
            <span className={`fr-chip fr-topbar__status ${readinessTone}`}>{readinessLabel}</span>
            {warnings.length > 0 ? (
              <span className="fr-chip fr-chip--warn">
                {warnings.length} {warnings.length === 1 ? "warning" : "warnings"}
              </span>
            ) : null}
          </div>
          <h1 className="fr-topbar__title" title={typeof title === "string" ? title : undefined}>
            {title}
          </h1>
          <p className="fr-topbar__meta-quiet">{humanizeStatus(render.status)}</p>
        </div>
        <nav className="fr-topbar__actions" aria-label={t("finalReviewHeader.navLabel")}>
          <button type="button" className="fr-tool fr-tool--primary" onClick={onRerender} disabled={actionBusy}>
            {t("finalReviewHeader.rerender")}
          </button>
          <Link className="fr-tool" href={`/production/transcript-editor/${render.source_video_id}`}>
            {t("finalReviewHeader.transcriptEditor")}
          </Link>
          <Link className="fr-tool" href={`/source-videos/${render.source_video_id}/publish`}>
            {t("finalReviewHeader.publishDraft")}
          </Link>
          <Link className="fr-tool fr-tool--quiet" href="/selection/review-board">
            {t("finalReviewHeader.reviewBoard")}
          </Link>
        </nav>
      </div>
    </header>
  );
}
