"use client";

import { useT } from "../../lib/i18n";
import type { RenderOutput, SourceVideoAssetManifest } from "../../types/final-review";
import { humanizeStatus } from "../../lib/statusLabels";
import { AsyncButton } from "../shared/AsyncButton";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";

export function FinalReviewHeader({
  render,
  manifest,
  actionBusy,
  rerenderPending,
  onRerender
}: {
  render: RenderOutput;
  manifest: SourceVideoAssetManifest | null;
  actionBusy: boolean;
  rerenderPending: boolean;
  onRerender: () => void;
}) {
  const t = useT();
  const title =
    manifest?.source_video?.caption ||
    manifest?.source_video?.external_id ||
    manifest?.source_video?.source_video_external_id ||
    render.source_video_id;
  const versionLabel = render.render_version ?? `v${render.version}`;
  const statusLabel = humanizeStatus(render.status);
  const statusTone =
    render.status === "APPROVED" || render.status === "READY_FOR_REVIEW"
      ? "is-good"
      : render.status === "FAILED"
        ? "is-warn"
        : "is-quiet";

  return (
    <header className="fr-topbar fr-topbar--compact fr-topbar--dossier">
      <div className="fr-topbar__toolbar">
        <div className="fr-topbar__lead">
          <span className="fr-topbar__kicker">{t("finalReviewHeader.title")}</span>
          <p className="fr-topbar__meta">
            <span className={`fr-topbar__meta-status ${statusTone}`}>{statusLabel}</span>
            <span className="fr-topbar__meta-sep" aria-hidden="true">
              ·
            </span>
            <span className="fr-topbar__meta-version">{versionLabel}</span>
          </p>
        </div>
        <nav className="fr-topbar__actions" aria-label={t("finalReviewHeader.pageActionsLabel")}>
          <AsyncButton
            className="fr-tool fr-tool--quiet"
            leadingIcon={<WorkItemActionIcon className="fr-tool__icon" kind="retry" />}
            pending={rerenderPending}
            pendingLabel={t("finalReviewHeader.rerender")}
            onClick={onRerender}
            disabled={actionBusy}
          >
            {t("finalReviewHeader.rerender")}
          </AsyncButton>
        </nav>
      </div>
      <div className="fr-topbar__main">
        <div className="fr-topbar__identity">
          <h1 className="fr-topbar__title" title={typeof title === "string" ? title : undefined}>
            {title}
          </h1>
        </div>
      </div>
    </header>
  );
}
