"use client";

import { useT } from "../../lib/i18n";
import type { EditablePublishDraft } from "../../types/publish-draft";

export function CaptionEditor({
  editable,
  disabled,
  onChange
}: {
  editable: EditablePublishDraft;
  disabled: boolean;
  onChange: (patch: Partial<EditablePublishDraft>) => void;
}) {
  const t = useT();
  return (
    <section className="publish-panel">
      <h2>{t("captionEditor.title")}</h2>
      <label className="publish-field">
        {t("captionEditor.caption")}
        <textarea value={editable.caption} onChange={(event) => onChange({ caption: event.target.value })} disabled={disabled} rows={6} />
      </label>
      <label className="publish-field">
        {t("captionEditor.cta")}
        <textarea value={editable.ctaText} onChange={(event) => onChange({ ctaText: event.target.value })} disabled={disabled} rows={3} />
      </label>
      <label className="publish-field">
        {t("captionEditor.internalNotes")}
        <textarea value={editable.notes} onChange={(event) => onChange({ notes: event.target.value })} disabled={disabled} rows={3} />
      </label>
    </section>
  );
}
