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
import { useAsyncAction } from "../../lib/useAsyncAction";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { StatusBadge } from "../app-shell/StatusBadge";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
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
  const [actionError, setActionError] = useState<string | null>(null);
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
  const action = useAsyncAction();
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load(mode: LatestRequestMode = members.length || invites.length ? "refresh" : "initial") {
    await request.run(
      async () => Promise.all([fetchWorkspaceMembers(), fetchWorkspaceInvites()]),
      ([nextMembers, nextInvites]) => {
        setMembers(nextMembers);
        setInvites(nextInvites);
      },
      mode
    ).catch(() => undefined);
  }

  useEffect(() => {
    void load("initial");
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
    setActionError(null);
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
    setActionError(null);
  }

  function closeOverlay() {
    setOverlayMode(null);
    setEditingMember(null);
    setTempPassword(null);
  }

  async function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await action.run("invite", async () => {
      setActionError(null);
      try {
        const created = await createWorkspaceInvite({ email: inviteEmail.trim(), role: inviteRole });
        const link = `${window.location.origin}/auth/invite?token=${encodeURIComponent(created.inviteToken)}`;
        setLastInviteLink(link);
        notify({ message: t("opsUsers.inviteCreated"), tone: "success" });
        setInviteEmail("");
        setInviteRole("operator");
        setTab("pending");
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsUsers.inviteError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingMember) return;

    if (editActive !== editingMember.isActive && !editActive) {
      const confirmed = window.confirm(t("opsUsers.disableConfirm").replace("{email}", editingMember.email));
      if (!confirmed) return;
    }

    await action.run(`member-${editingMember.operatorId}`, async () => {
      setActionError(null);
      try {
        await updateWorkspaceMember(editingMember.operatorId, {
          role: editRole,
          isActive: editActive,
          displayName: editDisplayName.trim() || null,
          phone: editPhone.trim() || null,
          address: editAddress.trim() || null,
          notes: editNotes.trim() || null
        });
        notify({ message: t("opsUsers.memberUpdated"), tone: "success" });
        closeOverlay();
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsUsers.updateError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function handleResetPassword() {
    if (!editingMember) return;
    const confirmed = window.confirm(t("opsUsers.resetPasswordConfirm").replace("{email}", editingMember.email));
    if (!confirmed) return;
    await action.run(`reset-${editingMember.operatorId}`, async () => {
      setActionError(null);
      try {
        const reset = await resetWorkspaceMemberPassword(editingMember.operatorId);
        setTempPassword(reset.temporaryPassword);
        notify({ message: t("opsUsers.resetPasswordDone"), tone: "success" });
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsUsers.resetPasswordError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function copyTempPassword() {
    if (!tempPassword) return;
    await action.run("copy-temp-password", async () => {
      try {
        await navigator.clipboard.writeText(tempPassword);
        notify({ message: t("opsUsers.tempPasswordCopied"), tone: "success" });
      } catch {
        setActionError(t("opsUsers.copyFailed"));
        notify({ message: t("opsUsers.copyFailed"), tone: "error" });
      }
    });
  }

  async function handleRevoke(inviteId: string) {
    await action.run(`invite-${inviteId}`, async () => {
      setActionError(null);
      try {
        await revokeWorkspaceInvite(inviteId);
        notify({ message: t("opsUsers.inviteRevoked"), tone: "success" });
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsUsers.revokeError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function handleCopyNewInviteLink(inviteId: string) {
    await action.run(`invite-${inviteId}`, async () => {
      setActionError(null);
      try {
        const rotated = await rotateWorkspaceInvite(inviteId);
        const link = `${window.location.origin}/auth/invite?token=${encodeURIComponent(rotated.inviteToken)}`;
        setRotatedLinkByInviteId((current) => ({ ...current, [inviteId]: link }));
        try {
          await navigator.clipboard.writeText(link);
          notify({ message: t("opsUsers.inviteLinkRotatedCopied"), tone: "success" });
        } catch {
          setActionError(t("opsUsers.copyFailed"));
          notify({ message: t("opsUsers.inviteLinkRotated"), tone: "success" });
          notify({ message: t("opsUsers.copyFailed"), tone: "error" });
        }
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsUsers.rotateError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
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
    await updateMemberStatus(member, true, t("opsUsers.memberEnabled"));
  }

  async function handleRemove(member: WorkspaceMember) {
    const confirmed = window.confirm(t("opsUsers.removeConfirm").replace("{email}", member.email));
    if (!confirmed) return;
    await updateMemberStatus(member, false, t("opsUsers.memberRemoved"));
  }

  async function updateMemberStatus(member: WorkspaceMember, isActive: boolean, successMessage: string) {
    await action.run(`member-${member.operatorId}`, async () => {
      setActionError(null);
      try {
        await updateWorkspaceMember(member.operatorId, { isActive });
        notify({ message: successMessage, tone: "success" });
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsUsers.updateError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function copyInviteLink() {
    if (!lastInviteLink) return;
    await action.run("copy-invite-link", async () => {
      try {
        await navigator.clipboard.writeText(lastInviteLink);
        notify({ message: t("opsUsers.inviteLinkCopied"), tone: "success" });
      } catch {
        setActionError(t("opsUsers.copyFailed"));
        notify({ message: t("opsUsers.copyFailed"), tone: "error" });
      }
    });
  }

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load("refresh")} />
  );
  const hasRosterData = members.length > 0 || invites.length > 0;
  const boundaryStatus = request.initialLoading && !hasRosterData ? "loading" : request.error && !hasRosterData ? "error" : "success";
  const inlineError = actionError ?? (hasRosterData ? request.error?.message ?? null : null);

  const viewActive: MetricKey =
    tab === "pending" ? "pending" : accessFilter === "active" ? "active" : accessFilter === "disabled" ? "disabled" : "total";

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsUsers.description")} title={t("opsUsers.title")}>
      <AsyncContentBoundary
        refreshing={request.refreshing}
        status={boundaryStatus}
        skeleton={<OpsState title={t("opsUsers.loadingTitle")} detail={t("opsUsers.loadingDetail")} />}
        errorState={<OpsState title={t("opsUsers.unavailableTitle")} detail={request.error?.message ?? t("opsUsers.loadError")} retry={() => void load("initial")} />}
      >
      <div className="ops-users ops-users-canvas ops-users-sheet-page">
        {inlineError ? <div className="inline-error">{inlineError}</div> : null}

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
                                disabled={action.isPending(`member-${member.operatorId}`)}
                                aria-busy={action.isPending(`member-${member.operatorId}`) || undefined}
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
                                disabled={action.isPending(`member-${member.operatorId}`)}
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
                              <AsyncButton
                                className="ops-users-quiet-btn is-accent"
                                pending={action.isPending(`invite-${invite.inviteId}`)}
                                pendingLabel={t("opsUsers.copyNewLink")}
                                title={t("opsUsers.copyNewLinkHelp")}
                                onClick={() => void handleCopyNewInviteLink(invite.inviteId)}
                              >
                                {t("opsUsers.copyNewLink")}
                              </AsyncButton>
                              <AsyncButton
                                className="ops-users-quiet-btn"
                                pending={action.isPending(`invite-${invite.inviteId}`)}
                                pendingLabel={t("opsUsers.revoke")}
                                onClick={() => void handleRevoke(invite.inviteId)}
                              >
                                {t("opsUsers.revoke")}
                              </AsyncButton>
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
                <AsyncButton
                  className="primary"
                  pending={action.isPending("invite")}
                  pendingLabel={t("opsUsers.inviting")}
                  type="submit"
                >
                  {t("opsUsers.sendInvite")}
                </AsyncButton>
              </div>
            </form>
            {lastInviteLink ? (
              <div className="ops-users-invite-link">
                <p>{t("opsUsers.inviteLinkHelp")}</p>
                <code>{lastInviteLink}</code>
                <AsyncButton
                  pending={action.isPending("copy-invite-link")}
                  pendingLabel={t("opsUsers.copyInviteLink")}
                  onClick={() => void copyInviteLink()}
                >
                  {t("opsUsers.copyInviteLink")}
                </AsyncButton>
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
                    <AsyncButton
                      className="ops-users-quiet-btn"
                      pending={action.isPending(`reset-${editingMember.operatorId}`)}
                      pendingLabel={t("opsUsers.resetPassword")}
                      onClick={() => void handleResetPassword()}
                    >
                      {t("opsUsers.resetPassword")}
                    </AsyncButton>
                  </div>
                  {tempPassword ? (
                    <div className="ops-users-invite-link">
                      <p>{t("opsUsers.tempPasswordHelp")}</p>
                      <code>{tempPassword}</code>
                      <AsyncButton
                        pending={action.isPending("copy-temp-password")}
                        pendingLabel={t("opsUsers.copyTempPassword")}
                        onClick={() => void copyTempPassword()}
                      >
                        {t("opsUsers.copyTempPassword")}
                      </AsyncButton>
                    </div>
                  ) : null}
                </section>
              </div>

              <div className="ops-users-drawer__footer">
                <button type="button" onClick={closeOverlay}>
                  {t("common.cancel")}
                </button>
                <AsyncButton
                  className="primary"
                  pending={action.isPending(`member-${editingMember.operatorId}`)}
                  pendingLabel={t("opsUsers.saveChanges")}
                  type="submit"
                >
                  {t("opsUsers.saveChanges")}
                </AsyncButton>
              </div>
            </form>
          </aside>
        </div>
      ) : null}
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
