"use client";

import { useT } from "../../lib/i18n";
import type { RenderOutput, SourceVideoAssetManifest } from "../../types/final-review";
import type { PublishDraft } from "../../types/publish-draft";
import { humanizeStatus } from "../../lib/statusLabels";

export function PublishMediaSummary({
  render,
  manifest,
  draft
}: {
  render: RenderOutput | null;
  manifest: SourceVideoAssetManifest | null;
  draft: PublishDraft | null;
}) {
  const t = useT();
  return (
    <section className="publish-panel">
      <h2>{t("publishMediaSummary.title")}</h2>
      <dl className="metadata-list">
        <div><dt>{t("publishMediaSummary.sourceVideo")}</dt><dd>{manifest?.source_video?.caption || manifest?.source_video?.external_id || draft?.source_video_id || t("publishMediaSummary.unknown")}</dd></div>
        <div><dt>{t("publishMediaSummary.render")}</dt><dd>{render?.render_version ?? draft?.render_output_id ?? t("publishMediaSummary.notLoaded")}</dd></div>
        <div><dt>{t("publishMediaSummary.renderStatus")}</dt><dd>{humanizeStatus(render?.status)}</dd></div>
        <div><dt>{t("publishMediaSummary.draftStatus")}</dt><dd>{draft ? humanizeStatus(draft.status) : t("publishMediaSummary.notCreated")}</dd></div>
        <div><dt>{t("publishMediaSummary.output")}</dt><dd>{render?.width && render.height ? `${render.width}x${render.height}` : t("publishMediaSummary.unknown")} / {render?.output_format ?? t("publishMediaSummary.unknown")}</dd></div>
      </dl>
    </section>
  );
}
