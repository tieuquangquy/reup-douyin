"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createWorkspaceInvite,
  fetchWorkspaceInvites,
  fetchWorkspaceMembers,
  revokeWorkspaceInvite,
  updateWorkspaceMember,
  type WorkspaceInvite,
  type WorkspaceMember
} from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useT } from "../../lib/i18n";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { StatusBadge } from "../app-shell/StatusBadge";
import { OpsState, formatDateTime } from "./OpsShared";

const ROLE_OPTIONS = ["owner", "admin", "operator", "viewer"] as const;

type ModalMode = "invite" | "edit" | null;

function memberInitial(member: WorkspaceMember): string {
  const source = (member.displayName || member.email || "?").trim();
  return (source[0] || "?").toUpperCase();
}

function roleChipClass(role: string): string {
  if (role === "owner") return "ops-users-role-chip is-owner";
  if (role === "admin") return "ops-users-role-chip is-admin";
  if (role === "viewer") return "ops-users-role-chip is-viewer";
  return "ops-users-role-chip is-operator";
}

function InviteIcon() {
  return (
    <svg aria-hidden="true" className="ops-users-btn-icon" fill="none" viewBox="0 0 16 16">
      <path
        d="M8 3.2v9.6M3.2 8h9.6"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

export function OpsUsersPage() {
  const t = useT();
  const { me } = useAuth();
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invites, setInvites] = useState<WorkspaceInvite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [pendingOpen, setPendingOpen] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [editingMember, setEditingMember] = useState<WorkspaceMember | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<string>("operator");
  const [editRole, setEditRole] = useState<string>("operator");
  const [lastInviteLink, setLastInviteLink] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [nextMembers, nextInvites] = await Promise.all([fetchWorkspaceMembers(), fetchWorkspaceInvites()]);
      setMembers(nextMembers);
      setInvites(nextInvites);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const summary = useMemo(() => {
    const active = members.filter((member) => member.isActive).length;
    const disabled = members.length - active;
    const pending = invites.filter((invite) => invite.status === "pending").length;
    return { active, disabled, pending, total: members.length };
  }, [invites, members]);

  const filteredMembers = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return members.filter((member) => {
      if (roleFilter !== "all" && member.role !== roleFilter) return false;
      if (!query) return true;
      const haystack = `${member.displayName ?? ""} ${member.email}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [members, roleFilter, searchQuery]);

  function openInviteModal() {
    setModalMode("invite");
    setEditingMember(null);
    setInviteEmail("");
    setInviteRole("operator");
    setLastInviteLink(null);
    setError(null);
  }

  function openEditModal(member: WorkspaceMember) {
    setModalMode("edit");
    setEditingMember(member);
    setEditRole(member.role);
    setError(null);
  }

  function closeModal() {
    setModalMode(null);
    setEditingMember(null);
  }

  async function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusyId("invite");
    setError(null);
    setMessage(null);
    try {
      const created = await createWorkspaceInvite({ email: inviteEmail.trim(), role: inviteRole });
      const link = `${window.location.origin}/auth/invite?token=${encodeURIComponent(created.inviteToken)}`;
      setLastInviteLink(link);
      setMessage(t("opsUsers.inviteCreated"));
      setInviteEmail("");
      setInviteRole("operator");
      setPendingOpen(true);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.inviteError"));
    } finally {
      setBusyId(null);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingMember) return;
    setBusyId(editingMember.operatorId);
    setError(null);
    setMessage(null);
    try {
      await updateWorkspaceMember(editingMember.operatorId, { role: editRole });
      setMessage(t("opsUsers.roleUpdated"));
      closeModal();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.updateError"));
    } finally {
      setBusyId(null);
    }
  }

  async function handleRevoke(inviteId: string) {
    setBusyId(inviteId);
    setError(null);
    setMessage(null);
    try {
      await revokeWorkspaceInvite(inviteId);
      setMessage(t("opsUsers.inviteRevoked"));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.revokeError"));
    } finally {
      setBusyId(null);
    }
  }

  async function handleEnable(member: WorkspaceMember) {
    setBusyId(member.operatorId);
    setError(null);
    setMessage(null);
    try {
      await updateWorkspaceMember(member.operatorId, { isActive: true });
      setMessage(t("opsUsers.memberEnabled"));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.updateError"));
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemove(member: WorkspaceMember) {
    const confirmed = window.confirm(t("opsUsers.removeConfirm").replace("{email}", member.email));
    if (!confirmed) return;
    setBusyId(member.operatorId);
    setError(null);
    setMessage(null);
    try {
      await updateWorkspaceMember(member.operatorId, { isActive: false });
      setMessage(t("opsUsers.memberRemoved"));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.updateError"));
    } finally {
      setBusyId(null);
    }
  }

  async function copyInviteLink() {
    if (!lastInviteLink) return;
    try {
      await navigator.clipboard.writeText(lastInviteLink);
      setMessage(t("opsUsers.inviteLinkCopied"));
    } catch {
      setError(t("opsUsers.copyFailed"));
    }
  }

  const refreshAction = (
    <TopbarRefreshButton busy={loading && members.length > 0} disabled={loading && members.length === 0} onClick={() => void load()} />
  );

  if (loading && members.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsUsers.description")} title={t("opsUsers.title")}>
        <OpsState title={t("opsUsers.loadingTitle")} detail={t("opsUsers.loadingDetail")} />
      </OpsConsoleShell>
    );
  }

  if (error && members.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsUsers.description")} title={t("opsUsers.title")}>
        <OpsState title={t("opsUsers.unavailableTitle")} detail={error} retry={() => void load()} />
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsUsers.description")} title={t("opsUsers.title")}>
      <div className="ops-users ops-users-canvas">
        {error ? <div className="inline-error">{error}</div> : null}
        {message ? <div className="inline-success">{message}</div> : null}

        <section className="ops-users-hero" aria-label={t("opsUsers.summaryLabel")}>
          <div className="ops-users-hero-copy">
            <p className="ops-users-hero-eyebrow">{t("opsUsers.directoryEyebrow")}</p>
            <h2>{t("opsUsers.directoryTitle")}</h2>
            <p>{t("opsUsers.directoryCopy")}</p>
          </div>
          <dl className="ops-users-hero-stats">
            <div>
              <dt>{t("opsUsers.summaryMembers")}</dt>
              <dd>{summary.total}</dd>
            </div>
            <div>
              <dt>{t("opsUsers.summaryActive")}</dt>
              <dd>{summary.active}</dd>
            </div>
            <div>
              <dt>{t("opsUsers.summaryPending")}</dt>
              <dd>{summary.pending}</dd>
            </div>
            <div>
              <dt>{t("opsUsers.summaryDisabled")}</dt>
              <dd>{summary.disabled}</dd>
            </div>
          </dl>
        </section>

        <section className="ops-users-roster">
          <div className="ops-users-toolbar">
            <div className="ops-users-toolbar-filters">
              <label className="ops-users-field is-inline">
                <span className="visually-hidden">{t("opsUsers.searchLabel")}</span>
                <input
                  placeholder={t("opsUsers.searchPlaceholder")}
                  type="search"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                />
              </label>
              <label className="ops-users-field is-inline">
                <span className="visually-hidden">{t("opsUsers.filterRole")}</span>
                <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
                  <option value="all">{t("opsUsers.allRoles")}</option>
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>
                      {t(`opsUsers.roles.${role}`)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className={`ops-users-quiet-btn${pendingOpen ? " is-accent" : ""}`}
                type="button"
                onClick={() => setPendingOpen((open) => !open)}
              >
                {t("opsUsers.pendingInvitesTitle")}
                {summary.pending > 0 ? <span className="ops-users-badge">{summary.pending}</span> : null}
              </button>
            </div>
            <button className="primary ops-users-invite-cta" type="button" onClick={openInviteModal}>
              <InviteIcon />
              {t("opsUsers.inviteMember")}
            </button>
          </div>

          {pendingOpen ? (
            <div className="ops-users-pending">
              {invites.length === 0 ? (
                <div className="ops-users-empty">
                  <strong>{t("opsUsers.noPendingInvites")}</strong>
                  <p>{t("opsUsers.noPendingInvitesHelp")}</p>
                </div>
              ) : (
                <ul className="ops-users-invite-list">
                  {invites.map((invite) => (
                    <li className="ops-users-invite-item" key={invite.inviteId}>
                      <div className="ops-users-invite-meta">
                        <strong>{invite.email}</strong>
                        <span>
                          {t(`opsUsers.roles.${invite.role}`)} · {formatDateTime(invite.expiresAt)}
                        </span>
                      </div>
                      <div className="ops-users-invite-actions">
                        <StatusBadge
                          label={invite.status === "expired" ? t("opsUsers.expired") : t("opsUsers.pending")}
                          tone={invite.status === "expired" ? "warn" : "muted"}
                        />
                        <button
                          className="ops-users-quiet-btn"
                          disabled={busyId === invite.inviteId}
                          type="button"
                          onClick={() => void handleRevoke(invite.inviteId)}
                        >
                          {t("opsUsers.revoke")}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          {filteredMembers.length === 0 ? (
            <div className="ops-users-empty is-featured">
              <strong>{t("opsUsers.noMembersMatch")}</strong>
              <p>{t("opsUsers.noMembersMatchHelp")}</p>
              <button className="primary ops-users-invite-cta" type="button" onClick={openInviteModal}>
                <InviteIcon />
                {t("opsUsers.inviteMember")}
              </button>
            </div>
          ) : (
            <div className="ops-users-table-wrap">
              <table className="ops-users-table">
                <thead>
                  <tr>
                    <th>{t("opsUsers.user")}</th>
                    <th>{t("opsUsers.role")}</th>
                    <th>{t("opsUsers.status")}</th>
                    <th>{t("opsUsers.joined")}</th>
                    <th>{t("opsUsers.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMembers.map((member) => {
                    const isSelf = me?.operatorId === member.operatorId;
                    return (
                      <tr className="ops-users-member-row" key={member.operatorId}>
                        <td>
                          <div className="ops-users-member-identity">
                            <span aria-hidden="true" className={`ops-users-avatar is-${member.role}`}>
                              {memberInitial(member)}
                            </span>
                            <div>
                              <div className="ops-users-member-name">
                                <strong>{member.displayName || member.email}</strong>
                                {isSelf ? <span className="ops-users-you">{t("opsUsers.you")}</span> : null}
                              </div>
                              <span className="ops-users-member-email">{member.email}</span>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={roleChipClass(member.role)}>{t(`opsUsers.roles.${member.role}`)}</span>
                        </td>
                        <td>
                          <StatusBadge
                            label={member.isActive ? t("opsUsers.active") : t("opsUsers.disabled")}
                            tone={member.isActive ? "good" : "danger"}
                          />
                        </td>
                        <td>
                          <span className="ops-users-member-joined">{formatDateTime(member.createdAt)}</span>
                        </td>
                        <td>
                          <div className="ops-users-member-controls">
                            <button
                              className="ops-users-quiet-btn"
                              disabled={busyId === member.operatorId}
                              type="button"
                              onClick={() => openEditModal(member)}
                            >
                              {t("opsUsers.editMember")}
                            </button>
                            {member.isActive ? (
                              <button
                                className="ops-users-quiet-btn is-danger"
                                disabled={busyId === member.operatorId}
                                type="button"
                                onClick={() => void handleRemove(member)}
                              >
                                {t("opsUsers.removeMember")}
                              </button>
                            ) : (
                              <button
                                className="ops-users-quiet-btn is-accent"
                                disabled={busyId === member.operatorId}
                                type="button"
                                onClick={() => void handleEnable(member)}
                              >
                                {t("opsUsers.enable")}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {modalMode ? (
        <div className="ops-users-modal-backdrop" onClick={closeModal} role="presentation">
          <div
            aria-labelledby="ops-users-modal-title"
            aria-modal="true"
            className="ops-users-modal"
            role="dialog"
            onClick={(event) => event.stopPropagation()}
          >
            {modalMode === "invite" ? (
              <>
                <header className="ops-users-modal-header">
                  <p className="ops-users-hero-eyebrow">{t("opsUsers.directoryEyebrow")}</p>
                  <h2 id="ops-users-modal-title">{t("opsUsers.inviteMember")}</h2>
                  <p>{t("opsUsers.inviteHelp")}</p>
                </header>
                <form className="ops-users-invite-form" onSubmit={(event) => void handleInvite(event)}>
                  <label>
                    {t("opsUsers.email")}
                    <input
                      autoComplete="email"
                      required
                      type="email"
                      value={inviteEmail}
                      onChange={(event) => setInviteEmail(event.target.value)}
                    />
                  </label>
                  <label>
                    {t("opsUsers.role")}
                    <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}>
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {t(`opsUsers.roles.${role}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="ops-users-modal-actions">
                    <button type="button" onClick={closeModal}>
                      {t("common.cancel")}
                    </button>
                    <button className="primary" disabled={busyId === "invite"} type="submit">
                      {busyId === "invite" ? t("opsUsers.inviting") : t("opsUsers.sendInvite")}
                    </button>
                  </div>
                </form>
                {lastInviteLink ? (
                  <div className="ops-users-invite-link">
                    <p>{t("opsUsers.inviteLinkHelp")}</p>
                    <code>{lastInviteLink}</code>
                    <button type="button" onClick={() => void copyInviteLink()}>
                      {t("opsUsers.copyInviteLink")}
                    </button>
                  </div>
                ) : null}
              </>
            ) : null}

            {modalMode === "edit" && editingMember ? (
              <>
                <header className="ops-users-modal-header">
                  <p className="ops-users-hero-eyebrow">{t("opsUsers.directoryEyebrow")}</p>
                  <h2 id="ops-users-modal-title">{t("opsUsers.editMember")}</h2>
                  <p>{editingMember.email}</p>
                </header>
                <form className="ops-users-invite-form" onSubmit={(event) => void handleEdit(event)}>
                  <label>
                    {t("opsUsers.role")}
                    <select value={editRole} onChange={(event) => setEditRole(event.target.value)}>
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {t(`opsUsers.roles.${role}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="ops-users-modal-actions">
                    <button type="button" onClick={closeModal}>
                      {t("common.cancel")}
                    </button>
                    <button className="primary" disabled={busyId === editingMember.operatorId} type="submit">
                      {t("opsUsers.saveChanges")}
                    </button>
                  </div>
                </form>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </OpsConsoleShell>
  );
}
