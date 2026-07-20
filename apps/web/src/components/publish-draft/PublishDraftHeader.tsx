"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import type { EditablePublishDraft, PublishDraft } from "../../types/publish-draft";
import { humanizeStatus } from "../../lib/statusLabels";

export function PublishDraftHeader({
  draft,
  editable,
  dirty,
  saving,
  errors,
  onSave,
  onDiscard,
  onMarkReady
}: {
  draft: PublishDraft | null;
  editable: EditablePublishDraft | null;
  dirty: boolean;
  saving: boolean;
  errors: string[];
  onSave: () => void;
  onDiscard: () => void;
  onMarkReady: () => void;
}) {
  const t = useT();
  return (
    <header className="publish-header">
      <div>
        <p className="eyebrow">{t("publishDraftHeader.eyebrow")}</p>
        <h1>{editable?.title || t("publishDraftHeader.defaultTitle")}</h1>
        <p>{draft ? `${draft.target_platform} / ${humanizeStatus(draft.status)} / v${draft.version}` : t("publishDraftHeader.createDraftHint")}</p>
      </div>
      <div className="publish-header-actions">
        <Link href={draft ? `/production/final-review/${draft.source_video_id}` : "/selection/review-board"}>{t("publishDraftHeader.finalReview")}</Link>
        <Link href="/publishing/drafts">{t("nav.publishDrafts")}</Link>
        <button onClick={onDiscard} disabled={!dirty || saving}>{t("publishDraftHeader.discard")}</button>
        <button onClick={onSave} disabled={!dirty || saving || !draft}>{t("publishDraftHeader.saveDraft")}</button>
        <button className="primary" onClick={onMarkReady} disabled={saving || !draft || errors.length > 0}>{t("publishDraftHeader.markDraftReady")}</button>
      </div>
    </header>
  );
}
