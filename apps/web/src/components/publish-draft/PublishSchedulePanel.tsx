"use client";

import { useT } from "../../lib/i18n";
import type { EditablePublishDraft, PublishDraft } from "../../types/publish-draft";

export function PublishSchedulePanel({
  draft,
  editable,
  disabled,
  onChange,
  onSchedule,
  onUnschedule
}: {
  draft: PublishDraft;
  editable: EditablePublishDraft;
  disabled: boolean;
  onChange: (patch: Partial<EditablePublishDraft>) => void;
  onSchedule: () => void;
  onUnschedule: () => void;
}) {
  const t = useT();
  return (
    <section className="publish-panel">
      <div className="panel-heading">
        <h2>{t("publishSchedulePanel.title")}</h2>
        <span className={`pill ${draft.status === "SCHEDULED" ? "good" : ""}`}>
          {draft.planned_publish_at ? `${t("publishSchedulePanel.scheduled")} ${new Date(draft.planned_publish_at).toLocaleString()}` : t("publishSchedulePanel.unscheduled")}
        </span>
      </div>
      <div className="publish-field-row">
        <label>
          {t("publishSchedulePanel.plannedPublishTime")}
          <input type="datetime-local" value={editable.plannedPublishAt} onChange={(event) => onChange({ plannedPublishAt: event.target.value })} disabled={disabled} />
        </label>
        <label>
          {t("publishSchedulePanel.timezone")}
          <input value={editable.timezone} onChange={(event) => onChange({ timezone: event.target.value })} disabled={disabled} />
        </label>
      </div>
      <label className="publish-field">
        {t("publishSchedulePanel.schedulingNotes")}
        <textarea value={editable.schedulingNotes} onChange={(event) => onChange({ schedulingNotes: event.target.value })} disabled={disabled} rows={3} />
      </label>
      <div className="publish-button-row">
        <button onClick={onSchedule} disabled={disabled || !editable.plannedPublishAt}>{t("publishSchedulePanel.schedule")}</button>
        <button onClick={onUnschedule} disabled={disabled || !draft.planned_publish_at}>{t("publishSchedulePanel.unschedule")}</button>
      </div>
    </section>
  );
}
