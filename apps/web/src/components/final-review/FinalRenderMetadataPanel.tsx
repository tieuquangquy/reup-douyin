import type { RenderOutput } from "../../types/final-review";
import { formatRenderDuration, getFinalReviewMetadata } from "../../lib/finalReviewState";

export function FinalRenderMetadataPanel({ render }: { render: RenderOutput }) {
  const finalReview = getFinalReviewMetadata(render);

  return (
    <section className="final-panel">
      <div className="panel-heading">
        <h2>Render metadata</h2>
        <span className="pill">{render.output_format ?? "unknown"}</span>
      </div>
      <dl className="metadata-list">
        <div><dt>Resolution</dt><dd>{render.width && render.height ? `${render.width}x${render.height}` : "unknown"}</dd></div>
        <div><dt>FPS</dt><dd>{render.fps ?? "unknown"}</dd></div>
        <div><dt>Duration</dt><dd>{formatRenderDuration(render.duration_seconds)}</dd></div>
        <div><dt>Audio strategy</dt><dd>{render.audio_strategy ?? "unknown"}</dd></div>
        <div><dt>Subtitle burned</dt><dd>{render.subtitle_burned ? "yes" : "no"}</dd></div>
        <div><dt>Render version</dt><dd>{render.render_version ?? `v${render.version}`}</dd></div>
        <div><dt>Video codec</dt><dd>{render.video_codec ?? "unknown"}</dd></div>
        <div><dt>Audio codec</dt><dd>{render.audio_codec ?? "unknown"}</dd></div>
        <div><dt>Approved at</dt><dd>{formatDate(finalReview.approved_at)}</dd></div>
        <div><dt>Media publish-ready at</dt><dd>{formatDate(finalReview.publish_ready_at)}</dd></div>
      </dl>
    </section>
  );
}

function formatDate(value: unknown): string {
  return typeof value === "string" && value.length > 0 ? new Date(value).toLocaleString() : "not set";
}
