"use client";

import { useState } from "react";
import { useT } from "../../lib/i18n";
import { addHashtag, removeHashtag } from "../../lib/publishDraftState";
import type { EditablePublishDraft } from "../../types/publish-draft";

export function HashtagEditor({
  editable,
  disabled,
  remainingTags,
  onReplace
}: {
  editable: EditablePublishDraft;
  disabled: boolean;
  remainingTags: number | null;
  onReplace: (next: EditablePublishDraft) => void;
}) {
  const t = useT();
  const [input, setInput] = useState("");

  function commitTag() {
    const next = input.trim();
    if (!next) return;
    onReplace(addHashtag(editable, next));
    setInput("");
  }

  return (
    <section className="publish-panel publish-draft-desk__tags">
      <header className="publish-draft-desk__copy-head">
        <h2 className="publish-draft-desk__heading">{t("hashtagEditor.title")}</h2>
        {remainingTags != null ? (
          <span className={`publish-draft-desk__chip${remainingTags < 0 ? " is-warn" : " is-ready"}`}>
            {remainingTags}
          </span>
        ) : null}
      </header>
      <div className="publish-draft-desk__tagbar">
        <div className="hashtag-list">
          {editable.hashtags.map((item) => (
            <button
              type="button"
              key={item.tag}
              onClick={() => onReplace(removeHashtag(editable, item.tag))}
              disabled={disabled}
              aria-label={`${t("hashtagEditor.remove")} #${item.tag}`}
            >
              #{item.tag}
              <span aria-hidden="true">×</span>
            </button>
          ))}
        </div>
        <form
          className="hashtag-add"
          onSubmit={(event) => {
            event.preventDefault();
            commitTag();
          }}
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={t("hashtagEditor.addHashtag")}
            disabled={disabled}
          />
          <button
            type="submit"
            className="publish-draft-desk__add"
            aria-label={t("hashtagEditor.add")}
            disabled={disabled || !input.trim()}
          >
            <svg className="publish-draft-desk__add-icon" viewBox="0 0 20 20" aria-hidden="true">
              <path
                d="M10 4.2v11.6M4.2 10h11.6"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeWidth="1.8"
              />
            </svg>
          </button>
        </form>
      </div>
    </section>
  );
}
