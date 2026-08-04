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
type AccessFilter = "all" | "active" | "disabled" | "never";
type InviteStatusFilter = "all" | "pending" | "expired";
type MemberSortKey = "name" | "access" | "joined" | "lastSignIn";
type SortDirection = "asc" | "desc";
type OverlayMode = "invite" | "edit" | null;

function memberInitial(member: WorkspaceMember): string {
  const source = (member.displayName || member.email || "?").trim();
  return (source[0] || "?").toUpperCase();
}

function formatCompactDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${day}/${month}/${date.getFullYear()}`;
}

function formatExpiry(value: string): string {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "—";
  const seconds = Math.floor((timestamp - Date.now()) / 1000);
  if (seconds <= 0) return "Expired";
  if (seconds < 3600) return `${Math.ceil(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.ceil(seconds / 3600)}h`;
  return `${Math.ceil(seconds / 86400)}d`;
}

function dateTimestamp(value: string | null | undefined): number {
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function lastSignInTone(value: string | null | undefined): "recent" | "standard" | "stale" | "never" {
  const timestamp = dateTimestamp(value);
  if (!timestamp) return "never";
  const ageDays = (Date.now() - timestamp) / 86_400_000;
  if (ageDays <= 7) return "recent";
  if (ageDays > 30) return "stale";
  return "standard";
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

type OpsUsersUiIconKind = "access" | "cancel" | "close" | "copy" | "invite" | "mail" | "profile" | "save" | "security" | "send";

function OpsUsersUiIcon({ kind }: { kind: OpsUsersUiIconKind }) {
  if (kind === "close") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><path d="m7 7 10 10M17 7 7 17" /></svg>;
  }
  if (kind === "cancel") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><path d="M19 12H5m5-5-5 5 5 5" /></svg>;
  }
  if (kind === "mail") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><rect height="14" rx="2.5" width="18" x="3" y="5" /><path d="m4.5 7 7.5 5.5L19.5 7" /></svg>;
  }
  if (kind === "invite") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.5" /><path d="M3.5 19c.7-3.2 2.5-4.8 5.5-4.8s4.8 1.6 5.5 4.8M18 7v6m-3-3h6" /></svg>;
  }
  if (kind === "send") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><path d="m3.5 5 17 7-17 7 3.3-7L3.5 5Z" /><path d="M7 12h8" /></svg>;
  }
  if (kind === "save") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><path d="m5 12.5 4.2 4.2L19 7" /></svg>;
  }
  if (kind === "copy") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><rect height="13" rx="2" width="12" x="8" y="7" /><path d="M16 7V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h2" /></svg>;
  }
  if (kind === "profile") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5" /><path d="M5 19c.8-3.7 3.1-5.5 7-5.5s6.2 1.8 7 5.5" /></svg>;
  }
  if (kind === "access") {
    return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><path d="M12 3.5 19 6v5.2c0 4.2-2.6 7.4-7 9.3-4.4-1.9-7-5.1-7-9.3V6l7-2.5Z" /><path d="m9 12 2 2 4-4" /></svg>;
  }
  return <svg aria-hidden="true" className="ops-users-ui-icon" fill="none" viewBox="0 0 24 24"><circle cx="8" cy="12" r="3" /><path d="M11 12h9m-3 0v3m-3-3v3" /></svg>;
}

type AccessSignalIconKind = "pending" | "expired" | "disabled" | "unseen" | "owner";

function AccessSignalIcon({ kind }: { kind: AccessSignalIconKind }) {
  if (kind === "pending" || kind === "unseen") {
    return <svg className="ops-users-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>;
  }
  if (kind === "expired") {
    return <svg className="ops-users-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.7 21 20H3L12 3.7Z" /><path d="M12 9.5v5M12 17.3v.1" /></svg>;
  }
  if (kind === "disabled") {
    return <svg className="ops-users-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="m8.8 8.8 6.4 6.4m0-6.4-6.4 6.4" /></svg>;
  }
  return <svg className="ops-users-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 19 6v5.2c0 4.2-2.6 7.4-7 9.3-4.4-1.9-7-5.1-7-9.3V6l7-2.5Z" /><path d="m9 12 2 2 4-4" /></svg>;
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
  const [inviteStatusFilter, setInviteStatusFilter] = useState<InviteStatusFilter>("all");
  const [memberSortKey, setMemberSortKey] = useState<MemberSortKey>("name");
  const [memberSortDirection, setMemberSortDirection] = useState<SortDirection>("asc");
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
    const pendingInvites = invites.filter((invite) => invite.status === "pending").length;
    const expiredInvites = invites.filter((invite) => invite.status === "expired").length;
    const neverSignedIn = members.filter((member) => !member.lastSeenAt).length;
    return {
      active,
      disabled,
      expiredInvites,
      neverSignedIn,
      pending: pendingInvites + expiredInvites,
      pendingInvites,
      total: members.length,
    };
  }, [invites, members]);
  const activeOwnerCount = useMemo(
    () => members.filter((member) => member.role === "owner" && member.isActive).length,
    [members]
  );
  const canManageOwners = me?.roles.includes("owner") ?? false;
  const assignableRoles = canManageOwners ? ROLE_OPTIONS : ROLE_OPTIONS.filter((role) => role !== "owner");
  const criticalSignalCount = summary.expiredInvites + (summary.total > 0 && activeOwnerCount === 0 ? 1 : 0);
  const watchSignalCount =
    summary.pendingInvites
    + summary.disabled
    + summary.neverSignedIn
    + (summary.total > 1 && activeOwnerCount === 1 ? 1 : 0);

  const filteredMembers = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return members.filter((member) => {
      if (roleFilter !== "all" && member.role !== roleFilter) return false;
      if (accessFilter === "active" && !member.isActive) return false;
      if (accessFilter === "disabled" && member.isActive) return false;
      if (accessFilter === "never" && member.lastSeenAt) return false;
      if (!query) return true;
      const haystack = `${member.displayName ?? ""} ${member.email} ${member.phone ?? ""}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [accessFilter, members, roleFilter, searchQuery]);

  const filteredInvites = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return invites.filter((invite) => {
      if (roleFilter !== "all" && invite.role !== roleFilter) return false;
      if (inviteStatusFilter !== "all" && invite.status !== inviteStatusFilter) return false;
      if (!query) return true;
      return `${invite.email} ${invite.note ?? ""}`.toLowerCase().includes(query);
    });
  }, [inviteStatusFilter, invites, roleFilter, searchQuery]);

  const sortedFilteredMembers = useMemo(() => {
    const direction = memberSortDirection === "asc" ? 1 : -1;
    return [...filteredMembers].sort((left, right) => {
      let comparison = 0;
      if (memberSortKey === "name") {
        comparison = (left.displayName || left.email).localeCompare(right.displayName || right.email, undefined, { sensitivity: "base" });
      } else if (memberSortKey === "access") {
        comparison = Number(left.isActive) - Number(right.isActive);
      } else if (memberSortKey === "joined") {
        comparison = dateTimestamp(left.createdAt) - dateTimestamp(right.createdAt);
      } else {
        comparison = dateTimestamp(left.lastSeenAt) - dateTimestamp(right.lastSeenAt);
      }
      if (comparison === 0) comparison = left.email.localeCompare(right.email, undefined, { sensitivity: "base" });
      return comparison * direction;
    });
  }, [filteredMembers, memberSortDirection, memberSortKey]);

  function toggleMemberSort(key: MemberSortKey) {
    if (memberSortKey === key) {
      setMemberSortDirection((current) => current === "asc" ? "desc" : "asc");
      return;
    }
    setMemberSortKey(key);
    setMemberSortDirection(key === "name" ? "asc" : "desc");
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

    if (editingMember.operatorId === me?.operatorId && !editActive) {
      setActionError(t("opsUsers.selfDisableBlocked"));
      return;
    }

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
    if (member.operatorId === me?.operatorId && !nextActive) {
      setActionError(t("opsUsers.selfDisableBlocked"));
      notify({ message: t("opsUsers.selfDisableBlocked"), tone: "error" });
      return;
    }
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

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsUsers.description")} title={t("opsUsers.title")}>
      <AsyncContentBoundary
        refreshing={request.refreshing}
        status={boundaryStatus}
        skeletonVariant="table"
        loadingLabel={t("opsUsers.loadingDetail")}
        errorState={<OpsState title={t("opsUsers.unavailableTitle")} detail={request.error?.message ?? t("opsUsers.loadError")} retry={() => void load("initial")} />}
      >
      <div className="ops-users ops-users-canvas ops-users-sheet-page">
        {inlineError ? <div className="inline-error">{inlineError}</div> : null}

        <section className="ops-users-command-table" aria-label={t("opsUsers.summaryLabel")}>

          <header className="ops-users-command-table__command">
            <div className="ops-users-command-table__views">
              <nav className="ops-users-command-table__tabs" aria-label={t("opsUsers.viewsLabel")}>
                <button type="button" className={tab === "members" ? "is-active" : ""} aria-pressed={tab === "members"} onClick={() => { setTab("members"); setRoleFilter("all"); }}>
                  {t("opsUsers.summaryMembers")}<span>{summary.total}</span>
                </button>
                <button type="button" className={tab === "pending" ? "is-active" : ""} aria-pressed={tab === "pending"} onClick={() => { setTab("pending"); setRoleFilter("all"); }}>
                  {t("opsUsers.summaryPending")}<span>{summary.pending}</span>
                </button>
              </nav>
              <span className="ops-users-command-table__count">
                {(tab === "members" ? t("opsUsers.showingCount") : t("opsUsers.showingInvites"))
                  .replace("{shown}", String(tab === "members" ? sortedFilteredMembers.length : filteredInvites.length))
                  .replace("{total}", String(tab === "members" ? summary.total : invites.length))}
              </span>
              {criticalSignalCount + watchSignalCount > 0 ? <span className="ops-users-command-table__review"><AccessSignalIcon kind={criticalSignalCount > 0 ? "expired" : "unseen"} /><strong>{criticalSignalCount + watchSignalCount}</strong>{t("opsUsers.signalsNeedReview")}</span> : null}
            </div>

            <div className="ops-users-command-table__tools">
              <label className="ops-users-field is-inline ops-users-search">
                <span className="visually-hidden">{t("opsUsers.searchLabel")}</span>
                <input placeholder={t("opsUsers.searchPlaceholder")} type="search" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} />
              </label>
              <label className="ops-users-field is-inline">
                <span className="visually-hidden">{t("opsUsers.filterRole")}</span>
                <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
                  <option value="all">{t("opsUsers.allRoles")}</option>
                  {ROLE_OPTIONS.map((role) => <option key={role} value={role}>{t(`opsUsers.roles.${role}`)}</option>)}
                </select>
              </label>
              {tab === "members" ? (
                <label className="ops-users-field is-inline">
                  <span className="visually-hidden">{t("opsUsers.filterAccess")}</span>
                  <select value={accessFilter} onChange={(event) => setAccessFilter(event.target.value as AccessFilter)}>
                    <option value="all">{t("opsUsers.allAccess")}</option>
                    <option value="active">{t("opsUsers.active")}</option>
                    <option value="disabled">{t("opsUsers.disabled")}</option>
                    <option value="never">{t("opsUsers.neverSignedInShort")}</option>
                  </select>
                </label>
              ) : (
                <label className="ops-users-field is-inline">
                  <span className="visually-hidden">{t("opsUsers.status")}</span>
                  <select value={inviteStatusFilter} onChange={(event) => setInviteStatusFilter(event.target.value as InviteStatusFilter)}>
                    <option value="all">{t("opsUsers.allAccess")}</option>
                    <option value="pending">{t("opsUsers.pending")}</option>
                    <option value="expired">{t("opsUsers.expired")}</option>
                  </select>
                </label>
              )}
              <button className="primary ops-users-invite-cta" type="button" onClick={openInviteModal}><InviteIcon />{t("opsUsers.inviteMember")}</button>
            </div>
          </header>

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
              <div className="ops-users-command-table__viewport">
                <table className="ops-users-command-table__table">
                  <thead>
                    <tr>
                      <th aria-sort={memberSortKey === "name" ? memberSortDirection === "asc" ? "ascending" : "descending" : "none"}>
                        <button type="button" onClick={() => toggleMemberSort("name")}>{t("opsUsers.user")}<i aria-hidden="true">{memberSortKey === "name" ? memberSortDirection === "asc" ? "↑" : "↓" : "↕"}</i></button>
                      </th>
                      <th>{t("opsUsers.role")}</th>
                      <th aria-sort={memberSortKey === "access" ? memberSortDirection === "asc" ? "ascending" : "descending" : "none"}>
                        <button type="button" onClick={() => toggleMemberSort("access")}>{t("opsUsers.status")}<i aria-hidden="true">{memberSortKey === "access" ? memberSortDirection === "asc" ? "↑" : "↓" : "↕"}</i></button>
                      </th>
                      <th className="ops-users-command-table__session-head">
                        <span>{t("opsUsers.sessionTimeline")}</span>
                        <span>
                          <button type="button" aria-pressed={memberSortKey === "lastSignIn"} onClick={() => toggleMemberSort("lastSignIn")}>{t("opsUsers.lastSignIn")}<i aria-hidden="true">{memberSortKey === "lastSignIn" ? memberSortDirection === "asc" ? "↑" : "↓" : "↕"}</i></button>
                          <button type="button" aria-pressed={memberSortKey === "joined"} onClick={() => toggleMemberSort("joined")}>{t("opsUsers.joined")}<i aria-hidden="true">{memberSortKey === "joined" ? memberSortDirection === "asc" ? "↑" : "↓" : "↕"}</i></button>
                        </span>
                      </th>
                      <th>{t("opsUsers.accessReview")}</th>
                      <th aria-label={t("opsUsers.actions")} />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedFilteredMembers.map((member) => {
                      const isSelf = me?.operatorId === member.operatorId;
                      const protectedOwner = member.role === "owner" && member.isActive && activeOwnerCount === 1;
                      const signInTone = lastSignInTone(member.lastSeenAt);
                      const signalCount = Number(!member.isActive) + Number(!member.lastSeenAt) + Number(protectedOwner);
                      const primarySignalKind: AccessSignalIconKind | null = !member.isActive ? "disabled" : !member.lastSeenAt ? "unseen" : protectedOwner ? "owner" : null;
                      const primarySignalLabel = !member.isActive
                        ? t("opsUsers.disabled")
                        : !member.lastSeenAt
                          ? t("opsUsers.neverSignedInShort")
                          : protectedOwner
                            ? t("opsUsers.protectedOwner")
                            : t("opsUsers.stableShort");
                      return (
                        <tr className={`ops-users-command-row is-${primarySignalKind ?? "clear"}${member.isActive ? "" : " is-disabled"}`} key={member.operatorId}>
                          <td className="ops-users-command-row__user">
                            <button
                              type="button"
                              className="ops-users-command-identity"
                              disabled={action.isPending(`member-${member.operatorId}`) || (member.role === "owner" && !canManageOwners)}
                              title={t("opsUsers.editMember")}
                              onClick={() => openEditDrawer(member)}
                            >
                              <span aria-hidden="true" className={`ops-users-avatar is-${member.role}`}>{memberInitial(member)}</span>
                              <span>
                                <span className="ops-users-member-name"><strong>{member.displayName || member.email}</strong>{isSelf ? <span className="ops-users-you">{t("opsUsers.you")}</span> : null}</span>
                                <span className="ops-users-member-email">{member.email}</span>
                              </span>
                            </button>
                          </td>
                          <td>
                            <span className={`ops-users-command-role is-${member.role}`}><i aria-hidden="true" />{t(`opsUsers.roles.${member.role}`)}</span>
                          </td>
                          <td>
                            <div className={`ops-users-command-access${member.isActive ? " is-active" : " is-disabled"}`}>
                              <label className="ops-tts-setup-switch" title={member.isActive ? t("opsUsers.active") : t("opsUsers.disabled")}>
                                <input
                                  type="checkbox"
                                  checked={member.isActive}
                                  disabled={action.isPending(`member-${member.operatorId}`) || isSelf || (member.role === "owner" && (!canManageOwners || activeOwnerCount === 1))}
                                  aria-busy={action.isPending(`member-${member.operatorId}`) || undefined}
                                  aria-label={member.isActive ? t("opsUsers.active") : t("opsUsers.disabled")}
                                  onChange={(event) => void handleStatusToggle(member, event.target.checked)}
                                />
                                <span className="ops-tts-setup-switch__track" aria-hidden="true" />
                              </label>
                              <strong>{member.isActive ? t("opsUsers.active") : t("opsUsers.disabled")}</strong>
                            </div>
                          </td>
                          <td>
                            <div className="ops-users-command-session">
                              <span>
                                <small>{t("opsUsers.lastSignIn")}</small>
                                <span className={`ops-users-registry-signin is-${signInTone}`} title={member.lastSeenAt ? formatDateTime(member.lastSeenAt) : undefined}>
                                  <i aria-hidden="true" />
                                  <strong>{member.lastSeenAt ? formatCompactDate(member.lastSeenAt) : t("opsUsers.neverSignedIn")}</strong>
                                </span>
                              </span>
                              <span title={formatDateTime(member.createdAt)}><small>{t("opsUsers.joined")}</small><strong>{formatCompactDate(member.createdAt)}</strong></span>
                            </div>
                          </td>
                          <td>
                            <div className={`ops-users-command-review is-${primarySignalKind ?? "clear"}`}>
                              <span aria-hidden="true">{primarySignalKind ? <AccessSignalIcon kind={primarySignalKind} /> : <i />}</span>
                              <span>
                                <strong>{primarySignalLabel}</strong>
                                <small>{signalCount > 0 ? t("opsUsers.signalCount").replace("{count}", String(signalCount)) : t("opsUsers.noSignals")}</small>
                              </span>
                            </div>
                          </td>
                          <td className="ops-users-command-row__actions">
                            <button type="button" className="ops-tts-setup-table__icon-btn" disabled={action.isPending(`member-${member.operatorId}`) || (member.role === "owner" && !canManageOwners)} aria-label={t("opsUsers.editMember")} title={t("opsUsers.editMember")} onClick={() => openEditDrawer(member)}><EditMemberIcon /></button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            <div className="ops-users-registry-invites">
              {filteredInvites.length === 0 ? (
                <div className="ops-users-empty">
                  <strong>{invites.length === 0 ? t("opsUsers.noPendingInvites") : t("opsUsers.noInvitesMatch")}</strong>
                  <p>{invites.length === 0 ? t("opsUsers.noPendingInvitesHelp") : t("opsUsers.noInvitesMatchHelp")}</p>
                </div>
              ) : (
                <div className="ops-users-command-table__viewport is-invites">
                  <table className="ops-users-command-table__table ops-users-command-invite-table">
                    <thead>
                      <tr>
                        <th>{t("opsUsers.email")}</th>
                        <th>{t("opsUsers.role")}</th>
                        <th>{t("opsUsers.status")}</th>
                        <th>{t("opsUsers.created")}</th>
                        <th>{t("opsUsers.expires")}</th>
                        <th>{t("opsUsers.actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredInvites.map((invite) => (
                        <tr className={`ops-users-command-invite-row is-${invite.status}`} key={invite.inviteId}>
                          <td>
                            <div className="ops-users-command-invite-identity">
                              <span aria-hidden="true" className={`ops-users-avatar is-${invite.role}`}>{invite.email.slice(0, 1).toUpperCase()}</span>
                              <div>
                                <strong title={invite.email}>{invite.email}</strong>
                                {invite.note ? <span>{invite.note}</span> : null}
                              </div>
                            </div>
                            {rotatedLinkByInviteId[invite.inviteId] ? <div className="ops-users-invite-link is-inline"><p>{t("opsUsers.inviteLinkHelp")}</p><code>{rotatedLinkByInviteId[invite.inviteId]}</code></div> : null}
                          </td>
                          <td><span className={`ops-users-command-role is-${invite.role}`}><i aria-hidden="true" />{t(`opsUsers.roles.${invite.role}`)}</span></td>
                          <td><StatusBadge label={invite.status === "expired" ? t("opsUsers.expired") : t("opsUsers.pending")} tone={invite.status === "expired" ? "warn" : "muted"} /></td>
                          <td><span className="ops-users-registry-date" title={invite.createdAt ? formatDateTime(invite.createdAt) : undefined}>{formatCompactDate(invite.createdAt)}</span></td>
                          <td><span className="ops-users-registry-date" title={formatDateTime(invite.expiresAt)}>{invite.status === "expired" ? t("opsUsers.expired") : formatExpiry(invite.expiresAt)}</span></td>
                          <td>
                            <div className="ops-users-command-invite-actions">
                              <AsyncButton className="ops-users-quiet-btn is-accent" pending={action.isPending(`invite-${invite.inviteId}`)} pendingLabel={t("opsUsers.copyNewLink")} title={t("opsUsers.copyNewLinkHelp")} onClick={() => void handleCopyNewInviteLink(invite.inviteId)}>{t("opsUsers.copyNewLink")}</AsyncButton>
                              <AsyncButton className="ops-users-quiet-btn" pending={action.isPending(`invite-${invite.inviteId}`)} pendingLabel={t("opsUsers.revoke")} onClick={() => void handleRevoke(invite.inviteId)}>{t("opsUsers.revoke")}</AsyncButton>
                            </div>
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
              <div className="ops-users-modal-heading">
                <span className="ops-users-modal-heading__icon"><OpsUsersUiIcon kind="invite" /></span>
                <div>
                  <p className="ops-users-hero-eyebrow">{t("opsUsers.directoryEyebrow")}</p>
                  <h2 id="ops-users-modal-title">{t("opsUsers.inviteMember")}</h2>
                  <p>{t("opsUsers.inviteHelp")}</p>
                </div>
              </div>
              <button className="ops-users-modal-close" type="button" aria-label={t("common.close")} onClick={closeOverlay}>
                <OpsUsersUiIcon kind="close" />
              </button>
            </header>
            <form className="ops-users-invite-form" onSubmit={(event) => void handleInvite(event)}>
              <label>
                <span className="ops-users-form-label"><OpsUsersUiIcon kind="mail" />{t("opsUsers.email")}</span>
                <input
                  required
                  type="email"
                  value={inviteEmail}
                  onChange={(event) => setInviteEmail(event.target.value)}
                />
              </label>
              <label>
                <span className="ops-users-form-label"><OpsUsersUiIcon kind="access" />{t("opsUsers.role")}</span>
                <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}>
                  {assignableRoles.map((role) => (
                    <option key={role} value={role}>
                      {t(`opsUsers.roles.${role}`)}
                    </option>
                  ))}
                </select>
              </label>
              <div className="ops-users-modal-actions">
                <button className="ops-users-overlay-btn is-secondary" type="button" onClick={closeOverlay}>
                  <OpsUsersUiIcon kind="cancel" />
                  {t("common.cancel")}
                </button>
                <AsyncButton
                  className="primary ops-users-overlay-btn"
                  leadingIcon={<OpsUsersUiIcon kind="send" />}
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
                  leadingIcon={<OpsUsersUiIcon kind="copy" />}
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
                <OpsUsersUiIcon kind="close" />
              </button>
            </header>

            <form className="ops-users-drawer-form" onSubmit={(event) => void handleEdit(event)}>
              <div className="ops-users-drawer__body">
                <section className="ops-users-section">
                  <h3><span className="ops-users-section-icon"><OpsUsersUiIcon kind="profile" /></span>{t("opsUsers.profileSection")}</h3>
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
                    <span><OpsUsersUiIcon kind="mail" />{t("opsUsers.email")}</span>
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

                <section className="ops-users-section ops-users-section--access">
                  <h3><span className="ops-users-section-icon"><OpsUsersUiIcon kind="access" /></span>{t("opsUsers.accessSection")}</h3>
                  <label className="ops-users-field">
                    {t("opsUsers.role")}
                    <select
                      value={editRole}
                      disabled={
                        editingMember.role === "owner" &&
                        (!canManageOwners || (editingMember.isActive && activeOwnerCount === 1))
                      }
                      onChange={(event) => setEditRole(event.target.value)}
                    >
                      {(editingMember.role === "owner" && !canManageOwners ? ["owner"] : assignableRoles).map((role) => (
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
                      disabled={
                        editingMember.operatorId === me?.operatorId ||
                        (editingMember.role === "owner" && (!canManageOwners || activeOwnerCount === 1))
                      }
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
                      <h3><span className="ops-users-section-icon"><OpsUsersUiIcon kind="security" /></span>{t("opsUsers.securitySection")}</h3>
                      <p>{t("opsUsers.resetPasswordHelp")}</p>
                    </div>
                    <AsyncButton
                      className="ops-users-quiet-btn"
                      leadingIcon={<OpsUsersUiIcon kind="security" />}
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
                        leadingIcon={<OpsUsersUiIcon kind="copy" />}
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
                <button className="ops-users-overlay-btn is-secondary" type="button" onClick={closeOverlay}>
                  <OpsUsersUiIcon kind="cancel" />
                  {t("common.cancel")}
                </button>
                <AsyncButton
                  className="primary ops-users-overlay-btn"
                  leadingIcon={<OpsUsersUiIcon kind="save" />}
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
