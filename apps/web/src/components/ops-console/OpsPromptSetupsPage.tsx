"use client";

import { useEffect, useRef, useState } from "react";
import {
  activateCaptionPromptProfile,
  activateTranslationPromptProfile,
  createCaptionPromptProfile,
  createTranslationPromptProfile,
  deleteCaptionPromptProfile,
  deleteTranslationPromptProfile,
  fetchCaptionPrompt,
  fetchCaptionPromptProfile,
  fetchTranslationPrompt,
  fetchTranslationPromptProfile,
  renameCaptionPromptProfile,
  renameTranslationPromptProfile,
  reorderCaptionPromptProfiles,
  reorderTranslationPromptProfiles,
  saveCaptionPromptProfile,
  saveTranslationPromptProfile,
  type PromptProfileSummary,
  type TranslationPromptResponse
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { isSetupTableInteractiveDragTarget, moveItemIndex, profileIdsOf } from "../../lib/opsProfileReorder";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsCaptionSettingsTabs } from "./OpsCaptionSettingsTabs";
import { OpsPanel } from "./OpsShared";
import { OpsTranslationSettingsTabs } from "./OpsTranslationSettingsTabs";

export type PromptVariant = "translation" | "caption";

type SetupActionIconKind = "edit" | "delete" | "add" | "back" | "save";

