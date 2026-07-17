"use client";

import { useState } from "react";
import { useT } from "../../lib/i18n";
import type { EditablePublishDraft, PublishTarget, PublishTargetPlatform } from "../../types/publish-draft";

export function PublishTargetSelector({
  targets,
  editable,
  disabled,
  onChange,
  onCreate
}: {
  targets: PublishTarget[];
  editable: EditablePublishDraft | null;
  disabled: boolean;
  onChange: (patch: Partial<EditablePublishDraft>) => void;
  onCreate: (platform: PublishTargetPlatform) => void;
}) {
  const t = useT();
  const [pendingPlatform, setPendingPlatform] = useState<PublishTargetPlatform>("TIKTOK");
  const selected = editable?.targetPlatform ?? pendingPlatform;

  return (
    <section className="publish-panel">
      <h2>{t("publishTargetSelector.title")}</h2>
      <div className="publish-field-row">
        <label>
          {t("publishTargetSelector.platform")}
          <select
            value={selected}
            onChange={(event) => {
              const platform = event.target.value as PublishTargetPlatform;
              if (editable) onChange({ targetPlatform: platform });
              else setPendingPlatform(platform);
            }}
            disabled={disabled || targets.length === 0}
          >
            {targets.map((target) => (
              <option key={target.platform} value={target.platform}>{target.label}</option>
            ))}
          </select>
        </label>
        <label>
          {t("publishTargetSelector.accountRefPlaceholder")}
          <input
            value={editable?.platformAccountRef ?? ""}
            onChange={(event) => onChange({ platformAccountRef: event.target.value })}
            disabled={disabled || !editable}
            placeholder="local-account-1"
          />
        </label>
      </div>
      {!editable ? (
        <button className="primary" onClick={() => onCreate(selected)} disabled={disabled || targets.length === 0}>
          {t("publishTargetSelector.createPublishDraft")}
        </button>
      ) : null}
    </section>
  );
}
