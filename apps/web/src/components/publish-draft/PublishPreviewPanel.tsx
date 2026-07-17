"use client";

import { useT } from "../../lib/i18n";
import { buildPostPreview, validatePublishDraft } from "../../lib/publishDraftState";
import type { EditablePublishDraft, PublishTarget } from "../../types/publish-draft";

export function PublishPreviewPanel({
  editable,
  target
}: {
  editable: EditablePublishDraft;
  target: PublishTarget | null;
}) {
  const t = useT();
  const preview = buildPostPreview(editable);
  const errors = validatePublishDraft(editable, target);

  return (
    <section className="publish-panel">
      <div className="panel-heading">
        <h2>{t("publishPreviewPanel.title")}</h2>
        <span className={`pill ${errors.length > 0 ? "warn" : "good"}`}>{preview.length} {t("publishPreviewPanel.chars")}</span>
      </div>
      <pre className="post-preview">{preview || t("publishPreviewPanel.placeholder")}</pre>
      {errors.length > 0 ? (
        <ul className="warning-list">
          {errors.map((error) => <li key={error}>{error}</li>)}
        </ul>
      ) : null}
    </section>
  );
}
