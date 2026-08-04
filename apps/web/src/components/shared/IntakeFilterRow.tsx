"use client";

import { CaptureInboxFilterChipIcon, type CaptureInboxFilterChipIconKind } from "../capture-inbox/CaptureInboxFilterChipIcon";
import { WorkItemActionIcon } from "./WorkItemActionIcon";
import {
  captureSessionOptionLabel,
  intakeFiltersActive,
  type IntakeDateChip,
  type IntakeFilterState
} from "../../lib/reviewBoardIntake";
import type { CaptureSession } from "../../types/capture-inbox";

const INTAKE_DATE_CHIPS: Array<{ key: IntakeDateChip; label: string; icon: CaptureInboxFilterChipIconKind }> = [
  { key: "today", label: "Today", icon: "time-current-month" },
  { key: "7d", label: "7 days", icon: "time-week" },
  { key: "30d", label: "30 days", icon: "time-month" },
  { key: "custom", label: "Custom", icon: "meta-posted" }
];

type Props = {
  addedLabel?: string;
  busy?: boolean;
  className?: string;
  onChange: (partial: Partial<IntakeFilterState>) => void;
  onClear: () => void;
  sessions: CaptureSession[];
  state: IntakeFilterState;
};

/**
 * "Which Capture Inbox batch, and when did it arrive" — shared by Review Board and Reup
 * Queue so both lanes answer the question the same way.
 *
 * Every control applies on the spot: a batch or a day is a discrete pick like a status
 * tab, and hiding it behind a separate Apply button reads as a dead control.
 */
export function IntakeFilterRow({
  addedLabel = "Added",
  busy = false,
  className = "",
  onChange,
  onClear,
  sessions,
  state
}: Props) {
  return (
    <div
      aria-busy={busy}
      aria-label="Intake filters"
      className={`review-board-intake-filter${busy ? " is-busy" : ""} ${className}`.trim()}
    >
      <label className="review-board-filter-control is-intake">
        <span className="review-board-filter-control__label">
          <CaptureInboxFilterChipIcon className="review-board-intake-filter__label-icon" kind="lane-captured" />
          Pushed batch
        </span>
        <select
          aria-label="Filter by the Capture Inbox batch that pushed these clips"
          className="review-board-deck-input review-board-deck-intake"
          disabled={busy}
          onChange={(event) => onChange({ captureSessionId: event.target.value })}
          value={state.captureSessionId}
        >
          <option value="">All intakes</option>
          {sessions.map((session) => (
            <option key={session.id} value={session.id}>
              {captureSessionOptionLabel(session)}
            </option>
          ))}
        </select>
      </label>
      <div className="review-board-intake-filter__chips" role="group" aria-label="Filter by arrival day">
        <span className="review-board-filter-control__label">
          <CaptureInboxFilterChipIcon className="review-board-intake-filter__label-icon" kind="meta-posted" />
          {addedLabel}
        </span>
        {INTAKE_DATE_CHIPS.map((chip) => (
          <button
            aria-pressed={state.dateChip === chip.key}
            className={`review-board-deck-btn is-chip ${state.dateChip === chip.key ? "is-active" : ""}`}
            disabled={busy}
            key={chip.key}
            onClick={() => onChange({ dateChip: state.dateChip === chip.key ? "" : chip.key })}
            type="button"
          >
            <CaptureInboxFilterChipIcon className="review-board-intake-filter__chip-icon" kind={chip.icon} />
            {chip.label}
          </button>
        ))}
      </div>
      {state.dateChip === "custom" ? (
        <div className="review-board-intake-filter__range">
          <label className="review-board-score-range__field">
            <span>From</span>
            <input
              aria-label="Added on or after"
              className="review-board-deck-input"
              disabled={busy}
              onChange={(event) => onChange({ dateFrom: event.target.value })}
              type="date"
              value={state.dateFrom}
            />
          </label>
          <label className="review-board-score-range__field">
            <span>To</span>
            <input
              aria-label="Added on or before"
              className="review-board-deck-input"
              disabled={busy}
              onChange={(event) => onChange({ dateTo: event.target.value })}
              type="date"
              value={state.dateTo}
            />
          </label>
        </div>
      ) : null}
      {busy ? (
        <span className="review-board-intake-filter__busy" role="status">
          <span aria-hidden="true" className="review-board-intake-filter__spinner" />
          Updating…
        </span>
      ) : null}
      {intakeFiltersActive(state) ? (
        <button className="review-board-deck-btn is-ghost is-intake-clear" disabled={busy} onClick={onClear} type="button">
          <WorkItemActionIcon className="review-board-filter-action__icon" kind="clear-selection" />
          Clear intake filter
        </button>
      ) : null}
    </div>
  );
}
