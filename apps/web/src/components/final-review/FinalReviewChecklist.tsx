"use client";

import { useT } from "../../lib/i18n";
import type { ChecklistState, FinalReviewChecklistKey } from "../../types/final-review";
import { checklistComplete } from "../../lib/finalReviewState";

const CHECKLIST_KEYS: FinalReviewChecklistKey[] = [
  "narration_clear",
  "subtitle_ok",
  "timing_ok",
  "render_clean",
  "playable",
  "warnings_checked"
];

export function FinalReviewChecklist({
  checklist,
  onToggle
}: {
  checklist: ChecklistState;
  onToggle: (key: FinalReviewChecklistKey) => void;
}) {
  const t = useT();
  return (
    <section className="final-panel">
      <div className="panel-heading">
        <h2>{t("finalReviewChecklist.title")}</h2>
        <span className={`pill ${checklistComplete(checklist) ? "good" : ""}`}>
          {Object.values(checklist).filter(Boolean).length}/{CHECKLIST_KEYS.length}
        </span>
      </div>
      <div className="checklist">
        {CHECKLIST_KEYS.map((key) => (
          <label key={key} className="checklist-row">
            <input type="checkbox" checked={checklist[key]} onChange={() => onToggle(key)} />
            <span>
              <strong>{t("finalReviewChecklist.items." + key)}</strong>
              <small>{t("finalReviewChecklist.items." + key + "_hint")}</small>
            </span>
          </label>
        ))}
      </div>
    </section>
  );
}
