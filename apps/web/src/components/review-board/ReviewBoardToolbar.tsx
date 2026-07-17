"use client";

import { useT } from "../../lib/i18n";
import type { CandidateFilters, FilterPreset } from "../../types/review-board";

type Props = {
  filters: CandidateFilters;
  presets: FilterPreset[];
  onChange: (filters: CandidateFilters) => void;
  onApply: () => void;
  onReset: () => void;
};

export function ReviewBoardToolbar({ filters, presets, onChange, onApply, onReset }: Props) {
  const t = useT();
  const update = (patch: Partial<CandidateFilters>) => onChange({ ...filters, ...patch });

  return (
    <div className="toolbar">
      <div className="field">
        <label htmlFor="preset">{t("reviewBoardPage.preset")}</label>
        <select id="preset" value={filters.presetName} onChange={(event) => update({ presetName: event.target.value })}>
          <option value="">{t("reviewBoardPage.currentCandidates")}</option>
          {presets.map((preset) => (
            <option key={preset.name} value={preset.name}>
              {preset.name}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="status">{t("reviewBoardPage.status")}</label>
        <select id="status" value={filters.status} onChange={(event) => update({ status: event.target.value as CandidateFilters["status"] })}>
          <option value="">{t("reviewBoardPage.any")}</option>
          <option value="SHORTLISTED">{t("reviewBoard.status.shortlisted")}</option>
          <option value="APPROVED">{t("reviewBoardPage.kept")}</option>
          <option value="REJECTED">{t("reviewBoard.status.rejected")}</option>
          <option value="IN_REVIEW">{t("reviewBoardPage.nextStep")}</option>
        </select>
      </div>

      <div className="field">
        <label htmlFor="min-score">{t("reviewBoardPage.minScore")}</label>
        <input id="min-score" inputMode="numeric" value={filters.minScore} onChange={(event) => update({ minScore: event.target.value })} />
      </div>

      <div className="field">
        <label htmlFor="max-score">{t("reviewBoardPage.maxScore")}</label>
        <input id="max-score" inputMode="numeric" value={filters.maxScore} onChange={(event) => update({ maxScore: event.target.value })} />
      </div>

      <div className="field">
        <label htmlFor="search">{t("reviewBoardPage.search")}</label>
        <input id="search" value={filters.search} onChange={(event) => update({ search: event.target.value })} placeholder={t("reviewBoardPage.searchPlaceholder")} />
      </div>

      <div className="field">
        <label htmlFor="sort">{t("reviewBoardPage.sort")}</label>
        <select id="sort" value={filters.sort} onChange={(event) => update({ sort: event.target.value as CandidateFilters["sort"] })}>
          <option value="score_desc">{t("reviewBoardPage.score")}</option>
          <option value="newest_first">{t("reviewBoardPage.newest")}</option>
          <option value="views_desc">{t("reviewBoardPage.views")}</option>
        </select>
      </div>

      <button className="primary" onClick={onApply}>{t("reviewBoardPage.apply")}</button>
      <button onClick={onReset}>{t("reviewBoardPage.reset")}</button>
    </div>
  );
}
