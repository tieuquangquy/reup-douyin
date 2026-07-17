"use client";

import { useT } from "../../lib/i18n";

type Props = {
  selectedCount: number;
  disabled: boolean;
  onKeep: () => void;
  onReject: () => void;
  onNextStep: () => void;
  onSendToReupQueue: () => void;
  onClear: () => void;
};

export function CandidateSelectionBar({
  selectedCount,
  disabled,
  onKeep,
  onReject,
  onNextStep,
  onSendToReupQueue,
  onClear
}: Props) {
  const t = useT();
  if (selectedCount === 0) return null;

  return (
    <div className="selection-bar">
      <strong>{selectedCount} selected</strong>
      <button disabled={disabled} onClick={onKeep}>{t("reviewBoardPage.keepSelected")}</button>
      <button disabled={disabled} onClick={onReject}>{t("reviewBoardPage.rejectSelected")}</button>
      <button disabled={disabled} onClick={onNextStep}>{t("reviewBoardPage.markNextStep")}</button>
      <button className="primary" disabled={disabled} onClick={onSendToReupQueue}>Send to Reup Queue</button>
      <button disabled={disabled} onClick={onClear}>{t("reviewBoardPage.clear")}</button>
    </div>
  );
}
