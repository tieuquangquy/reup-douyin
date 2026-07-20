"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createWorkspaceInvite,
  fetchWorkspaceInvites,
  fetchWorkspaceMembers,
  resetWorkspaceMemberPassword,
  revokeWorkspaceInvite,
  rotateWorkspaceInvite,
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

type RosterTab = "members" | "pending";
type AccessFilter = "all" | "active" | "disabled";
type MetricKey = "total" | "active" | "pending" | "disabled";
type OverlayMode = "invite" | "edit" | null;

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

function formatCompactDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function InviteIcon() {
  return (
    <svg aria-hidden="true" className="ops-users-btn-icon" fill="none" viewBox="0 0 16 16">
      <path d="M8 3.2v9.6M3.2 8h9.6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

function EditMemberIcon() {
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
  const [accessFilter, setAccessFilter] = useState<AccessFilter>("all");
  const [tab, setTab] = useState<RosterTab>("members");
  const [overlayMode, setOverlayMode] = useState<OverlayMode>(null);
  const [editingMember, setEditingMember] = useState<WorkspaceMember | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<string>("operator");
  const [editRole, setEditRole] = useState<string>("operator");
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editAddress, setEditAddress] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [lastInviteLink, setLastInviteLink] = useState<string | null>(null);
  const [rotatedLinkByInviteId, setRotatedLinkByInviteId] = useState<Record<string, string>>({});
  const [tempPassword, setTempPassword] = useState<string | null>(null);

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
    const pending = invites.filter((invite) => invite.status === "pending" || invite.status === "expired").length;
    return { active, disabled, pending, total: members.length };
  }, [invites, members]);

  const filteredMembers = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return members.filter((member) => {
      if (roleFilter !== "all" && member.role !== roleFilter) return false;
      if (accessFilter === "active" && !member.isActive) return false;
      if (accessFilter === "disabled" && member.isActive) return false;
      if (!query) return true;
      const haystack = `${member.displayName ?? ""} ${member.email} ${member.phone ?? ""}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [accessFilter, members, roleFilter, searchQuery]);

  function applyMetric(key: MetricKey) {
    if (key === "pending") {
      setTab("pending");
      return;
    }
    setTab("members");
    if (key === "total") setAccessFilter("all");
    if (key === "active") setAccessFilter("active");
    if (key === "disabled") setAccessFilter("disabled");
  }

  function openInviteModal() {
    setOverlayMode("invite");
    setEditingMember(null);
    setInviteEmail("");
    setInviteRole("operator");
    setLastInviteLink(null);
    setTempPassword(null);
    setError(null);
  }

  function openEditDrawer(member: WorkspaceMember) {
    setOverlayMode("edit");
    setEditingMember(member);
    setEditRole(member.role);
    setEditDisplayName(member.displayName ?? "");
    setEditPhone(member.phone ?? "");
    setEditAddress(member.address ?? "");
    setEditNotes(member.notes ?? "");
    setEditActive(member.isActive);
    setTempPassword(null);
    setError(null);
  }

  function closeOverlay() {
    setOverlayMode(null);
    setEditingMember(null);
    setTempPassword(null);
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
      setTab("pending");
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

    if (editActive !== editingMember.isActive && !editActive) {
      const confirmed = window.confirm(t("opsUsers.disableConfirm").replace("{email}", editingMember.email));
      if (!confirmed) return;
    }

    setBusyId(editingMember.operatorId);
    setError(null);
    setMessage(null);
    try {
      await updateWorkspaceMember(editingMember.operatorId, {
        role: editRole,
        isActive: editActive,
        displayName: editDisplayName.trim() || null,
        phone: editPhone.trim() || null,
        address: editAddress.trim() || null,
        notes: editNotes.trim() || null
      });
      setMessage(t("opsUsers.memberUpdated"));
      closeOverlay();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.updateError"));
    } finally {
      setBusyId(null);
    }
  }

  async function handleResetPassword() {
    if (!editingMember) return;
    const confirmed = window.confirm(t("opsUsers.resetPasswordConfirm").replace("{email}", editingMember.email));
    if (!confirmed) return;
    setBusyId(`reset-${editingMember.operatorId}`);
    setError(null);
    setMessage(null);
    try {
      const reset = await resetWorkspaceMemberPassword(editingMember.operatorId);
      setTempPassword(reset.temporaryPassword);
      setMessage(t("opsUsers.resetPasswordDone"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.resetPasswordError"));
    } finally {
      setBusyId(null);
    }
  }

  async function copyTempPassword() {
    if (!tempPassword) return;
    try {
      await navigator.clipboard.writeText(tempPassword);
      setMessage(t("opsUsers.tempPasswordCopied"));
    } catch {
      setError(t("opsUsers.copyFailed"));
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

  async function handleCopyNewInviteLink(inviteId: string) {
    setBusyId(inviteId);
    setError(null);
    setMessage(null);
    try {
      const rotated = await rotateWorkspaceInvite(inviteId);
      const link = `${window.location.origin}/auth/invite?token=${encodeURIComponent(rotated.inviteToken)}`;
      setRotatedLinkByInviteId((current) => ({ ...current, [inviteId]: link }));
      try {
        await navigator.clipboard.writeText(link);
        setMessage(t("opsUsers.inviteLinkRotatedCopied"));
      } catch {
        setMessage(t("opsUsers.inviteLinkRotated"));
        setError(t("opsUsers.copyFailed"));
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsUsers.rotateError"));
    } finally {
      setBusyId(null);
    }
  }

  async function handleStatusToggle(member: WorkspaceMember, nextActive: boolean) {
    if (nextActive === member.isActive) return;
    if (nextActive) {
      await handleEnable(member);
      return;
    }
    await handleRemove(member);
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

  const viewActive: MetricKey =
    tab === "pending" ? "pending" : accessFilter === "active" ? "active" : accessFilter === "disabled" ? "disabled" : "total";

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsUsers.description")} title={t("opsUsers.title")}>
      <div className="ops-users ops-users-canvas ops-users-sheet-page">
        {error ? <div className="inline-error">{error}</div> : null}
        {message ? <div className="inline-success">{message}</div> : null}

        <header className="ops-users-chrome">
          <div className="ops-users-chrome__lead">
            <p className="ops-users-hero-eyebrow">{t("opsUsers.directoryEyebrow")}</p>
            <h2>{t("opsUsers.directoryTitle")}</h2>
            <p className="ops-users-chrome__copy">{t("opsUsers.directoryCopy")}</p>
          </div>

          <div className="ops-users-chrome__tools" aria-label={t("opsUsers.summaryLabel")}>
            <nav className="ops-users-views" aria-label={t("opsUsers.viewsLabel")}>
              {(
                [
                  ["total", t("opsUsers.summaryMembers"), summary.total],
                  ["active", t("opsUsers.summaryActive"), summary.active],
                  ["pending", t("opsUsers.summaryPending"), summary.pending],
                  ["disabled", t("opsUsers.summaryDisabled"), summary.disabled]
                ] as const
              ).map(([key, label, value]) => (
                <button
                  key={key}
                  aria-pressed={viewActive === key}
                  className={`ops-users-views__btn${viewActive === key ? " is-active" : ""}`}
                  type="button"
                  onClick={() => applyMetric(key)}
                >
                  {label}
                  <span>{value}</span>
                </button>
              ))}
            </nav>

            <div className="ops-users-toolbar">
              <div className="ops-users-toolbar-filters">
                <label className="ops-users-field is-inline">
                  <span className="visually-hidden">{t("opsUsers.filterRole")}</span>
                  <select
                    value={roleFilter}
                    onChange={(event) => {
                      setRoleFilter(event.target.value);
                      if (tab === "pending") setTab("members");
                    }}
                  >
                    <option value="all">{t("opsUsers.allRoles")}</option>
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role} value={role}>
                        {t(`opsUsers.roles.${role}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="ops-users-field is-inline ops-users-search">
                  <span className="visually-hidden">{t("opsUsers.searchLabel")}</span>
                  <input
                    placeholder={t("opsUsers.searchPlaceholder")}
                    type="search"
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                  />
                </label>
                <button className="primary ops-users-invite-cta" type="button" onClick={openInviteModal}>
                  <InviteIcon />
                  {t("opsUsers.inviteMember")}
                </button>
              </div>
            </div>
          </div>
        </header>

        <section className="ops-users-sheet" aria-label={t("opsUsers.membersTitle")}>
          <div className="ops-users-sheet__bar">
            <p className="ops-users-toolbar-meta">
              {tab === "members"
                ? t("opsUsers.showingCount")
                    .replace("{shown}", String(filteredMembers.length))
                    .replace("{total}", String(summary.total))
                : t("opsUsers.pendingInvitesHelp")}
            </p>
          </div>

          {tab === "members" ? (
            filteredMembers.length === 0 ? (
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
                      <th>{t("opsUsers.lastActive")}</th>
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
                                {member.phone ? <span className="ops-users-member-phone">{member.phone}</span> : null}
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className={roleChipClass(member.role)}>{t(`opsUsers.roles.${member.role}`)}</span>
                          </td>
                          <td>
                            <label
                              className="ops-tts-setup-switch"
                              title={member.isActive ? t("opsUsers.active") : t("opsUsers.disabled")}
                            >
                              <input
                                type="checkbox"
                                checked={member.isActive}
                                disabled={busyId === member.operatorId}
                                aria-label={
                                  member.isActive ? t("opsUsers.active") : t("opsUsers.disabled")
                                }
                                onChange={(event) =>
                                  void handleStatusToggle(member, event.target.checked)
                                }
                              />
                              <span className="ops-tts-setup-switch__track" aria-hidden="true" />
                            </label>
                          </td>
                          <td>
                            <span className="ops-users-member-joined" title={formatDateTime(member.createdAt)}>
                              {formatCompactDate(member.createdAt)}
                            </span>
                          </td>
                          <td>
                            <span
                              className="ops-users-member-joined"
                              title={member.lastSeenAt ? formatDateTime(member.lastSeenAt) : undefined}
                            >
                              {member.lastSeenAt
                                ? formatCompactDate(member.lastSeenAt)
                                : t("opsUsers.neverSignedIn")}
                            </span>
                          </td>
                          <td className="ops-users-table__actions">
                            <div className="ops-users-member-controls">
                              <button
                                type="button"
                                className="ops-tts-setup-table__icon-btn"
                                disabled={busyId === member.operatorId}
                                aria-label={t("opsUsers.editMember")}
                                title={t("opsUsers.editMember")}
                                onClick={() => openEditDrawer(member)}
                              >
                                <EditMemberIcon />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            <div className="ops-users-pending">
              {invites.length === 0 ? (
                <div className="ops-users-empty">
                  <strong>{t("opsUsers.noPendingInvites")}</strong>
                  <p>{t("opsUsers.noPendingInvitesHelp")}</p>
                </div>
              ) : (
                <div className="ops-users-table-wrap">
                  <table className="ops-users-table">
                    <thead>
                      <tr>
                        <th>{t("opsUsers.email")}</th>
                        <th>{t("opsUsers.role")}</th>
                        <th>{t("opsUsers.status")}</th>
                        <th>{t("opsUsers.expires")}</th>
                        <th>{t("opsUsers.actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invites.map((invite) => (
                        <tr className="ops-users-member-row" key={invite.inviteId}>
                          <td>
                            <strong>{invite.email}</strong>
                          </td>
                          <td>
                            <span className={roleChipClass(invite.role)}>{t(`opsUsers.roles.${invite.role}`)}</span>
                          </td>
                          <td>
                            <StatusBadge
                              label={invite.status === "expired" ? t("opsUsers.expired") : t("opsUsers.pending")}
                              tone={invite.status === "expired" ? "warn" : "muted"}
                            />
                          </td>
                          <td>
                            <span className="ops-users-member-joined" title={formatDateTime(invite.expiresAt)}>
                              {formatCompactDate(invite.expiresAt)}
                            </span>
                          </td>
                          <td>
                            <div className="ops-users-member-controls">
                              <button
                                className="ops-users-quiet-btn is-accent"
                                disabled={busyId === invite.inviteId}
                                title={t("opsUsers.copyNewLinkHelp")}
                                type="button"
                                onClick={() => void handleCopyNewInviteLink(invite.inviteId)}
                              >
                                {t("opsUsers.copyNewLink")}
                              </button>
                              <button
                                className="ops-users-quiet-btn"
                                disabled={busyId === invite.inviteId}
                                type="button"
                                onClick={() => void handleRevoke(invite.inviteId)}
                              >
                                {t("opsUsers.revoke")}
                              </button>
                            </div>
                            {rotatedLinkByInviteId[invite.inviteId] ? (
                              <div className="ops-users-invite-link is-inline">
                                <p>{t("opsUsers.inviteLinkHelp")}</p>
                                <code>{rotatedLinkByInviteId[invite.inviteId]}</code>
                              </div>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {overlayMode === "invite" ? (
        <div className="ops-users-modal-backdrop" onClick={closeOverlay} role="presentation">
          <div
            aria-labelledby="ops-users-modal-title"
            aria-modal="true"
            className="ops-users-modal"
            role="dialog"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="ops-users-modal-header">
              <p className="ops-users-hero-eyebrow">{t("opsUsers.directoryEyebrow")}</p>
              <h2 id="ops-users-modal-title">{t("opsUsers.inviteMember")}</h2>
              <p>{t("opsUsers.inviteHelp")}</p>
            </header>
            <form className="ops-users-invite-form" onSubmit={(event) => void handleInvite(event)}>
              <label>
                {t("opsUsers.email")}
                <input
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
                <button type="button" onClick={closeOverlay}>
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
          </div>
        </div>
      ) : null}

      {overlayMode === "edit" && editingMember ? (
        <div className="ops-users-drawer-backdrop" onClick={closeOverlay} role="presentation">
          <aside
            aria-labelledby="ops-users-drawer-title"
            className="ops-users-drawer"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="ops-users-drawer-header">
              <div className="ops-users-edit-identity">
                <span aria-hidden="true" className={`ops-users-avatar is-${editingMember.role}`}>
                  {memberInitial(editingMember)}
                </span>
                <div>
                  <h2 id="ops-users-drawer-title">{t("opsUsers.editMemberTitle")}</h2>
                  <strong>{editingMember.displayName || editingMember.email}</strong>
                  <span className="ops-users-member-email">{editingMember.email}</span>
                </div>
                <StatusBadge
                  label={editingMember.isActive ? t("opsUsers.active") : t("opsUsers.disabled")}
                  tone={editingMember.isActive ? "good" : "danger"}
                />
              </div>
              <button className="ops-users-drawer-close" type="button" aria-label={t("common.close")} onClick={closeOverlay}>
                ×
              </button>
            </header>

            <form className="ops-users-drawer-form" onSubmit={(event) => void handleEdit(event)}>
              <div className="ops-users-drawer__body">
                <section className="ops-users-section">
                  <h3>{t("opsUsers.profileSection")}</h3>
                  <div className="ops-users-field-grid">
                    <label className="ops-users-field">
                      {t("opsUsers.displayName")}
                      <input
                        maxLength={160}
                        type="text"
                        value={editDisplayName}
                        onChange={(event) => setEditDisplayName(event.target.value)}
                        placeholder={t("opsUsers.displayNamePlaceholder")}
                      />
                    </label>
                    <label className="ops-users-field">
                      {t("opsUsers.phone")}
                      <input
                        maxLength={40}
                        type="tel"
                        value={editPhone}
                        onChange={(event) => setEditPhone(event.target.value)}
                        placeholder={t("opsUsers.phonePlaceholder")}
                      />
                    </label>
                  </div>
                  <div className="ops-users-email-readonly">
                    <span>{t("opsUsers.email")}</span>
                    <strong>{editingMember.email}</strong>
                    <small>{t("opsUsers.emailReadOnlyHelp")}</small>
                  </div>
                  <label className="ops-users-field">
                    {t("opsUsers.address")}
                    <input
                      maxLength={320}
                      type="text"
                      value={editAddress}
                      onChange={(event) => setEditAddress(event.target.value)}
                      placeholder={t("opsUsers.addressPlaceholder")}
                    />
                  </label>
                  <label className="ops-users-field">
                    {t("opsUsers.notes")}
                    <textarea
                      maxLength={2000}
                      rows={2}
                      value={editNotes}
                      onChange={(event) => setEditNotes(event.target.value)}
                      placeholder={t("opsUsers.notesPlaceholder")}
                    />
                  </label>
                </section>

                <section className="ops-users-section">
                  <h3>{t("opsUsers.accessSection")}</h3>
                  <label className="ops-users-field">
                    {t("opsUsers.role")}
                    <select value={editRole} onChange={(event) => setEditRole(event.target.value)}>
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {t(`opsUsers.roles.${role}`)}
                        </option>
                      ))}
                    </select>
                    <span className="ops-users-field-hint">{t(`opsUsers.roleHints.${editRole}`)}</span>
                  </label>
                  <label className="ops-users-switch">
                    <input
                      checked={editActive}
                      type="checkbox"
                      onChange={(event) => setEditActive(event.target.checked)}
                    />
                    <span className="ops-users-switch__track" aria-hidden="true" />
                    <span className="ops-users-switch__copy">
                      <strong>{t("opsUsers.accessActive")}</strong>
                      <small>{t("opsUsers.accessActiveHelp")}</small>
                    </span>
                  </label>
                </section>

                <section className="ops-users-section ops-users-section--security">
                  <div className="ops-users-security-row">
                    <div>
                      <h3>{t("opsUsers.securitySection")}</h3>
                      <p>{t("opsUsers.resetPasswordHelp")}</p>
                    </div>
                    <button
                      className="ops-users-quiet-btn"
                      disabled={busyId === `reset-${editingMember.operatorId}`}
                      type="button"
                      onClick={() => void handleResetPassword()}
                    >
                      {t("opsUsers.resetPassword")}
                    </button>
                  </div>
                  {tempPassword ? (
                    <div className="ops-users-invite-link">
                      <p>{t("opsUsers.tempPasswordHelp")}</p>
                      <code>{tempPassword}</code>
                      <button type="button" onClick={() => void copyTempPassword()}>
                        {t("opsUsers.copyTempPassword")}
                      </button>
                    </div>
                  ) : null}
                </section>
              </div>

              <div className="ops-users-drawer__footer">
                <button type="button" onClick={closeOverlay}>
                  {t("common.cancel")}
                </button>
                <button className="primary" disabled={busyId === editingMember.operatorId} type="submit">
                  {t("opsUsers.saveChanges")}
                </button>
              </div>
            </form>
          </aside>
        </div>
      ) : null}
    </OpsConsoleShell>
  );
}
