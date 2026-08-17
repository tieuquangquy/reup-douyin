"use client";

import { useT } from "../../lib/i18n";
import type { EditablePublishDraft, PublishDraft } from "../../types/publish-draft";
import { humanizeStatus } from "../../lib/statusLabels";
import { AsyncButton } from "../shared/AsyncButton";

function PublishStripIcon({ kind }: { kind: "discard" | "save" | "ready" | "publish" | "review" | "drafts" }) {
  if (kind === "review") {
    return (
      <svg className="publish-draft-desk__action-icon" viewBox="0 0 20 20" aria-hidden="true">
        <rect x="4.2" y="3.6" width="11.6" height="12.8" rx="2" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M7 10.2 8.9 12.1 13.2 8"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.7"
        />
      </svg>
    );
  }
  if (kind === "drafts") {
    return (
      <svg className="publish-draft-desk__action-icon" viewBox="0 0 20 20" aria-hidden="true">
        <rect x="6.2" y="4.2" width="9" height="11.6" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M4.8 6.4v8.8A1.6 1.6 0 0 0 6.4 16.8h8" fill="none" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (kind === "discard") {
    return (
      <svg className="publish-draft-desk__action-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M6.4 8.2H4.6V6.4M4.8 8.1A5.4 5.4 0 1 1 6.2 13.4"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.7"
        />
      </svg>
    );
  }
  if (kind === "save") {
    return (
      <svg className="publish-draft-desk__action-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.6 4.6h8.8L15.4 6.6v8.8H4.6V4.6z"
          fill="none"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.7"
        />
        <path
          d="M7.1 4.6v3.6h5V4.6M7.2 15.4v-4h5.6"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.7"
        />
      </svg>
    );
  }
  if (kind === "ready") {
    return (
      <svg className="publish-draft-desk__action-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M5 10.2 8.1 13.3 15 6.5"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        />
      </svg>
    );
  }
  return (
    <svg className="publish-draft-desk__action-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M4.4 10.1h8.8M10.6 6.6 14.2 10.1 10.6 13.6"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

export function PublishDraftHeader({
  sourceVideoId,
  draft,
  editable,
  dirty,
  saving,
  savePending,
  readyPending,
  publishPending,
  errors,
  remainingChars,
  remainingTags,
  canPublish,
  onChange,
  onSave,
  onDiscard,
  onMarkReady,
  onPublishNow
}: {
  sourceVideoId: string;
  draft: PublishDraft | null;
  editable: EditablePublishDraft | null;
  dirty: boolean;
  saving: boolean;
  savePending: boolean;
  readyPending: boolean;
  publishPending: boolean;
  errors: string[];
  remainingChars: number | null;
  remainingTags: number | null;
  canPublish: boolean;
  onChange: (patch: Partial<EditablePublishDraft>) => void;
  onSave: () => void;
  onDiscard: () => void;
  onMarkReady: () => void;
  onPublishNow?: () => void;
}) {
  const t = useT();
  const readyClass = draft?.status === "READY" ? "publish-draft-desk__action" : "publish-draft-desk__action primary";
  return (
    <header className="publish-draft-desk__strip">
      <div className="publish-draft-desk__identity">
        <p className="eyebrow">{t("publishDraftHeader.eyebrow")}</p>
        <label className="publish-draft-desk__title-field" htmlFor="publish-draft-title">
          <span className="visually-hidden">{t("publishDraftHeader.titleField")}</span>
          <input
            id="publish-draft-title"
            className="publish-draft-desk__title"
            value={editable?.title ?? ""}
            title={editable?.title ?? undefined}
            placeholder={t("publishDraftHeader.defaultTitle")}
            disabled={!editable || saving}
            onChange={(event) => onChange({ title: event.target.value })}
          />
        </label>
        <div className="publish-draft-desk__meta">
          {draft ? (
            <>
              <span className="publish-draft-desk__chip">{humanizeStatus(draft.target_platform)}</span>
              <span className={`publish-draft-desk__chip is-${draft.status.toLowerCase()}`}>
                {humanizeStatus(draft.status)}
              </span>
              <span className="publish-draft-desk__chip is-quiet">v{draft.version}</span>
              {dirty ? <span className="publish-draft-desk__chip is-dirty">{t("publishDraftHeader.unsaved")}</span> : null}
              <span className="publish-draft-desk__id">{draft.id.slice(0, 8)}</span>
            </>
          ) : (
            <span className="publish-draft-desk__hint">{t("publishDraftHeader.createDraftHint")}</span>
          )}
          {remainingChars != null ? (
            <span className={`publish-draft-desk__chip${remainingChars < 0 ? " is-warn" : " is-quiet"}`}>
              {remainingChars} {t("publishDraftHeader.remainingChars")}
            </span>
          ) : null}
          {remainingTags != null ? (
            <span className={`publish-draft-desk__chip${remainingTags < 0 ? " is-warn" : " is-quiet"}`}>
              {remainingTags} {t("publishDraftHeader.remainingTags")}
            </span>
          ) : null}
        </div>
      </div>
      <div className="publish-draft-desk__actions">
        <nav className="publish-draft-desk__jumps" aria-label={t("operatorRoutes.publishDraftTitle")}>
          <a className="publish-draft-desk__action is-ghost" href={`/production/final-review/${sourceVideoId}`}>
            <PublishStripIcon kind="review" />
            <span>{t("nav.finalReview")}</span>
          </a>
          <a className="publish-draft-desk__action is-ghost" href="/publishing/drafts">
            <PublishStripIcon kind="drafts" />
            <span>{t("nav.publishDrafts")}</span>
          </a>
        </nav>
        <div className="publish-draft-desk__ops">
          <button type="button" className="publish-draft-desk__action is-ghost" onClick={onDiscard} disabled={!dirty || saving}>
            <PublishStripIcon kind="discard" />
            <span>{t("publishDraftHeader.discard")}</span>
          </button>
          <AsyncButton
            className="publish-draft-desk__action"
            pending={savePending}
            onClick={onSave}
            disabled={!dirty || saving || !draft}
            leadingIcon={<PublishStripIcon kind="save" />}
          >
            {t("publishDraftHeader.saveDraft")}
          </AsyncButton>
          <AsyncButton
            className={readyClass}
            pending={readyPending}
            onClick={onMarkReady}
            disabled={saving || !draft || errors.length > 0}
            leadingIcon={<PublishStripIcon kind="ready" />}
          >
            {t("publishDraftHeader.markDraftReady")}
          </AsyncButton>
          {onPublishNow ? (
            <AsyncButton
              className="publish-draft-desk__action primary"
              pending={publishPending}
              onClick={onPublishNow}
              disabled={!canPublish || saving}
              leadingIcon={<PublishStripIcon kind="publish" />}
            >
              {t("publishDraftPage.publishNow")}
            </AsyncButton>
          ) : null}
        </div>
      </div>
    </header>
  );
}
