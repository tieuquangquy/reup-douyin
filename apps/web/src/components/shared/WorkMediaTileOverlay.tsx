"use client";

import type { ReactNode } from "react";
import type { OperatorTileScoreBadge } from "../../lib/operatorTileScore";

export type WorkMediaTileStatusTone = "good" | "warn" | "danger" | "muted" | "ready";
export type WorkMediaTileOverlayDensity = "default" | "compact";

export type WorkMediaTileStatusChip = {
  key?: string;
  label: string;
  tone: WorkMediaTileStatusTone;
  /** Optional modifier class, e.g. queue/job chip variants. */
  modifierClassName?: string;
};

type WorkMediaTileSelectProps = {
  selected: boolean;
  onToggle: () => void;
  ariaLabel: string;
  title: string;
};

type WorkMediaTileScoreBadgeProps = {
  badge: OperatorTileScoreBadge;
  className?: string;
  compact?: boolean;
};

export function WorkMediaTileScoreBadge({ badge, className = "", compact = false }: WorkMediaTileScoreBadgeProps) {
  const tier = badge.tierLabel.trim();
  return (
    <span
      className={`work-media-tile-score-badge is-${badge.level} ${badge.score == null ? "is-missing" : "is-ready"} ${compact ? "is-inline" : ""} ${className}`.trim()}
      title={badge.title}
    >
      {compact ? (
        <span className="work-media-tile-score-inline">
          <strong>{badge.valueLabel}</strong>
          {tier ? (
            <>
              <span aria-hidden="true" className="work-media-tile-score-sep">
                ·
              </span>
              <small>{tier}</small>
            </>
          ) : null}
        </span>
      ) : (
        <>
          <strong>{badge.valueLabel}</strong>
          <small>{badge.tierLabel}</small>
        </>
      )}
    </span>
  );
}

function WorkMediaTileSelect({ selected, onToggle, ariaLabel, title }: WorkMediaTileSelectProps) {
  return (
    <label
      className={`work-media-tile-select ${selected ? "is-selected" : ""}`}
      title={title}
    >
      <input aria-label={ariaLabel} checked={selected} onChange={onToggle} type="checkbox" />
      <span aria-hidden="true" className="work-media-tile-select-visual" />
    </label>
  );
}

type WorkMediaTileOverlayProps = {
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: () => void;
  selectAriaLabel?: string;
  selectTitle?: string;
  statusChips: WorkMediaTileStatusChip[];
  scoreBadge: OperatorTileScoreBadge;
  scoreBadgeClassName?: string;
  rightSlot?: ReactNode;
  /** `compact` = micro rail (single row, inline score). Default for Work tiles. */
  density?: WorkMediaTileOverlayDensity;
};

/** Shared top overlay for Capture Inbox, Review Board, and Reup Queue media tiles. */
export function WorkMediaTileOverlay({
  selectable = true,
  selected = false,
  onToggleSelect,
  selectAriaLabel = "Select item",
  selectTitle = "Select item",
  statusChips,
  scoreBadge,
  scoreBadgeClassName = "",
  rightSlot,
  density = "compact",
}: WorkMediaTileOverlayProps) {
  const compact = density === "compact";
  const visibleChips = compact ? statusChips.slice(0, 1) : statusChips;

  return (
    <div
      className={`capture-inbox-media-overlay top work-media-tile-overlay${compact ? " is-compact" : ""}`}
      aria-label="Tile overlay controls"
    >
      <div className="capture-inbox-media-overlay-scrim work-media-tile-overlay-scrim" aria-hidden="true" />
      <div className="work-media-tile-overlay-left">
        {selectable && onToggleSelect ? (
          <WorkMediaTileSelect
            ariaLabel={selectAriaLabel}
            onToggle={onToggleSelect}
            selected={selected}
            title={selectTitle}
          />
        ) : null}
        {visibleChips.map((chip) => (
          <span
            className={[
              "work-media-tile-status-chip",
              `is-${chip.tone}`,
              chip.modifierClassName ?? "",
            ]
              .filter(Boolean)
              .join(" ")}
            key={chip.key ?? chip.label}
            title={chip.label}
          >
            {chip.label}
          </span>
        ))}
      </div>
      <div className="work-media-tile-overlay-right">
        {rightSlot}
        <WorkMediaTileScoreBadge badge={scoreBadge} className={scoreBadgeClassName} compact={compact} />
      </div>
    </div>
  );
}
