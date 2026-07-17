"use client";

import { useState } from "react";
import { useT } from "../../lib/i18n";
import { addHashtag, removeHashtag } from "../../lib/publishDraftState";
import type { EditablePublishDraft } from "../../types/publish-draft";

export function HashtagEditor({
  editable,
  disabled,
  onReplace
}: {
  editable: EditablePublishDraft;
  disabled: boolean;
  onReplace: (next: EditablePublishDraft) => void;
}) {
  const t = useT();
  const [input, setInput] = useState("");

  return (
    <section className="publish-panel">
      <h2>{t("hashtagEditor.title")}</h2>
      <div className="hashtag-list">
        {editable.hashtags.map((item) => (
          <button key={item.tag} onClick={() => onReplace(removeHashtag(editable, item.tag))} disabled={disabled}>
            #{item.tag} <span>{t("hashtagEditor.remove")}</span>
          </button>
        ))}
      </div>
      <div className="hashtag-add">
        <input value={input} onChange={(event) => setInput(event.target.value)} placeholder={t("hashtagEditor.addHashtag")} disabled={disabled} />
        <button
          onClick={() => {
            onReplace(addHashtag(editable, input));
            setInput("");
          }}
          disabled={disabled || !input.trim()}
        >
          {t("hashtagEditor.add")}
        </button>
      </div>
    </section>
  );
}
