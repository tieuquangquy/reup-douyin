"use client";

import { useT } from "../../lib/i18n";

type Props = {
  dirtyCount: number;
  warningCount: number;
  blockingCount: number;
  saving: boolean;
  jobBusy?: boolean;
  onSave: () => void;
  onDiscard: () => void;
};

export function TranscriptActionBar({
  dirtyCount,
  warningCount,
  blockingCount,
  saving,
  jobBusy = false,
  onSave,
  onDiscard
}: Props) {
  const t = useT();
  // Dirty-only dock — warnings stay on the segment / inspector.
  if (dirtyCount === 0) return null;
  const locked = saving || jobBusy;
  return (
    <div className="transcript-action-bar">
      <strong>
        {dirtyCount} {t("transcriptEditorActionBar.unsavedEdits")}
      </strong>
      {warningCount > 0 ? (
        <span>
          {warningCount} {t("transcriptEditorActionBar.warnings")}
        </span>
      ) : null}
      {blockingCount > 0 ? (
        <span>
          {blockingCount} {t("transcriptEditorActionBar.timingBlockers")}
        </span>
      ) : null}
      <button onClick={onDiscard} disabled={locked}>
        {t("transcriptEditorActionBar.discard")}
      </button>
      <button className="primary" onClick={onSave} disabled={locked || blockingCount > 0}>
        {saving ? t("transcriptEditorActionBar.saving") : t("transcriptEditorActionBar.saveDraft")}
      </button>
    </div>
  );
}
