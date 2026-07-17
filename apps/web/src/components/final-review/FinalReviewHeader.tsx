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

  return (
    <header className="fr-topbar">
      <div className="fr-topbar__main">
        <div className="fr-topbar__identity">
          <div className="fr-topbar__kicker-row">
            <span className="fr-topbar__kicker">{t("finalReviewHeader.title")}</span>
            <span className="fr-chip fr-chip--quiet">{versionLabel}</span>
            <span className="fr-chip fr-chip--quiet">{humanizeStatus(render.status)}</span>
            <span className={`fr-chip ${warnings.length > 0 ? "fr-chip--warn" : "fr-chip--quiet"}`}>
              {warnings.length} {warnings.length === 1 ? "warning" : "warnings"}
            </span>
          </div>
          <h1 className="fr-topbar__title" title={typeof title === "string" ? title : undefined}>
            {title}
          </h1>
        </div>
        <div className="fr-topbar__gates" aria-label={t("finalReviewHeader.gatesLabel")}>
          <span className={`fr-gate ${approved ? "fr-gate--good" : "fr-gate--warn"}`}>
            <span className="fr-gate__dot" aria-hidden="true" />
            {approved ? t("finalReviewHeader.exportApproved") : t("finalReviewHeader.needsExportApproval")}
          </span>
          <span className={`fr-gate ${publishReady ? "fr-gate--good" : "fr-gate--idle"}`}>
            <span className="fr-gate__dot" aria-hidden="true" />
            {publishReady ? t("finalReviewHeader.mediaPublishReady") : t("finalReviewHeader.notReadyForPublish")}
          </span>
        </div>
      </div>
      <nav className="fr-topbar__tools fr-nav-links" aria-label={t("finalReviewHeader.navLabel")}>
        <button type="button" className="fr-tool" onClick={onRerender} disabled={actionBusy}>
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
    </header>
  );
}
