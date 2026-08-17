"use client";

import { useT } from "../../lib/i18n";
import type { EditablePublishDraft } from "../../types/publish-draft";

export function CaptionEditor({
  editable,
  disabled,
  remainingChars,
  onChange
}: {
  editable: EditablePublishDraft;
  disabled: boolean;
  remainingChars: number | null;
  onChange: (patch: Partial<EditablePublishDraft>) => void;
}) {
  const t = useT();
  return (
    <section className="publish-panel publish-draft-desk__copy-block">
      <header className="publish-draft-desk__copy-head">
        <h2 className="publish-draft-desk__heading">
          <svg className="publish-draft-desk__heading-icon" viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M4.8 5.2h10.4M4.8 10h10.4M4.8 14.8h6.6"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeWidth="1.6"
            />
          </svg>
          {t("captionEditor.title")}
        </h2>
        {remainingChars != null ? (
          <span className={`publish-draft-desk__chip${remainingChars < 0 ? " is-warn" : " is-ready"}`}>
            {remainingChars}
          </span>
        ) : null}
      </header>
      <label className="publish-field">
        <span className="visually-hidden">{t("captionEditor.caption")}</span>
        <textarea
          value={editable.caption}
          onChange={(event) => onChange({ caption: event.target.value })}
          placeholder={t("captionEditor.caption")}
          disabled={disabled}
          rows={4}
        />
      </label>
      <div className="publish-draft-desk__cta-row">
        <label className="publish-field publish-draft-desk__cta">
          <span className="publish-draft-desk__label">{t("captionEditor.cta")}</span>
          <input
            value={editable.ctaText}
            onChange={(event) => onChange({ ctaText: event.target.value })}
            placeholder={t("captionEditor.cta")}
            disabled={disabled}
          />
        </label>
      </div>
      <div className="publish-draft-desk__copy-head publish-draft-desk__copy-lang">
        <span className="publish-draft-desk__label" id="caption-language-label">
          {t("publishDraftPage.language")}
        </span>
        <label className="publish-draft-desk__lang">
          <input
            aria-labelledby="caption-language-label"
            value={editable.languageCode}
            onChange={(event) => onChange({ languageCode: event.target.value })}
            disabled={disabled}
          />
        </label>
      </div>
    </section>
  );
}
