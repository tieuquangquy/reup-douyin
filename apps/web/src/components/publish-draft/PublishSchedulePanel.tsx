"use client";

import { useT } from "../../lib/i18n";
import {
  isCompletePlannedPublishAt,
  joinPlannedPublishAt,
  splitPlannedPublishAt
} from "../../lib/publishDraftState";
import type { EditablePublishDraft, PublishDraft } from "../../types/publish-draft";
import { AsyncButton } from "../shared/AsyncButton";

function WhenStampIcon({ kind }: { kind: "date" | "time" | "zone" }) {
  if (kind === "time") {
    return (
      <svg className="publish-draft-desk__when-icon" viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10.2" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 7.2v3.3l2.2 1.4" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
      </svg>
    );
  }
  if (kind === "zone") {
    return (
      <svg className="publish-draft-desk__when-icon" viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M4 10h12M10 3.8c2.1 2.2 3.1 4 3.1 6.2s-1 4-3.1 6.2C7.9 14 6.9 12.2 6.9 10s1-4 3.1-6.2Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
        />
      </svg>
    );
  }
  return (
    <svg className="publish-draft-desk__when-icon" viewBox="0 0 20 20" aria-hidden="true">
      <rect x="3.6" y="5" width="12.8" height="11.2" rx="2" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3.6 8.4h12.8M7.2 3.6v2.8M12.8 3.6v2.8" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  );
}

function WhenIcon({ kind }: { kind: "schedule" | "unschedule" }) {
  if (kind === "unschedule") {
    return (
      <svg className="publish-draft-desk__bay-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M5 10h10"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.8"
        />
      </svg>
    );
  }
  return (
    <svg className="publish-draft-desk__bay-icon" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10.2" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 7.2v3.3l2.2 1.4" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  );
}

export function PublishSchedulePanel({
  draft,
  editable,
  disabled,
  schedulePending,
  unschedulePending,
  onChange,
  onSchedule,
  onUnschedule,
  compact = false,
  mode = "all"
}: {
  draft: PublishDraft;
  editable: EditablePublishDraft;
  disabled: boolean;
  schedulePending: boolean;
  unschedulePending: boolean;
  onChange: (patch: Partial<EditablePublishDraft>) => void;
  onSchedule: () => void;
  onUnschedule: () => void;
  compact?: boolean;
  mode?: "all" | "fields" | "actions";
}) {
  const t = useT();
  const showFields = mode === "all" || mode === "fields";
  const showActions = mode === "all" || mode === "actions";
  const stamp = splitPlannedPublishAt(editable.plannedPublishAt);
  const scheduleStatus = draft.planned_publish_at
    ? `${t("publishSchedulePanel.scheduled")} ${new Date(draft.planned_publish_at).toLocaleString()}`
    : t("publishSchedulePanel.unscheduled");
  return (
    <section className={compact ? `publish-draft-desk__when${mode === "actions" ? " is-actions" : ""}` : "publish-panel"}>
      {showFields ? (
        <>
          {compact ? null : (
            <div className="panel-heading">
              <h2>{t("publishSchedulePanel.title")}</h2>
              <span className={`pill ${draft.status === "SCHEDULED" ? "good" : ""}`}>{scheduleStatus}</span>
            </div>
          )}
          <header className="publish-draft-desk__when-head">
            <h3 className="publish-draft-desk__heading">{t("publishSchedulePanel.plannedPublishTime")}</h3>
            {compact ? (
              <span
                className={`publish-draft-desk__chip ${draft.planned_publish_at ? "is-ready" : "is-unassigned"} publish-draft-desk__when-status`}
                aria-label={scheduleStatus}
              >
                {draft.planned_publish_at
                  ? t("publishSchedulePanel.scheduled")
                  : t("publishSchedulePanel.unscheduled")}
              </span>
            ) : null}
          </header>
          <div className="publish-draft-desk__tagbar publish-draft-desk__when-stamp">
            <label>
              <WhenStampIcon kind="date" />
              <span className="visually-hidden">{t("publishSchedulePanel.date")}</span>
              <input
                type="date"
                value={stamp.date}
                onChange={(event) => onChange({ plannedPublishAt: joinPlannedPublishAt(event.target.value, stamp.time) })}
                disabled={disabled}
              />
            </label>
            <label>
              <WhenStampIcon kind="time" />
              <span className="visually-hidden">{t("publishSchedulePanel.time")}</span>
              <input
                type="time"
                step={60}
                value={stamp.time}
                onChange={(event) => onChange({ plannedPublishAt: joinPlannedPublishAt(stamp.date, event.target.value) })}
                disabled={disabled || !stamp.date}
              />
            </label>
            <label>
              <WhenStampIcon kind="zone" />
              <span className="visually-hidden">{t("publishSchedulePanel.timezone")}</span>
              <input
                value={editable.timezone}
                onChange={(event) => onChange({ timezone: event.target.value })}
                disabled={disabled}
              />
            </label>
          </div>
          {compact ? null : (
            <label className="publish-field">
              {t("publishSchedulePanel.schedulingNotes")}
              <textarea
                value={editable.schedulingNotes}
                onChange={(event) => onChange({ schedulingNotes: event.target.value })}
                disabled={disabled}
                rows={3}
              />
            </label>
          )}
        </>
      ) : null}
      {showActions ? (
        <div className="publish-button-row">
          <AsyncButton
            className="publish-draft-desk__action is-schedule"
            pending={schedulePending}
            onClick={onSchedule}
            disabled={disabled || !isCompletePlannedPublishAt(editable.plannedPublishAt)}
            leadingIcon={<WhenIcon kind="schedule" />}
          >
            {t("publishSchedulePanel.schedule")}
          </AsyncButton>
          <AsyncButton
            className="publish-draft-desk__action"
            pending={unschedulePending}
            onClick={onUnschedule}
            disabled={disabled || !draft.planned_publish_at}
            leadingIcon={<WhenIcon kind="unschedule" />}
          >
            {t("publishSchedulePanel.unschedule")}
          </AsyncButton>
        </div>
      ) : null}
    </section>
  );
}
