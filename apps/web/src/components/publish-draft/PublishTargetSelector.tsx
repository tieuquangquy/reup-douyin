"use client";

import { useId, useState } from "react";
import { useT } from "../../lib/i18n";
import type { EditablePublishDraft, PublishTarget, PublishTargetPlatform } from "../../types/publish-draft";
import { AsyncButton } from "../shared/AsyncButton";
import { PublishDestSelect } from "./PublishDestSelect";

export function PublishTargetSelector({
  targets,
  editable,
  disabled,
  createPending,
  onChange,
  onCreate
}: {
  targets: PublishTarget[];
  editable: EditablePublishDraft | null;
  disabled: boolean;
  createPending: boolean;
  onChange: (patch: Partial<EditablePublishDraft>) => void;
  onCreate: (platform: PublishTargetPlatform) => void;
}) {
  const t = useT();
  const platformLabelId = useId();
  const [pendingPlatform, setPendingPlatform] = useState<PublishTargetPlatform>("TIKTOK");
  const selected = editable?.targetPlatform ?? pendingPlatform;

  return (
    <section className="publish-draft-desk__platform publish-draft-desk__channel">
      <span className="visually-hidden" id={platformLabelId}>
        {t("publishTargetSelector.platform")}
      </span>
      <PublishDestSelect
        className="publish-draft-desk__dest-hero publish-draft-desk__channel-select"
        value={selected}
        disabled={disabled || targets.length === 0}
        labelledBy={platformLabelId}
        options={targets.map((target) => ({ value: target.platform, label: target.label }))}
        onChange={(platform) => {
          const next = platform as PublishTargetPlatform;
          if (editable) onChange({ targetPlatform: next });
          else setPendingPlatform(next);
        }}
      />
      {!editable ? (
        <AsyncButton
          className="primary"
          pending={createPending}
          onClick={() => onCreate(selected)}
          disabled={disabled || targets.length === 0}
        >
          {t("publishTargetSelector.createPublishDraft")}
        </AsyncButton>
      ) : null}
    </section>
  );
}