function SetupActionIcon({ kind }: { kind: SetupActionIconKind }) {
  if (kind === "add") {
    return (
      <svg className="ops-tts-list-toolbar__plus" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M10 4.5v11M4.5 10h11"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "back") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M11.5 4.5 6 10l5.5 5.5M6 10h8.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "save") {
    return (
      <svg className="ops-tts-editor-actions__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 4.5h9.2L15.5 6.3V15.5H4.5V4.5z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinejoin="round"
        />
        <path
          d="M7 4.5v3.8h5.2V4.5M7 15.5v-4.2h6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "edit") {
    return (
      <svg className="ops-tts-setup-table__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M4 20h4.2L18.8 9.4a1.8 1.8 0 0 0 0-2.5l-1.7-1.7a1.8 1.8 0 0 0-2.5 0L4 15.8V20z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M13.2 6.4 17.6 10.8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg className="ops-tts-setup-table__icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 7h16M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M6.5 7 7.4 19a1.5 1.5 0 0 0 1.5 1.3h6.2a1.5 1.5 0 0 0 1.5-1.3L17.5 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10 11v5.5M14 11v5.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

type ApiBundle = {
  fetchList: () => Promise<TranslationPromptResponse>;
  fetchProfile: (profileId: string) => Promise<TranslationPromptResponse>;
  createProfile: (name: string) => Promise<TranslationPromptResponse>;
  saveProfile: (profileId: string, prompt: string) => Promise<TranslationPromptResponse>;
  renameProfile: (profileId: string, name: string) => Promise<TranslationPromptResponse>;
  activate: (profileId: string) => Promise<TranslationPromptResponse>;
  reorderProfiles: (profileIds: string[]) => Promise<TranslationPromptResponse>;
  deleteProfile: (profileId: string) => Promise<TranslationPromptResponse>;
};

function apiForVariant(variant: PromptVariant): ApiBundle {
  if (variant === "caption") {
    return {
      fetchList: fetchCaptionPrompt,
      fetchProfile: fetchCaptionPromptProfile,
      createProfile: createCaptionPromptProfile,
      saveProfile: saveCaptionPromptProfile,
      renameProfile: renameCaptionPromptProfile,
      activate: activateCaptionPromptProfile,
      reorderProfiles: reorderCaptionPromptProfiles,
      deleteProfile: deleteCaptionPromptProfile
    };
  }
  return {
    fetchList: fetchTranslationPrompt,
    fetchProfile: fetchTranslationPromptProfile,
    createProfile: createTranslationPromptProfile,
    saveProfile: saveTranslationPromptProfile,
    renameProfile: renameTranslationPromptProfile,
    activate: activateTranslationPromptProfile,
    reorderProfiles: reorderTranslationPromptProfiles,
    deleteProfile: deleteTranslationPromptProfile
  };
}

function nextBlankSetupName(existing: Array<{ name: string }>): string {
  const used = new Set(existing.map((p) => (p.name || "").trim().toLowerCase()).filter(Boolean));
  let index = existing.length + 1;
  for (;;) {
    const candidate = `Setup ${index}`;
    if (!used.has(candidate.toLowerCase())) return candidate;
    index += 1;
  }
}

function previewFrom(prompt: string): string {
  const collapsed = prompt.replace(/\s+/g, " ").trim();
  if (collapsed.length <= 120) return collapsed;
  return `${collapsed.slice(0, 117)}…`;
}

export function OpsPromptSetupsPage({ variant }: { variant: PromptVariant }) {
  const t = useT();
  const asyncAction = useAsyncAction();
  const { notify } = useNotice();
  const api = apiForVariant(variant);
  const i18n = variant === "caption" ? "opsCaptionPrompt" : "opsTranslationPrompt";
  const navTitle = variant === "caption" ? t("nav.captionPrompt") : t("nav.translationPrompt");
  const navDesc =
    variant === "caption" ? t("nav.captionPromptDesc") : t("nav.translationPromptDesc");
  const idPrefix = variant === "caption" ? "caption-prompt" : "translation-prompt";

  const [profiles, setProfiles] = useState<PromptProfileSummary[]>([]);
  const [activeProfileId, setActiveProfileId] = useState("");
  const [activeProfileName, setActiveProfileName] = useState("Default");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [viewMode, setViewMode] = useState<"list" | "editor">("list");
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [editingProfileName, setEditingProfileName] = useState("");
  const [promptDraft, setPromptDraft] = useState("");

  const [renamingProfileId, setRenamingProfileId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [dragFromId, setDragFromId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const renameInputRef = useRef<HTMLInputElement | null>(null);

  function applyListResponse(data: TranslationPromptResponse) {
    setProfiles(data.profiles || []);
    setActiveProfileId(data.active_profile_id || "");
    setActiveProfileName(data.active_profile_name || "Default");
  }

  function applyEditorResponse(data: TranslationPromptResponse) {
    setPromptDraft(data.prompt || "");
    if (data.profiles) applyListResponse(data);
    const focusId = data.focus_profile_id;
    if (focusId) {
      setEditingProfileId(focusId);
      const named = (data.profiles || []).find((p) => p.id === focusId);
      if (named?.name) setEditingProfileName(named.name);
    }
  }

  async function loadList() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.fetchList();
      applyListResponse(data);
      setViewMode("list");
      setEditingProfileId(null);
      setPromptDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.loadError`));
    } finally {
      setLoading(false);
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      if (viewMode === "editor" && editingProfileId) {
        const data = await api.fetchProfile(editingProfileId);
        applyEditorResponse(data);
      } else {
        const data = await api.fetchList();
        applyListResponse(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.loadError`));
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on locale/variant change
  }, [t, variant]);

  useEffect(() => {
    if (!renamingProfileId) return;
    const input = renameInputRef.current;
    if (!input) return;
    input.focus();
    input.select();
  }, [renamingProfileId]);

  async function openEditor(profileId: string) {
    setProfileBusy(true);
    setError(null);
    try {
      const data = await api.fetchProfile(profileId);
      applyEditorResponse(data);
      setEditingProfileId(profileId);
      const named = (data.profiles || []).find((p) => p.id === profileId);
      setEditingProfileName(named?.name || "Setup");
      setViewMode("editor");
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.loadError`));
    } finally {
      setProfileBusy(false);
    }
  }

  function onCreateProfile() {
    const name = nextBlankSetupName(profiles);
    setError(null);
    setEditingProfileId(null);
    setEditingProfileName(name);
    setPromptDraft("");
    setViewMode("editor");
  }

  async function onSave() {
    setSaving(true);
    setError(null);
    try {
      let profileId = editingProfileId;
      const setupName = editingProfileName.trim() || nextBlankSetupName(profiles);
      if (!profileId) {
        const created = await api.createProfile(setupName);
        profileId = created.focus_profile_id || null;
        if (!profileId) throw new Error(t(`${i18n}.profileError`));
        setEditingProfileId(profileId);
        setEditingProfileName(setupName);
      } else {
        const currentName = profiles.find((p) => p.id === profileId)?.name || "";
        if (setupName && setupName !== currentName) {
          await api.renameProfile(profileId, setupName);
          setEditingProfileName(setupName);
        }
      }
      const data = await api.saveProfile(profileId, promptDraft);
      applyEditorResponse(data);
      notify({ id: `${idPrefix}-saved`, message: t(`${i18n}.saved`), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.saveError`));
    } finally {
      setSaving(false);
    }
  }

  function startRenameProfile(profileId: string, currentName: string) {
    setRenamingProfileId(profileId);
    setRenameDraft(currentName);
    setError(null);
  }

  function cancelRenameProfile() {
    setRenamingProfileId(null);
    setRenameDraft("");
  }

  async function commitRenameProfile() {
    const profileId = renamingProfileId;
    if (!profileId) return;
    const name = renameDraft.trim();
    const current = profiles.find((p) => p.id === profileId)?.name || "";
    if (!name || name === current) {
      cancelRenameProfile();
      return;
    }
    setProfileBusy(true);
    setError(null);
    try {
      const data = await api.renameProfile(profileId, name);
      applyListResponse(data);
      cancelRenameProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.profileError`));
    } finally {
      setProfileBusy(false);
    }
  }

  async function onSetActive(profileId: string, nextOn: boolean) {
    if (!profileId) return;
    if (!nextOn) {
      return;
    }
    if (profileId === activeProfileId) return;
    setProfileBusy(true);
    setError(null);
    try {
      const data = await api.activate(profileId);
      applyListResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.profileError`));
    } finally {
      setProfileBusy(false);
    }
  }

  async function onReorderProfiles(fromId: string, toId: string) {
    if (!fromId || !toId || fromId === toId || profileBusy) return;
    const from = profiles.findIndex((p) => p.id === fromId);
    const to = profiles.findIndex((p) => p.id === toId);
    if (from < 0 || to < 0) return;
    const next = moveItemIndex(profiles, from, to);
    const previous = profiles;
    setProfiles(next);
    setProfileBusy(true);
    setError(null);
    try {
      applyListResponse(await api.reorderProfiles(profileIdsOf(next)));
    } catch (err) {
      setProfiles(previous);
      setError(err instanceof Error ? err.message : t(`${i18n}.profileError`));
    } finally {
      setProfileBusy(false);
      setDragFromId(null);
      setDragOverId(null);
    }
  }

  async function onDeleteProfile(profileId: string, name: string) {
    if (profiles.length <= 1) {
      setError(t(`${i18n}.profileLastError`));
      return;
    }
    if (!window.confirm(`${t(`${i18n}.profileDeleteConfirm`)} (${name})`)) return;
    setProfileBusy(true);
    setError(null);
    try {
      const data = await api.deleteProfile(profileId);
      applyListResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t(`${i18n}.profileError`));
    } finally {
      setProfileBusy(false);
    }
  }

  const refreshAction = (
    <TopbarRefreshButton
      busy={refreshing}
      disabled={refreshing || profileBusy || saving}
      onClick={() => void onRefresh()}
    />
  );

  const settingsTabs =
    variant === "caption" ? <OpsCaptionSettingsTabs /> : <OpsTranslationSettingsTabs />;

  if (loading && profiles.length === 0 && viewMode === "list") {
    return (
      <OpsConsoleShell actions={refreshAction} description={navDesc} title={navTitle}>
        <AsyncContentBoundary status="loading" skeletonVariant="list" loadingLabel={t(`${i18n}.loadingDetail`)}>
          {null}
        </AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  if (viewMode === "list") {
    return (
      <OpsConsoleShell actions={refreshAction} description={navDesc} title={navTitle}>
        <main className="ops-page ops-page--settings ops-ai-page is-compact">
          {error ? <div className="inline-error">{error}</div> : null}
          <div className="ops-tts-list-header">
            {settingsTabs}
            <div className="ops-tts-list-toolbar">
              <div
                className="ops-tts-list-toolbar__cluster"
                aria-label={t(`${i18n}.sectionProfiles`)}
              >
                {activeProfileName ? (
                  <span
                    className="ops-tts-list-toolbar__active"
                    title={t(`${i18n}.profileActiveHint`)}
                  >
                    <span className="ops-tts-list-toolbar__dot" aria-hidden="true" />
                    <span className="ops-tts-list-toolbar__active-label">
                      {t(`${i18n}.profileActive`)}
                    </span>
                    <strong>{activeProfileName}</strong>
                  </span>
                ) : null}
                <span className="ops-tts-list-toolbar__divider" aria-hidden="true" />
                <span className="ops-tts-list-toolbar__count">
                  <strong>{profiles.length}</strong>
                  <span>{t(`${i18n}.profileSetupsCount`)}</span>
                </span>
                <button
                  type="button"
                  className="ops-tts-list-toolbar__new"
                  onClick={() => onCreateProfile()}
                  disabled={profileBusy}
                  aria-label={t(`${i18n}.profileNew`)}
                  title={t(`${i18n}.profileNew`)}
                >
                  <SetupActionIcon kind="add" />
                  <span>{t(`${i18n}.profileNew`)}</span>
                </button>
              </div>
            </div>
          </div>
          {profiles.length === 0 ? (
            <p className="ops-tts-empty">{t(`${i18n}.profileEmpty`)}</p>
          ) : (
            <div className="ops-tts-setup-table-wrap">
              <table className="ops-tts-setup-table ops-tts-setup-table--prompt">
                <thead>
                  <tr>
                    <th scope="col" className="ops-tts-setup-table__drag-col">
                      <span className="visually-hidden">{t("common.dragToReorder")}</span>
                    </th>
                    <th scope="col">{t(`${i18n}.profileNameCol`)}</th>
                    <th scope="col">{t(`${i18n}.profileActiveCol`)}</th>
                    <th scope="col">{t(`${i18n}.previewCol`)}</th>
                    <th scope="col" className="ops-tts-setup-table__actions">
                      {t(`${i18n}.profileActionsCol`)}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {profiles.map((profile) => {
                    const isActive = Boolean(profile.is_active) || profile.id === activeProfileId;
                    const preview = previewFrom(profile.prompt || "");
                    const canDrag = !profileBusy && renamingProfileId !== profile.id;
                    const rowClass = [
                      isActive ? "is-active" : "",
                      canDrag ? "is-draggable" : "",
                      dragFromId === profile.id ? "is-dragging" : "",
                      dragOverId === profile.id && dragFromId !== profile.id ? "is-drag-over" : ""
                    ]
                      .filter(Boolean)
                      .join(" ");
                    return (
                      <tr
                        key={profile.id}
                        className={rowClass || undefined}
                        draggable={canDrag}
                        title={canDrag ? t("common.dragToReorder") : undefined}
                        onDragStart={(event) => {
                          if (!canDrag || isSetupTableInteractiveDragTarget(event.target)) {
                            event.preventDefault();
                            return;
                          }
                          setDragFromId(profile.id);
                          setDragOverId(profile.id);
                          event.dataTransfer.effectAllowed = "move";
                          event.dataTransfer.setData("text/plain", profile.id);
                        }}
                        onDragEnd={() => {
                          setDragFromId(null);
                          setDragOverId(null);
                        }}
                        onDragOver={(event) => {
                          if (!dragFromId || profileBusy) return;
                          event.preventDefault();
                          if (dragOverId !== profile.id) setDragOverId(profile.id);
                        }}
                        onDrop={(event) => {
                          event.preventDefault();
                          const fromId = dragFromId || event.dataTransfer.getData("text/plain");
                          void onReorderProfiles(fromId, profile.id);
                        }}
                      >
                        <td className="ops-tts-setup-table__drag">
                          <span className="ops-tts-setup-table__drag-handle" aria-hidden="true">
                            ⋮⋮
                          </span>
                        </td>
                        <td className="ops-tts-setup-table__name">
                          {renamingProfileId === profile.id ? (
                            <input
                              ref={renameInputRef}
                              className="ops-tts-setup-table__rename-input"
                              type="text"
                              value={renameDraft}
                              maxLength={80}
                              disabled={profileBusy}
                              onChange={(e) => setRenameDraft(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  void commitRenameProfile();
                                } else if (e.key === "Escape") {
                                  e.preventDefault();
                                  cancelRenameProfile();
                                }
                              }}
                              onBlur={() => {
                                if (!profileBusy) void commitRenameProfile();
                              }}
                            />
                          ) : (
                            <>
                              <button
                                type="button"
                                className="ops-tts-setup-table__name-btn"
                                disabled={profileBusy}
                                onClick={() => startRenameProfile(profile.id, profile.name)}
                              >
                                {profile.name}
                              </button>
                            </>
                          )}
                        </td>
                        <td>
                          <label
                            className="ops-tts-setup-switch"
                            title={t(`${i18n}.profileActiveHint`)}
                          >
                            <input
                              type="checkbox"
                              checked={isActive}
                              disabled={profileBusy}
                              aria-label={
                                isActive
                                  ? t(`${i18n}.profileActiveBadge`)
                                  : t(`${i18n}.profileActive`)
                              }
                              onChange={(e) => void onSetActive(profile.id, e.target.checked)}
                            />
                            <span className="ops-tts-setup-switch__track" aria-hidden="true" />
                          </label>
                        </td>
                        <td
                          className="ops-tts-setup-table__preview"
                          title={profile.prompt || undefined}
                        >
                          {preview || <span className="ops-muted">—</span>}
                        </td>
                        <td className="ops-tts-setup-table__actions">
                          <button
                            type="button"
                            className="ops-tts-setup-table__icon-btn"
                            disabled={profileBusy}
                            aria-label={t(`${i18n}.profileEdit`)}
                            title={t(`${i18n}.profileEdit`)}
                            onClick={() => void openEditor(profile.id)}
                          >
                            <SetupActionIcon kind="edit" />
                          </button>
                          <button
                            type="button"
                            className="ops-tts-setup-table__icon-btn ops-tts-setup-table__icon-btn--danger"
                            disabled={profileBusy || profiles.length <= 1}
                            aria-label={t(`${i18n}.profileDelete`)}
                            title={t(`${i18n}.profileDelete`)}
                            onClick={() => void onDeleteProfile(profile.id, profile.name)}
                          >
                            <SetupActionIcon kind="delete" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </main>
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={navDesc} title={navTitle}>
      <main className="ops-page ops-page--settings ops-ai-page is-compact">
        {settingsTabs}
        {error ? <div className="inline-error">{error}</div> : null}

        <OpsPanel
          title={`${t(`${i18n}.panelTitle`)} · ${editingProfileName || t(`${i18n}.profileNew`)}`}
          actions={
            <div
              className="ops-header-actions ops-ai-toolbar"
              role="group"
              aria-label={t(`${i18n}.panelTitle`)}
            >
              <div className="ops-ai-toolbar__group">
                <button
                  type="button"
                  onClick={() => void loadList()}
                  disabled={saving || profileBusy}
                  aria-label={t(`${i18n}.actionBack`)}
                  title={t(`${i18n}.actionBack`)}
                >
                  <SetupActionIcon kind="back" />
                  <span className="ops-tts-editor-actions__label">
                    {t(`${i18n}.actionBack`)}
                  </span>
                </button>
                <AsyncButton
                  className="primary"
                  pending={asyncAction.isPending("save")}
                  pendingLabel={t(`${i18n}.saving`)}
                  leadingIcon={<SetupActionIcon kind="save" />}
                  onClick={() => void asyncAction.run("save", onSave)}
                  disabled={profileBusy}
                  aria-label={t(`${i18n}.save`)}
                  title={t(`${i18n}.save`)}
                >
                  <span className="ops-tts-editor-actions__label">{t(`${i18n}.actionSave`)}</span>
                </AsyncButton>
              </div>
            </div>
          }
        >
          <div className="ops-form-field">
            <label htmlFor={`${idPrefix}-setup-name`}>{t(`${i18n}.setupName`)}</label>
            <input
              id={`${idPrefix}-setup-name`}
              type="text"
              value={editingProfileName}
              maxLength={80}
              onChange={(event) => setEditingProfileName(event.target.value)}
              placeholder={t(`${i18n}.setupNamePlaceholder`)}
              title={t(`${i18n}.setupNameHint`)}
              autoComplete="off"
              spellCheck={false}
            />
            <p className="ops-tts-field-hint">{t(`${i18n}.setupNameHint`)}</p>
          </div>

          <div className="ops-ai-prompt-body">
            <textarea
              className="ops-prompt-textarea"
              rows={18}
              value={promptDraft}
              onChange={(event) => setPromptDraft(event.target.value)}
              placeholder={t(`${i18n}.placeholder`)}
              spellCheck={false}
            />
          </div>
        </OpsPanel>
      </main>
    </OpsConsoleShell>
  );
}
