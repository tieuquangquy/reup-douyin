"use client";

import { useT } from "../../lib/i18n";
import type { ChecklistState, FinalReviewChecklistKey } from "../../types/final-review";
import { checklistComplete } from "../../lib/finalReviewState";

export const FINAL_REVIEW_CHECKLIST_KEYS: FinalReviewChecklistKey[] = [
  "narration_clear",
  "subtitle_ok",
  "timing_ok",
  "render_clean",
  "playable",
  "warnings_checked"
];

export function FinalReviewChecklist({
  checklist,
  onToggle,
  onSetAll
}: {
  checklist: ChecklistState;
  onToggle: (key: FinalReviewChecklistKey) => void;
  onSetAll: (checked: boolean) => void;
}) {
  const t = useT();
  const checkedCount = Object.values(checklist).filter(Boolean).length;
  const complete = checklistComplete(checklist);

  return (
    <section className="final-panel fr-check" aria-label={t("finalReviewChecklist.title")}>
      <div className="fr-check__head">
        <div className="fr-check__title-row">
          <h2>{t("finalReviewChecklist.title")}</h2>
          <span className={`pill ${complete ? "good" : ""}`}>
            {checkedCount}/{FINAL_REVIEW_CHECKLIST_KEYS.length}
          </span>
        </div>
        <button
          type="button"
          className="fr-check__bulk"
          onClick={() => onSetAll(!complete)}
        >
          {complete ? t("finalReviewChecklist.clearAll") : t("finalReviewChecklist.markAll")}
        </button>
      </div>
      <ul className="fr-check__list">
        {FINAL_REVIEW_CHECKLIST_KEYS.map((key) => (
          <li key={key}>
            <label
              className={`fr-check__row${checklist[key] ? " is-on" : ""}`}
              title={t("finalReviewChecklist.items." + key + "_hint")}
            >
              <input type="checkbox" checked={checklist[key]} onChange={() => onToggle(key)} />
              <span>{t("finalReviewChecklist.items." + key)}</span>
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}
