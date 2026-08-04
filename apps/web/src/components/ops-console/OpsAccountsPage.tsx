"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  checkFacebookAccountSetup,
  completeFacebookOAuthCallback,
  connectFacebookOAuthPage,
  createPlatformAccount,
  fetchAllPlatformAccounts,
  fetchFacebookOAuthConfiguration,
  fetchFacebookOAuthSession,
  fetchFacebookPublishSafetyStatus,
  fetchPublishControlQueue,
  startFacebookOAuth,
  updateFacebookOAuthConfiguration,
  updatePlatformAccount,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type {
  FacebookAccountSetupCheckResponse,
  FacebookOAuthConfiguration,
  FacebookOAuthSession,
  FacebookPublishSafetyStatus,
  PlatformAccount,
  PlatformAccountStatus,
} from "../../types/publish-draft";
import type { AccountHealthSummary, PublishControlQueue } from "../../types/publish-control";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone, type OpsTone } from "./OpsShared";

type AccountRow = PlatformAccount & {
  healthStatus: string | null;
  healthSummary: AccountHealthSummary | null;
  needsAttention: boolean;
  safetyStatus: FacebookPublishSafetyStatus | null;
};

type AccountSetupTab = "account" | "safety";
type AccountSetupMethod = "oauth" | "manual";
type ReadinessLaneKey = "attention" | "ready" | "standby";
type OAuthPageState = "NEW" | "CONNECTED" | "RECONNECT_REQUIRED" | "MISSING_PERMISSIONS" | "NEEDS_ATTENTION" | "ARCHIVED" | "STATUS_UNAVAILABLE";

type SetupForm = {
  displayName: string;
  pageId: string;
  tokenReference: string;
  graphApiVersion: string;
  status: PlatformAccountStatus;
  priority: string;
  isOnHold: boolean;
  holdReason: string;
  cooldownUntil: string;
  allowedNiches: string;
  routingNotes: string;
  notes: string;
};

type MetaConfigurationForm = {
  appId: string;
  appSecret: string;
  redirectUri: string;
  graphApiVersion: string;
  requestedScopes: string[];
};

const META_SCOPE_OPTIONS = [
  "pages_show_list",
  "pages_read_engagement",
  "read_insights",
  "pages_manage_posts",
] as const;

const EMPTY_META_CONFIGURATION_FORM: MetaConfigurationForm = {
  appId: "",
  appSecret: "",
  redirectUri: "http://localhost:3000/publishing/accounts",
  graphApiVersion: "v20.0",
  requestedScopes: [...META_SCOPE_OPTIONS],
};

const EMPTY_SETUP_FORM: SetupForm = {
  displayName: "",
  pageId: "",
  tokenReference: "FACEBOOK_PAGE_ACCESS_TOKEN",
  graphApiVersion: "v20.0",
  status: "ACTIVE",
  priority: "100",
  isOnHold: false,
  holdReason: "",
  cooldownUntil: "",
  allowedNiches: "",
  routingNotes: "",
  notes: "",
};

function formatChipLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function accountAvatarLabel(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "FB";
  return parts.slice(0, 2).map((part) => part.charAt(0)).join("").toUpperCase();
}

function accountAvatarUrl(account: PlatformAccount): string | null {
  const value = account.metadata_json?.facebook_page_picture_url;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function toDateTimeLocal(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function isSystemSafetyHold(reason: string | null | undefined): boolean {
  return Boolean(reason?.startsWith("FACEBOOK_SAFETY_HOLD:") || reason?.startsWith("FACEBOOK_OAUTH_CAPABILITY_MISSING:"));
}

function isPublishableOAuthPage(session: FacebookOAuthSession, page: FacebookOAuthSession["pages"][number]): boolean {
  return session.granted_scopes.includes("pages_manage_posts") && page.tasks.map((item) => item.toUpperCase()).includes("CREATE_CONTENT");
}

function publicationLibraryHref(accountId?: string | null): string {
  return accountId
    ? `/publishing/publications?account_id=${encodeURIComponent(accountId)}`
    : "/publishing/publications";
}

type AccountIconKind = "capacity" | "queue" | "success" | "hold" | "attention" | "library" | "drafts" | "setup" | "settings" | "facebook" | "clock" | "shield" | "close" | "save" | "check" | "reconnect" | "add" | "chevron";

function AccountIcon({ kind, className = "ops-accounts-icon" }: { kind: AccountIconKind; className?: string }) {
  const common = { className, fill: "none", viewBox: "0 0 24 24", "aria-hidden": true } as const;
  if (kind === "capacity") return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.2 2M8 4.8 6.2 3.2M16 4.8l1.8-1.6" /></svg>;
  if (kind === "queue") return <svg {...common}><rect height="4" rx="1.5" width="13" x="5.5" y="5" /><rect height="4" rx="1.5" width="13" x="5.5" y="10" /><rect height="4" rx="1.5" width="9" x="5.5" y="15" /></svg>;
  if (kind === "success") return <svg {...common}><path d="m5 13 3.2 3.2L19 6.8" /><path d="M4.5 19.5h15" /></svg>;
  if (kind === "hold") return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M9.3 9.2v5.6M14.7 9.2v5.6" /></svg>;
  if (kind === "attention") return <svg {...common}><path d="M12 4 21 19H3L12 4Z" /><path d="M12 9.5v4M12 16.4v.1" /></svg>;
  if (kind === "library") return <svg {...common}><path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21V5.5Z" /><path d="M5 5.5V19M9 7h6M9 10h6" /></svg>;
  if (kind === "drafts") return <svg {...common}><path d="M7 3.5h7l4 4V20.5H7z" /><path d="M14 3.5v4h4M9.5 12h5M9.5 15h5" /></svg>;
  if (kind === "setup") return <svg {...common}><path d="M5 6h14M5 12h14M5 18h14" /><circle cx="9" cy="6" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="11" cy="18" r="2" /></svg>;
  if (kind === "settings") return <svg {...common}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></svg>;
  if (kind === "facebook") return <svg {...common}><path d="M13.4 21v-7h2.4l.4-2.8h-2.8V9.4c0-.8.3-1.4 1.5-1.4h1.5V5.5c-.3 0-1.2-.1-2.3-.1-2.3 0-3.9 1.4-3.9 4V11H7.7V14h2.5v7" /></svg>;
  if (kind === "clock") return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>;
  if (kind === "shield") return <svg {...common}><path d="m12 3.5 7 2.6v5.2c0 4.2-2.6 7.4-7 9.2-4.4-1.8-7-5-7-9.2V6.1L12 3.5Z" /><path d="m9 12 2 2 4-4" /></svg>;
  if (kind === "close") return <svg {...common}><path d="m6.5 6.5 11 11m0-11-11 11" /></svg>;
  if (kind === "save") return <svg {...common}><path d="M5 4h12l2 2v14H5z" /><path d="M8 4v5h7V4M8 20v-6h8v6" /></svg>;
  if (kind === "check") return <svg {...common}><path d="m5 12.5 4.2 4.2L19 7" /></svg>;
  if (kind === "reconnect") return <svg {...common}><path d="M19 8.5A7.5 7.5 0 1 0 19.4 15M19 4v4.5h-4.5" /></svg>;
  if (kind === "chevron") return <svg {...common}><path d="m7.5 9.5 4.5 4.5 4.5-4.5" /></svg>;
  return <svg {...common}><path d="M12 5v14M5 12h14" /></svg>;
}

function AccountsChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ops-accounts-chip tone-${tone}`}>{formatChipLabel(label)}</span>;
}

function safetyTone(status: FacebookPublishSafetyStatus | null): OpsTone {
  if (!status) return "muted";
  if (status.eligible_for_publish) return status.state === "WARM_UP" ? "warn" : "good";
  if (["COOLDOWN", "CADENCE_WAIT"].includes(status.state)) return "warn";
  return "danger";
}

function CheckList({
  checks,
  ready,
  readyLabel,
  blockedLabel,
  blockingGroupLabel,
  warningGroupLabel,
  passedGroupLabel,
}: {
  checks: Array<{ code: string; passed: boolean; blocking: boolean; message: string }>;
  ready: boolean;
  readyLabel: string;
  blockedLabel: string;
  blockingGroupLabel: string;
  warningGroupLabel: string;
  passedGroupLabel: string;
}) {
  const blocking = checks.filter((item) => !item.passed && item.blocking);
  const warnings = checks.filter((item) => !item.passed && !item.blocking);
  const passed = checks.filter((item) => item.passed);
  const renderItems = (items: typeof checks, tone: "block" | "warn" | "pass") => (
    <ul>
      {items.map((item) => (
        <li className={`is-${tone}`} key={item.code}>
          <span aria-hidden="true">{tone === "pass" ? "✓" : tone === "warn" ? "i" : "!"}</span>
          <div><b>{formatChipLabel(item.code)}</b><small>{item.message}</small></div>
        </li>
      ))}
    </ul>
  );
  return (
    <div className={`ops-accounts-checks${ready ? " is-ready" : " is-blocked"}`}>
      <strong>{ready ? readyLabel : blockedLabel}</strong>
      {blocking.length > 0 ? <section><em>{blockingGroupLabel.replace("{count}", String(blocking.length))}</em>{renderItems(blocking, "block")}</section> : null}
      {warnings.length > 0 ? <section><em>{warningGroupLabel.replace("{count}", String(warnings.length))}</em>{renderItems(warnings, "warn")}</section> : null}
      {passed.length > 0 ? <details><summary>{passedGroupLabel.replace("{count}", String(passed.length))}</summary>{renderItems(passed, "pass")}</details> : null}
    </div>
  );
}

export function OpsAccountsPage() {
  const t = useT();
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [safetyStatuses, setSafetyStatuses] = useState<Record<string, FacebookPublishSafetyStatus>>({});
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [editingAccountId, setEditingAccountId] = useState<string | null>(null);
  const [setupForm, setSetupForm] = useState<SetupForm>(EMPTY_SETUP_FORM);
  const [activeAccount, setActiveAccount] = useState<PlatformAccount | null>(null);
  const [accountCheck, setAccountCheck] = useState<FacebookAccountSetupCheckResponse | null>(null);
  const [oauthConfiguration, setOauthConfiguration] = useState<FacebookOAuthConfiguration | null>(null);
  const [metaConfigurationForm, setMetaConfigurationForm] = useState<MetaConfigurationForm>(EMPTY_META_CONFIGURATION_FORM);
  const [oauthSession, setOauthSession] = useState<FacebookOAuthSession | null>(null);
  const [oauthCatalogPages, setOauthCatalogPages] = useState<FacebookOAuthSession["pages"]>([]);
  const [oauthSessionConnectedPageIds, setOauthSessionConnectedPageIds] = useState<string[]>([]);
  const [selectedOAuthPageIds, setSelectedOAuthPageIds] = useState<string[]>([]);
  const [oauthDefaultPriority, setOauthDefaultPriority] = useState("100");
  const [activeTab, setActiveTab] = useState<AccountSetupTab>("account");
  const [setupMethod, setSetupMethod] = useState<AccountSetupMethod>("oauth");
  const [oauthConfigurationError, setOauthConfigurationError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [collapsedLanes, setCollapsedLanes] = useState<Set<ReadinessLaneKey>>(() => new Set());
  const oauthCallbackStarted = useRef(false);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load(mode: "initial" | "refresh" = loadedAt ? "refresh" : "initial") {
    try {
      await request.run(async () => {
        const [accountPayload, queuePayload] = await Promise.all([
          fetchAllPlatformAccounts(),
          fetchPublishControlQueue(),
        ]);
        const statusEntries = await Promise.all(accountPayload.map(async (account) => {
          try {
            return [account.id, await fetchFacebookPublishSafetyStatus(account.id)] as const;
          } catch {
            return null;
          }
        }));
        return { accountPayload, queuePayload, statusEntries };
      }, ({ accountPayload, queuePayload, statusEntries }) => {
        setAccounts(accountPayload);
        setQueue(queuePayload);
        setSafetyStatuses(Object.fromEntries(statusEntries.filter((entry): entry is readonly [string, FacebookPublishSafetyStatus] => Boolean(entry))));
        setLoadedAt(new Date().toISOString());
        setActiveAccount((current) => current ? accountPayload.find((item) => item.id === current.id) ?? current : null);
      }, mode);
      if (mode === "refresh") notify({ id: "ops-accounts-refresh", message: t("opsAccounts.refreshSuccess"), tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "ops-accounts-refresh", message: err instanceof Error ? err.message : t("opsAccounts.unavailableTitle"), tone: "error" });
    }
  }

  useEffect(() => {
    void load("initial");
  }, [t]);

  useEffect(() => {
    void fetchFacebookOAuthConfiguration()
      .then((configuration) => {
        setOauthConfiguration(configuration);
        setMetaConfigurationForm({
          appId: configuration.app_id ?? "",
          appSecret: "",
          redirectUri: configuration.redirect_uri,
          graphApiVersion: configuration.graph_api_version,
          requestedScopes: configuration.requested_scopes.length > 0
            ? Array.from(new Set([...configuration.requested_scopes, "pages_show_list", "pages_manage_posts"]))
            : [...META_SCOPE_OPTIONS],
        });
        setOauthConfigurationError(null);
      })
      .catch((error) => {
        setOauthConfigurationError(error instanceof Error ? error.message : t("opsAccounts.oauthConfigError"));
      });
  }, [t]);

  useEffect(() => {
    if (typeof window === "undefined" || oauthCallbackStarted.current) return;
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    const providerError = params.get("error_description") || params.get("error");
    if (!code && !state && !providerError) return;
    oauthCallbackStarted.current = true;
    setSetupOpen(true);
    if (providerError) {
      setSetupError(t("opsAccounts.oauthDenied"));
      window.history.replaceState({}, document.title, window.location.pathname);
      return;
    }
    if (!code || !state) {
      setSetupError(t("opsAccounts.oauthCallbackInvalid"));
      window.history.replaceState({}, document.title, window.location.pathname);
      return;
    }
    setBusyAction("oauth-callback");
    void (async () => {
      try {
        const session = await completeFacebookOAuthCallback(code, state);
        setOauthSession(session);
        setOauthCatalogPages(session.pages);
        setOauthSessionConnectedPageIds([]);
        setSelectedOAuthPageIds([]);
      } catch (error) {
        setSetupError(error instanceof Error ? error.message : t("opsAccounts.oauthCallbackError"));
      } finally {
        window.history.replaceState({}, document.title, window.location.pathname);
        setBusyAction(null);
      }
    })();
  }, [t]);

  const healthById = useMemo(() => {
    const health = new Map<string, AccountHealthSummary>();
    for (const item of queue?.accounts ?? []) {
      health.set(item.platform_account_id, item);
    }
    return health;
  }, [queue]);

  const rows = useMemo<AccountRow[]>(
    () => accounts.map((account) => {
      const healthSummary = healthById.get(account.id) ?? null;
      const healthStatus = healthSummary?.health_status ?? null;
      const safetyStatus = safetyStatuses[account.id] ?? null;
      const needsAttention = account.status !== "ACTIVE"
        || account.is_on_hold
        || Boolean(account.cooldown_until && new Date(account.cooldown_until).getTime() > Date.now())
        || ["DEGRADED", "UNHEALTHY", "HELD"].includes(healthStatus ?? "")
        || Boolean(safetyStatus && !safetyStatus.eligible_for_publish);
      return { ...account, healthStatus, healthSummary, safetyStatus, needsAttention };
    }).sort((a, b) => a.needsAttention !== b.needsAttention ? (a.needsAttention ? -1 : 1) : a.display_name.localeCompare(b.display_name)),
    [accounts, healthById, safetyStatuses],
  );

  const accountByExternalId = useMemo(
    () => new Map(accounts.map((account) => [account.external_account_id, account])),
    [accounts],
  );

  function oauthPageState(session: FacebookOAuthSession, page: FacebookOAuthSession["pages"][number]): OAuthPageState {
    if (!isPublishableOAuthPage(session, page)) return "MISSING_PERMISSIONS";
    if (oauthSessionConnectedPageIds.includes(page.page_id)) return "CONNECTED";
    const account = accountByExternalId.get(page.page_id);
    if (!account) return "NEW";
    if (account.status === "ARCHIVED") return "ARCHIVED";
    const safety = safetyStatuses[account.id];
    if (account.token_reference == null) return "RECONNECT_REQUIRED";
    if (!safety) return "STATUS_UNAVAILABLE";
    if (safety.state === "RECONNECT_REQUIRED") return "RECONNECT_REQUIRED";
    if (account.is_on_hold || account.status !== "ACTIVE" || ["HOLD", "BLOCKED", "COOLDOWN", "CADENCE_WAIT"].includes(safety?.state ?? "")) return "NEEDS_ATTENTION";
    return "CONNECTED";
  }

  function canSelectOAuthPage(session: FacebookOAuthSession, page: FacebookOAuthSession["pages"][number]): boolean {
    const state = oauthPageState(session, page);
    return state === "NEW" || state === "RECONNECT_REQUIRED";
  }

  function oauthPageStateLabel(state: OAuthPageState): string {
    if (state === "NEW") return t("opsAccounts.pageStateNew");
    if (state === "CONNECTED") return t("opsAccounts.pageStateConnected");
    if (state === "RECONNECT_REQUIRED") return t("opsAccounts.pageStateReconnect");
    if (state === "MISSING_PERMISSIONS") return t("opsAccounts.pageStatePermissions");
    if (state === "ARCHIVED") return t("opsAccounts.pageStateArchived");
    if (state === "STATUS_UNAVAILABLE") return t("opsAccounts.pageStateUnavailable");
    return t("opsAccounts.pageStateAttention");
  }

  const attentionRows = rows.filter((row) => row.needsAttention);
  const readyRows = rows.filter((row) => !row.needsAttention && row.safetyStatus?.eligible_for_publish === true);
  const standbyRows = rows.filter((row) => !row.needsAttention && row.safetyStatus?.eligible_for_publish !== true);
  const attempts7d = queue?.accounts.reduce((sum, item) => sum + item.attempts_7d, 0) ?? 0;
  const succeeded7d = queue?.accounts.reduce((sum, item) => sum + item.succeeded_7d, 0) ?? 0;
  const successRate7d = attempts7d > 0 ? Math.round((succeeded7d / attempts7d) * 100) : null;
  const queueWorkload = (queue?.assigned_total ?? queue?.assigned_drafts.length ?? 0)
    + (queue?.scheduled_total ?? queue?.scheduled_drafts.length ?? 0);
  const readinessLanes: Array<{ key: ReadinessLaneKey; label: string; hint: string; icon: AccountIconKind; items: AccountRow[] }> = [
    { key: "attention", label: t("opsAccounts.laneAttention"), hint: t("opsAccounts.laneAttentionHint"), icon: "attention", items: attentionRows },
    { key: "ready", label: t("opsAccounts.laneReady"), hint: t("opsAccounts.laneReadyHint"), icon: "check", items: readyRows },
    { key: "standby", label: t("opsAccounts.laneStandby"), hint: t("opsAccounts.laneStandbyHint"), icon: "clock", items: standbyRows },
  ];
  const activeSafety = activeAccount ? safetyStatuses[activeAccount.id] ?? null : null;
  const managedAccount = Boolean(activeSafety?.managed_credential || activeAccount?.metadata_json?.credential_source === "META_OAUTH");
  const systemSafetyHold = isSystemSafetyHold(activeAccount?.hold_reason);
  const selectedOAuthPages = oauthCatalogPages.filter((page) => selectedOAuthPageIds.includes(page.page_id));
  const selectedNewPageCount = oauthSession ? selectedOAuthPages.filter((page) => oauthPageState(oauthSession, page) === "NEW").length : 0;
  const selectedReconnectPageCount = oauthSession ? selectedOAuthPages.filter((page) => oauthPageState(oauthSession, page) === "RECONNECT_REQUIRED").length : 0;

  function toggleReadinessLane(key: ReadinessLaneKey) {
    setCollapsedLanes((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function openCreate() {
    setSetupOpen(true);
    setEditingAccountId(null);
    setActiveAccount(null);
    setSetupForm(EMPTY_SETUP_FORM);
    setAccountCheck(null);
    setOauthSession(null);
    setOauthCatalogPages([]);
    setOauthSessionConnectedPageIds([]);
    setSelectedOAuthPageIds([]);
    setOauthDefaultPriority("100");
    setActiveTab("account");
    setSetupMethod("oauth");
    setSetupError(null);
  }

  function applyAccountToForm(account: PlatformAccount) {
    const metadata = account.metadata_json ?? {};
    setSetupOpen(true);
    setEditingAccountId(account.id);
    setActiveAccount(account);
    setSetupForm({
      displayName: account.display_name,
      pageId: account.external_account_id,
      tokenReference: account.token_reference?.toLowerCase().startsWith("env:") ? account.token_reference.slice(4) : account.token_reference ?? "FACEBOOK_PAGE_ACCESS_TOKEN",
      graphApiVersion: String(metadata.graph_api_version ?? "v20.0"),
      status: account.status,
      priority: String(account.priority),
      isOnHold: account.is_on_hold,
      holdReason: account.hold_reason ?? "",
      cooldownUntil: toDateTimeLocal(account.cooldown_until),
      allowedNiches: Array.isArray(account.allowed_niches_json) ? account.allowed_niches_json.map(String).join(", ") : "",
      routingNotes: account.routing_notes ?? "",
      notes: account.notes ?? "",
    });
  }

  function openEdit(account: PlatformAccount) {
    setSetupOpen(true);
    applyAccountToForm(account);
    setAccountCheck(null);
    setOauthSession(null);
    setOauthCatalogPages([]);
    setOauthSessionConnectedPageIds([]);
    setSelectedOAuthPageIds([]);
    setActiveTab("account");
    setSetupMethod(account.metadata_json?.credential_source === "META_OAUTH" ? "oauth" : "manual");
    setSetupError(null);
  }

  async function beginFacebookOAuth() {
    if (!oauthConfiguration?.configured) return;
    setBusyAction("oauth-start");
    setSetupError(null);
    try {
      const started = await startFacebookOAuth();
      window.location.assign(started.authorization_url);
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : t("opsAccounts.oauthStartError"));
      setBusyAction(null);
    }
  }

  async function saveMetaConfiguration() {
    const initialSecretRequired = oauthConfiguration?.source !== "DATABASE";
    if (!/^\d+$/.test(metaConfigurationForm.appId.trim())) {
      setSetupError(t("opsAccounts.metaAppIdInvalid"));
      return;
    }
    if (initialSecretRequired && !metaConfigurationForm.appSecret.trim()) {
      setSetupError(t("opsAccounts.metaAppSecretRequired"));
      return;
    }
    setBusyAction("save-meta-config");
    setSetupError(null);
    try {
      const configuration = await updateFacebookOAuthConfiguration({
        app_id: metaConfigurationForm.appId.trim(),
        app_secret: metaConfigurationForm.appSecret.trim() || null,
        redirect_uri: metaConfigurationForm.redirectUri.trim(),
        graph_api_version: metaConfigurationForm.graphApiVersion.trim(),
        requested_scopes: metaConfigurationForm.requestedScopes,
      });
      setOauthConfiguration(configuration);
      setMetaConfigurationForm((current) => ({ ...current, appSecret: "" }));
      notify({ message: t("opsAccounts.metaConfigurationSaved"), tone: "success" });
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : t("opsAccounts.metaConfigurationSaveError"));
    } finally {
      setBusyAction(null);
    }
  }

  function toggleMetaScope(scope: string) {
    setMetaConfigurationForm((current) => ({
      ...current,
      requestedScopes: current.requestedScopes.includes(scope)
        ? current.requestedScopes.filter((item) => item !== scope)
        : [...current.requestedScopes, scope],
    }));
  }

  function toggleOAuthPage(pageId: string) {
    setSelectedOAuthPageIds((current) => current.includes(pageId)
      ? current.filter((item) => item !== pageId)
      : [...current, pageId]);
  }

  async function connectSelectedPages(session: FacebookOAuthSession) {
    const selectedPages = session.pages.filter((page) => selectedOAuthPageIds.includes(page.page_id) && canSelectOAuthPage(session, page));
    if (selectedPages.length === 0) {
      setSetupError(t("opsAccounts.selectAtLeastOnePage"));
      return;
    }
    setBusyAction("oauth-pages");
    setSetupError(null);
    let connectedCount = 0;
    try {
      const priority = Math.max(0, Math.min(1000, Number(oauthDefaultPriority) || 100));
      for (const page of selectedPages) {
        await connectFacebookOAuthPage(session.connection_id, page.page_id, priority);
        connectedCount += 1;
        setOauthSessionConnectedPageIds((current) => current.includes(page.page_id) ? current : [...current, page.page_id]);
      }
      const refreshedSession = await fetchFacebookOAuthSession(session.connection_id);
      setOauthSession(refreshedSession);
      setSelectedOAuthPageIds([]);
      await load("refresh");
      if (refreshedSession.status === "COMPLETED") setSetupOpen(false);
      notify({ message: t("opsAccounts.oauthPagesConnected").replace("{count}", String(selectedPages.length)), tone: "success" });
    } catch (error) {
      try {
        const refreshedSession = await fetchFacebookOAuthSession(session.connection_id);
        setOauthSession(refreshedSession);
        setSelectedOAuthPageIds([]);
        if (connectedCount > 0) await load("refresh");
      } catch {
        // Preserve the original boundary error when session refresh also fails.
      }
      setSetupError(error instanceof Error ? error.message : t("opsAccounts.oauthPageError"));
      if (connectedCount > 0) notify({ message: t("opsAccounts.oauthPagesPartial").replace("{count}", String(connectedCount)), tone: "warning" });
    } finally {
      setBusyAction(null);
    }
  }

  async function saveAccount(nextTab: AccountSetupTab = "safety") {
    if (!setupForm.displayName.trim() || !setupForm.pageId.trim() || !setupForm.tokenReference.trim()) {
      setSetupError(t("opsAccounts.requiredSetupFields"));
      return;
    }
    setBusyAction("save-account");
    setSetupError(null);
    try {
      const existingMetadata = activeAccount?.metadata_json ?? {};
      const payload = {
        platform: "FACEBOOK_REELS",
        display_name: setupForm.displayName.trim(),
        external_account_id: setupForm.pageId.trim(),
        token_reference: setupForm.tokenReference.trim(),
        status: setupForm.status,
        priority: Math.max(0, Math.min(1000, Number(setupForm.priority) || 100)),
        is_on_hold: setupForm.isOnHold,
        hold_reason: setupForm.holdReason.trim() || null,
        cooldown_until: activeSafety?.cooldown_until && new Date(activeSafety.cooldown_until).getTime() > Date.now()
          ? activeSafety.cooldown_until
          : setupForm.cooldownUntil ? new Date(setupForm.cooldownUntil).toISOString() : null,
        allowed_niches_json: setupForm.allowedNiches.split(",").map((item) => item.trim()).filter(Boolean),
        routing_notes: setupForm.routingNotes.trim() || null,
        notes: setupForm.notes.trim() || null,
        metadata_json: {
          ...existingMetadata,
          graph_api_version: setupForm.graphApiVersion.trim(),
        },
      };
      const saved = editingAccountId
        ? await updatePlatformAccount(editingAccountId, payload)
        : await createPlatformAccount(payload);
      setEditingAccountId(saved.id);
      setActiveAccount(saved);
      const [check, safety] = await Promise.all([
        checkFacebookAccountSetup(saved.id),
        fetchFacebookPublishSafetyStatus(saved.id),
      ]);
      setAccountCheck(check);
      setSafetyStatuses((current) => ({ ...current, [saved.id]: safety }));
      setActiveTab(nextTab);
      await load("refresh");
      notify({ message: t("opsAccounts.accountSaved"), tone: "success" });
    } catch (err) {
      setSetupError(err instanceof Error ? err.message : t("opsAccounts.accountSaveError"));
    } finally {
      setBusyAction(null);
    }
  }

  async function runAccountCheck() {
    if (!activeAccount) return;
    setBusyAction("account-check");
    setSetupError(null);
    try {
      const [check, safety] = await Promise.all([
        checkFacebookAccountSetup(activeAccount.id),
        fetchFacebookPublishSafetyStatus(activeAccount.id),
      ]);
      setAccountCheck(check);
      setSafetyStatuses((current) => ({ ...current, [activeAccount.id]: safety }));
    } catch (err) {
      setSetupError(err instanceof Error ? err.message : t("opsAccounts.accountCheckError"));
    } finally {
      setBusyAction(null);
    }
  }

  const refreshAction = (
    <div className="ops-accounts-top-actions">
      <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load("refresh")} />
    </div>
  );

  if (!loadedAt && !request.error) {
    return <OperatorStudioShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}><AsyncContentBoundary skeletonVariant="table" loadingLabel={t("opsAccounts.loadingDetail")} status="loading"><span /></AsyncContentBoundary></OperatorStudioShell>;
  }

  if (request.error && !loadedAt) {
    return <OperatorStudioShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}><AsyncContentBoundary errorState={<OpsState title={t("opsAccounts.unavailableTitle")} detail={request.error.message} retry={() => void load("initial")} />} skeletonVariant="table" status="error"><span /></AsyncContentBoundary></OperatorStudioShell>;
  }

  const manualMissingFields = [setupForm.displayName, setupForm.pageId, setupForm.tokenReference].filter((value) => !value.trim()).length;
  const activeAccountAvatarUrl = activeAccount ? accountAvatarUrl(activeAccount) : null;
  const safetyStages = ["PILOT", "OBSERVE", "STANDARD"] as const;
  const activeSafetyStageIndex = activeSafety ? Math.max(0, safetyStages.indexOf(activeSafety.warmup_stage)) : 0;

  return (
    <OperatorStudioShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="table" status="success">
        <main className="ops-page ops-accounts-page">
          <section className="ops-accounts-spectrum" aria-label={t("opsAccounts.title")}>
            <div className="ops-accounts-spectrum__intro"><span><AccountIcon kind="shield" />{t("opsAccounts.readinessBoard")}</span><strong>{accounts.length} <small>{t("opsAccounts.platformAccounts")}</small></strong><p><AccountIcon kind="clock" /><span className="visually-hidden">{t("opsAccounts.loadedAt")}</span><time dateTime={loadedAt ?? undefined}>{formatDateTime(loadedAt)}</time></p></div>
            <div className="ops-accounts-spectrum__segments"><div className="is-attention"><span><AccountIcon kind="attention" /></span><strong>{attentionRows.length}</strong><small>{t("opsAccounts.laneAttention")}</small></div><div className="is-ready"><span><AccountIcon kind="check" /></span><strong>{readyRows.length}</strong><small>{t("opsAccounts.laneReady")}</small></div><div className="is-standby"><span><AccountIcon kind="clock" /></span><strong>{standbyRows.length}</strong><small>{t("opsAccounts.laneStandby")}</small></div></div>
            <div className="ops-accounts-spectrum__insights"><div><span><AccountIcon kind="success" />{t("opsAccounts.success7d")}</span><strong>{successRate7d == null ? "—" : `${successRate7d}%`}</strong><small>{t("opsAccounts.success7dDetail").replace("{success}", String(succeeded7d)).replace("{attempts}", String(attempts7d))}</small></div><div><span><AccountIcon kind="queue" />{t("opsAccounts.queueWorkload")}</span><strong>{queueWorkload}</strong><small>{t("opsAccounts.assignedScheduledWork")}</small></div></div>
          </section>

          {setupOpen ? (
            <section className="ops-accounts-setup" aria-label={t("opsAccounts.setupTitle")}>
              <aside className="ops-accounts-setup__rail">
              <div className="ops-accounts-setup__head">
                <div><span>{t("opsAccounts.setupEyebrow")}</span><h2>{editingAccountId ? t("opsAccounts.editPage") : t("opsAccounts.addFacebookPage")}</h2></div>
                <button onClick={() => setSetupOpen(false)} type="button"><AccountIcon kind="close" />{t("common.close")}</button>
              </div>
              <nav className="ops-accounts-tabs" aria-label={t("opsAccounts.setupSteps")} role="tablist">
                {([
                  ["account", t("opsAccounts.stepAccount"), false],
                  ["safety", t("opsAccounts.stepSafety"), !activeAccount],
                ] as Array<[AccountSetupTab, string, boolean]>).map(([tab, label, disabled], index) => (
                  <button aria-selected={activeTab === tab} className={activeTab === tab ? "is-current" : ""} disabled={disabled} key={tab} onClick={() => setActiveTab(tab)} role="tab" type="button"><b>{index + 1}</b><span>{label}</span></button>
                ))}
              </nav>
              </aside>

              <div className="ops-accounts-setup__workspace">

              {activeTab === "account" ? <div className="ops-accounts-method-switch" aria-label={t("opsAccounts.setupMethod")} role="tablist"><button aria-selected={setupMethod === "oauth"} className={setupMethod === "oauth" ? "is-current" : ""} onClick={() => setSetupMethod("oauth")} role="tab" type="button"><b>{t("opsAccounts.oauthTitle")}</b><small>{t("opsAccounts.oauthDescription")}</small></button><button aria-selected={setupMethod === "manual"} className={setupMethod === "manual" ? "is-current" : ""} onClick={() => setSetupMethod("manual")} role="tab" type="button"><b>{t("opsAccounts.manualFallbackTitle")}</b><small>{t("opsAccounts.manualFallbackHint")}</small></button></div> : null}

              {setupError ? <div className="inline-error" role="alert">{setupError}</div> : null}

              {activeTab === "account" ? <>
                {setupMethod === "oauth" ? <>
                <section className={`ops-accounts-oauth${oauthConfiguration?.configured ? " is-ready" : " is-missing"}`}>
                  <div className="ops-accounts-oauth__head">
                    <div><span>{t("opsAccounts.oauthEyebrow")}</span><b>{t("opsAccounts.oauthTitle")}</b><small>{t("opsAccounts.oauthDescription")}</small></div>
                    {oauthConfiguration?.configured ? <AccountsChip label={t("opsAccounts.oauthReady")} tone="good" /> : <AccountsChip label={t("opsAccounts.oauthSetupRequired")} tone="warn" />}
                  </div>
                  {!oauthConfiguration && !oauthConfigurationError ? <p className="muted">{t("opsAccounts.oauthConfigLoading")}</p> : null}
                  {oauthConfigurationError ? <p className="inline-error">{oauthConfigurationError}</p> : null}
                  {oauthConfiguration ? <details className="ops-accounts-meta-config" open={!oauthConfiguration.configured}>
                    <summary><span><b>{t("opsAccounts.metaConfiguration")}</b><small>{oauthConfiguration.source === "DATABASE" ? t("opsAccounts.metaConfigurationDatabase") : t("opsAccounts.metaConfigurationHint")}</small></span><AccountsChip label={oauthConfiguration.app_secret_configured ? t("opsAccounts.secretStored") : t("opsAccounts.secretMissing")} tone={oauthConfiguration.app_secret_configured ? "good" : "warn"} /><span aria-hidden="true" className="ops-accounts-disclosure-toggle"><AccountIcon kind="chevron" /></span></summary>
                    <div className="ops-accounts-meta-config__body">
                      <div className="ops-accounts-form-grid">
                        <label className="is-app-id"><span className="ops-accounts-field-label">{t("opsAccounts.metaAppId")}</span><input autoComplete="off" inputMode="numeric" value={metaConfigurationForm.appId} onChange={(event) => setMetaConfigurationForm((current) => ({ ...current, appId: event.target.value }))} /></label>
                        <label className="is-app-secret"><span className="ops-accounts-field-label">{t("opsAccounts.metaAppSecret")}</span><input autoComplete="new-password" placeholder={oauthConfiguration.app_secret_configured ? t("opsAccounts.secretPreservePlaceholder") : t("opsAccounts.secretRequiredPlaceholder")} type="password" value={metaConfigurationForm.appSecret} onChange={(event) => setMetaConfigurationForm((current) => ({ ...current, appSecret: event.target.value }))} /><small>{t("opsAccounts.metaAppSecretHint")}</small></label>
                        <label className="is-redirect"><span className="ops-accounts-field-label">{t("opsAccounts.redirectUri")}</span><input autoComplete="off" value={metaConfigurationForm.redirectUri} onChange={(event) => setMetaConfigurationForm((current) => ({ ...current, redirectUri: event.target.value }))} /><small>{t("opsAccounts.redirectUriHint")}</small></label>
                        <label className="is-version"><span className="ops-accounts-field-label">{t("opsAccounts.graphVersion")}</span><input autoComplete="off" placeholder="v20.0" value={metaConfigurationForm.graphApiVersion} onChange={(event) => setMetaConfigurationForm((current) => ({ ...current, graphApiVersion: event.target.value }))} /></label>
                      </div>
                      {oauthConfiguration.missing_configuration.length > 0 ? <div className="ops-accounts-oauth-missing"><span>{t("opsAccounts.oauthMissing")}</span>{oauthConfiguration.missing_configuration.map((item) => <code key={item}>{item}</code>)}</div> : null}
                      <div className="ops-accounts-meta-config__footer"><fieldset className="ops-accounts-meta-scopes"><legend>{t("opsAccounts.requestedPermissions")}</legend>{META_SCOPE_OPTIONS.map((scope) => { const required = scope === "pages_show_list" || scope === "pages_manage_posts"; return <label key={scope}><input checked={metaConfigurationForm.requestedScopes.includes(scope)} disabled={required} onChange={() => toggleMetaScope(scope)} type="checkbox" /><span>{scope}{required ? ` · ${t("opsAccounts.required")}` : ""}</span></label>; })}</fieldset><div className="ops-accounts-meta-config__actions"><AsyncButton className="primary" leadingIcon={<AccountIcon kind="save" />} pending={busyAction === "save-meta-config"} onClick={() => void saveMetaConfiguration()}>{t("opsAccounts.saveMetaConfiguration")}</AsyncButton><small>{t("opsAccounts.secretNeverReturned")}</small></div></div>
                    </div>
                  </details> : null}
                  {oauthConfiguration?.configured ? <div className="ops-accounts-oauth__actions"><AsyncButton className="primary" leadingIcon={<AccountIcon kind={managedAccount ? "reconnect" : "facebook"} />} pending={busyAction === "oauth-start" || busyAction === "oauth-callback"} onClick={() => void beginFacebookOAuth()}>{managedAccount ? t("opsAccounts.reconnectFacebook") : t("opsAccounts.connectFacebook")}</AsyncButton><small>{t("opsAccounts.connectFacebookHint")}</small></div> : null}
                  {oauthSession?.status === "PAGE_SELECTION_REQUIRED" && oauthCatalogPages.length >= 1 ? <div className="ops-accounts-page-picker">
                    <div className="ops-accounts-page-picker__head"><div><strong>{t("opsAccounts.oauthChoosePages")}</strong><small>{t("opsAccounts.oauthChoosePagesHint")}</small></div><label><span>{t("opsAccounts.defaultPriority")}</span><input max="1000" min="0" type="number" value={oauthDefaultPriority} onChange={(event) => setOauthDefaultPriority(event.target.value)} /></label></div>
                    <div className="ops-accounts-page-picker__list">{oauthCatalogPages.map((page) => {
                      const pageState = oauthPageState(oauthSession, page);
                      const selectable = canSelectOAuthPage(oauthSession, page);
                      const selected = selectedOAuthPageIds.includes(page.page_id);
                      return <label className={`state-${pageState.toLowerCase()}${selected ? " is-selected" : ""}`} key={page.page_id}><input checked={selected} disabled={busyAction !== null || !selectable} onChange={() => toggleOAuthPage(page.page_id)} type="checkbox" /><span><b>{page.display_name}</b><small>{page.page_id}</small><small>{page.tasks.join(" · ") || t("opsAccounts.noPageTasks")}</small></span><em>{selected ? t("opsAccounts.selectedPage") : oauthPageStateLabel(pageState)}</em></label>;
                    })}</div>
                    <div className="ops-accounts-page-picker__actions"><span>{t("opsAccounts.selectedPageCount").replace("{count}", String(selectedOAuthPageIds.length))}</span><AsyncButton className="primary" disabled={selectedOAuthPageIds.length === 0} leadingIcon={<AccountIcon kind="add" />} pending={busyAction === "oauth-pages"} onClick={() => void connectSelectedPages(oauthSession)}>{t("opsAccounts.processSelectedPages").replace("{add}", String(selectedNewPageCount)).replace("{reconnect}", String(selectedReconnectPageCount))}</AsyncButton></div>
                  </div> : null}
                  <p className="ops-accounts-oauth__manual">{t("opsAccounts.oauthManualFallback")}</p>
                </section>
                </> : null}

                {activeAccount ? <section className="ops-accounts-setup-card ops-accounts-operations-card">
                  <div className="ops-accounts-operations-deck">
                    <div className="ops-accounts-operations-profile">
                      <span className="ops-accounts-operations-avatar">{activeAccountAvatarUrl ? <img alt="" src={activeAccountAvatarUrl} /> : <b>{accountAvatarLabel(setupForm.displayName)}</b>}<i><AccountIcon kind="facebook" /></i></span>
                      <div className="ops-accounts-operations-profile-copy"><small>{t("opsAccounts.accountOperations")}</small><strong>{setupForm.displayName}</strong><dl className="ops-accounts-managed-identity ops-accounts-operations-facts"><div><dt>{t("opsAccounts.pageId")}</dt><dd>{setupForm.pageId}</dd></div><div><dt>{t("opsAccounts.managedCredential")}</dt><dd>{managedAccount ? t("opsAccounts.oauthManaged") : t("opsAccounts.manualCredential")}</dd></div></dl></div>
                    </div>
                    <div className="ops-accounts-operations-command"><div className="ops-accounts-operations-command__head"><span>{t("opsAccounts.accountOperationsHint")}</span><AccountsChip label={managedAccount ? t("opsAccounts.oauthManaged") : t("opsAccounts.manualCredential")} tone={managedAccount ? "good" : "warn"} /></div><div className="ops-accounts-form-grid ops-accounts-operations-controls"><label>{t("opsAccounts.status")}<select disabled={systemSafetyHold} value={setupForm.status} onChange={(event) => setSetupForm((current) => ({ ...current, status: event.target.value as PlatformAccountStatus }))}><option value="ACTIVE">ACTIVE</option><option value="PAUSED">PAUSED</option><option value="INVALID">INVALID</option><option value="ARCHIVED">ARCHIVED</option></select></label><label>{t("opsAccounts.priority")}<input min="0" max="1000" type="number" value={setupForm.priority} onChange={(event) => setSetupForm((current) => ({ ...current, priority: event.target.value }))} /></label></div></div>
                  </div>
                  {!managedAccount ? <details className="ops-accounts-manual-fallback"><summary><span><b>{t("opsAccounts.manualIdentityEdit")}</b><small>{t("opsAccounts.manualFallbackHint")}</small></span></summary><div className="ops-accounts-form-grid"><label>{t("opsAccounts.displayName")}<input value={setupForm.displayName} onChange={(event) => setSetupForm((current) => ({ ...current, displayName: event.target.value }))} /></label><label>{t("opsAccounts.pageId")}<input value={setupForm.pageId} onChange={(event) => setSetupForm((current) => ({ ...current, pageId: event.target.value }))} /></label><label className="is-wide">{t("opsAccounts.tokenReference")}<input autoCapitalize="characters" value={setupForm.tokenReference} onChange={(event) => setSetupForm((current) => ({ ...current, tokenReference: event.target.value.toUpperCase() }))} /></label><label>{t("opsAccounts.graphVersion")}<input value={setupForm.graphApiVersion} onChange={(event) => setSetupForm((current) => ({ ...current, graphApiVersion: event.target.value }))} /></label></div></details> : null}
                  <details className="ops-accounts-advanced ops-accounts-operations-advanced"><summary>{t("opsAccounts.advancedRouting")}</summary><div className="ops-accounts-form-grid ops-accounts-operations-notes"><label className="is-wide">{t("opsAccounts.allowedNiches")}<input placeholder={t("opsAccounts.allowedNichesHint")} value={setupForm.allowedNiches} onChange={(event) => setSetupForm((current) => ({ ...current, allowedNiches: event.target.value }))} /></label><label>{t("opsAccounts.routingNotes")}<textarea value={setupForm.routingNotes} onChange={(event) => setSetupForm((current) => ({ ...current, routingNotes: event.target.value }))} /></label><label>{t("opsAccounts.operatorNotes")}<textarea value={setupForm.notes} onChange={(event) => setSetupForm((current) => ({ ...current, notes: event.target.value }))} /></label></div></details>
                  <div className="ops-accounts-setup-actions ops-accounts-operations-actions"><span className="ops-accounts-operations-save-note"><AccountIcon kind="shield" />{t("opsAccounts.operationsSaveHint")}</span><AsyncButton className="primary" leadingIcon={<AccountIcon kind="save" />} pending={busyAction === "save-account"} onClick={() => void saveAccount("safety")}>{t("opsAccounts.saveAndCheck")}</AsyncButton></div>
                </section> : setupMethod === "manual" ? <section aria-label={t("opsAccounts.manualFallbackTitle")} className="ops-accounts-manual-panel">
                  <div className="ops-accounts-manual-fallback__body"><div className="ops-accounts-manual-groups"><section><header>{t("opsAccounts.manualIdentityGroup")}</header><div className="ops-accounts-manual-group-fields"><label>{t("opsAccounts.displayName")}<input value={setupForm.displayName} onChange={(event) => setSetupForm((current) => ({ ...current, displayName: event.target.value }))} /></label><label>{t("opsAccounts.pageId")}<input value={setupForm.pageId} onChange={(event) => setSetupForm((current) => ({ ...current, pageId: event.target.value }))} /></label></div></section><section><header>{t("opsAccounts.manualCredentialGroup")}</header><label>{t("opsAccounts.tokenReference")}<input autoCapitalize="characters" value={setupForm.tokenReference} onChange={(event) => setSetupForm((current) => ({ ...current, tokenReference: event.target.value.toUpperCase() }))} /><small>{t("opsAccounts.tokenReferenceHint")}</small></label></section><section><header>{t("opsAccounts.manualDefaultsGroup")}</header><div className="ops-accounts-manual-group-fields is-triple"><label>{t("opsAccounts.graphVersion")}<input value={setupForm.graphApiVersion} onChange={(event) => setSetupForm((current) => ({ ...current, graphApiVersion: event.target.value }))} /></label><label>{t("opsAccounts.status")}<select value={setupForm.status} onChange={(event) => setSetupForm((current) => ({ ...current, status: event.target.value as PlatformAccountStatus }))}><option value="ACTIVE">ACTIVE</option><option value="PAUSED">PAUSED</option></select></label><label>{t("opsAccounts.priority")}<input min="0" max="1000" type="number" value={setupForm.priority} onChange={(event) => setSetupForm((current) => ({ ...current, priority: event.target.value }))} /></label></div></section></div><div className="ops-accounts-setup-actions"><div aria-live="polite" className={`ops-accounts-manual-validation ${manualMissingFields === 0 ? "is-ready" : "is-incomplete"}`}><span aria-hidden="true" /><span>{manualMissingFields === 0 ? t("opsAccounts.manualValidationReady") : t("opsAccounts.manualValidationMissing").replace("{count}", String(manualMissingFields))}</span></div><AsyncButton className="ops-accounts-save-check primary" leadingIcon={<AccountIcon kind="save" />} pending={busyAction === "save-account"} onClick={() => void saveAccount("safety")}>{t("opsAccounts.saveAndCheck")}</AsyncButton></div></div>
                </section> : null}
              </> : null}

              {activeTab === "safety" ? <section className="ops-accounts-setup-card ops-accounts-safety ops-accounts-safety-dashboard">
                <div className="ops-accounts-setup-card__head ops-accounts-safety-head"><div><span><AccountIcon kind="shield" /></span><span><b>{t("opsAccounts.permissionsSafety")}</b><small>{t("opsAccounts.safetyServerManaged")}</small></span></div></div>
                {activeSafety ? <>
                  <div className="ops-accounts-safety-command-grid">
                    <div className={`ops-accounts-safety-runway state-${activeSafety.state.toLowerCase()} is-stage-${activeSafety.warmup_stage.toLowerCase()}`}>
                      <div className="ops-accounts-safety-runway__head"><span><AccountIcon kind="shield" /></span><div><small>{t("opsAccounts.publishingRunway")}</small><strong>{formatChipLabel(activeSafety.state)}</strong><p>{activeSafety.eligible_for_publish ? t("opsAccounts.eligibleForPublish") : activeSafety.blockers[0] ?? t("opsAccounts.notEligibleForPublish")}</p></div><AccountsChip label={formatChipLabel(activeSafety.warmup_stage)} tone={activeSafety.warmup_stage === "STANDARD" ? "good" : "warn"} /></div>
                      <div className="ops-accounts-safety-runway__track"><i /></div>
                      <ol>{safetyStages.map((stage, index) => <li className={index < activeSafetyStageIndex ? "is-complete" : index === activeSafetyStageIndex ? "is-current" : "is-upcoming"} key={stage}><i /><span><b>{formatChipLabel(stage)}</b><small>{index < activeSafetyStageIndex ? t("opsAccounts.stageCompleted") : index === activeSafetyStageIndex ? t("opsAccounts.stageCurrent") : t("opsAccounts.stageUpcoming")}</small></span></li>)}</ol>
                      <div className="ops-accounts-safety-runway__promotion"><span>{t("opsAccounts.nextStageRequirement")}</span><strong>{activeSafety.next_stage_min_successes == null ? t("opsAccounts.standardStageReached") : t("opsAccounts.confirmedPublishRequirement").replace("{count}", String(activeSafety.next_stage_min_successes))}</strong><small>{t("opsAccounts.nextStageEarliest")} · {formatDateTime(activeSafety.next_stage_earliest_at)}</small></div>
                    </div>
                    <div className="ops-accounts-safety-metrics">
                      <div><span>{t("opsAccounts.warmupStage")}</span><b>{formatChipLabel(activeSafety.warmup_stage)}</b></div>
                      <div><span>{t("opsAccounts.confirmedPublishes")}</span><b>{activeSafety.confirmed_connector_publishes}</b></div>
                      <div><span>{t("opsAccounts.attempts24h")}</span><b>{activeSafety.attempts_24h} / {activeSafety.effective_max_attempts_24h}</b></div>
                      <div><span>{t("opsAccounts.failures24h")}</span><b>{activeSafety.failures_24h}</b></div>
                      <div><span>{t("opsAccounts.activeAttempts")}</span><b>{activeSafety.active_attempts}</b></div>
                      <div><span>{t("opsAccounts.unresolvedAttempts")}</span><b>{activeSafety.unresolved_attempts}</b></div>
                    </div>
                  </div>
                  <dl className="ops-accounts-safety-details">
                    <div><dt>{t("opsAccounts.credentialSource")}</dt><dd>{activeSafety.credential_source ?? (activeSafety.managed_credential ? "META_OAUTH" : "MANUAL")}</dd></div>
                    <div><dt>{t("opsAccounts.publishScopes")}</dt><dd>{activeSafety.verified_publish_scopes.join(" · ") || "—"}</dd></div>
                    <div><dt>{t("opsAccounts.pageTasks")}</dt><dd>{activeSafety.page_tasks.join(" · ") || "—"}</dd></div>
                    <div><dt>{t("opsAccounts.capabilityVerified")}</dt><dd>{formatDateTime(activeSafety.capability_verified_at)}</dd></div>
                    <div><dt>{t("opsAccounts.capabilityExpires")}</dt><dd>{formatDateTime(activeSafety.capability_expires_at)}</dd></div>
                    <div><dt>{t("opsAccounts.nextPublishAt")}</dt><dd>{formatDateTime(activeSafety.next_publish_at)}</dd></div>
                    <div><dt>{t("opsAccounts.nextStageRequirement")}</dt><dd>{activeSafety.next_stage_min_successes == null ? t("opsAccounts.standardStageReached") : t("opsAccounts.confirmedPublishRequirement").replace("{count}", String(activeSafety.next_stage_min_successes))}</dd></div>
                    <div><dt>{t("opsAccounts.nextStageEarliest")}</dt><dd>{formatDateTime(activeSafety.next_stage_earliest_at)}</dd></div>
                    <div><dt>{t("opsAccounts.minimumInterval")}</dt><dd>{activeSafety.effective_min_interval_minutes} {t("opsAccounts.minutes")}</dd></div>
                  </dl>
                  {activeSafety.blockers.length > 0 ? <ul className="ops-accounts-safety-messages is-blocked">{activeSafety.blockers.map((item) => <li key={item}>{item}</li>)}</ul> : null}
                  {activeSafety.warnings.length > 0 ? <ul className="ops-accounts-safety-messages is-warning">{activeSafety.warnings.map((item) => <li key={item}>{item}</li>)}</ul> : null}
                </> : <p className="muted">{t("opsAccounts.safetyStatusUnavailable")}</p>}
                <div className="ops-accounts-safety-control-deck"><aside className="ops-accounts-safety-controls ops-accounts-safety-control-deck__state"><label className={`ops-accounts-consent${setupForm.isOnHold ? " is-enabled" : ""}`}><input checked={setupForm.isOnHold} disabled={systemSafetyHold} onChange={(event) => setSetupForm((current) => ({ ...current, isOnHold: event.target.checked }))} type="checkbox" /><span><b>{t("opsAccounts.manualHold")}</b><small>{systemSafetyHold ? t("opsAccounts.systemHoldReconnect") : t("opsAccounts.manualHoldHint")}</small></span></label><label className="is-cooldown">{t("opsAccounts.cooldownUntil")}<input disabled={Boolean(activeSafety?.cooldown_until && new Date(activeSafety.cooldown_until).getTime() > Date.now())} type="datetime-local" value={setupForm.cooldownUntil} onChange={(event) => setSetupForm((current) => ({ ...current, cooldownUntil: event.target.value }))} /></label></aside><section className="ops-accounts-safety-control-deck__workspace"><label className="is-reason">{t("opsAccounts.holdReason")}<input readOnly={systemSafetyHold} value={setupForm.holdReason} onChange={(event) => setSetupForm((current) => ({ ...current, holdReason: event.target.value }))} /></label><div className="ops-accounts-setup-actions ops-accounts-safety-actions"><Link className="ops-accounts-publication-link" href={publicationLibraryHref(activeAccount?.id)}><AccountIcon kind="library" />{t("opsAccounts.openPublicationLibrary")}</Link><div><AsyncButton disabled={!activeAccount} leadingIcon={<AccountIcon kind="check" />} pending={busyAction === "account-check"} onClick={() => void runAccountCheck()}>{t("opsAccounts.runSetupCheck")}</AsyncButton>{oauthConfiguration?.configured && activeSafety?.state === "RECONNECT_REQUIRED" ? <AsyncButton leadingIcon={<AccountIcon kind="reconnect" />} pending={busyAction === "oauth-start"} onClick={() => void beginFacebookOAuth()}>{t("opsAccounts.reconnectFacebook")}</AsyncButton> : null}<AsyncButton className="primary" leadingIcon={<AccountIcon kind="save" />} pending={busyAction === "save-account"} onClick={() => void saveAccount("safety")}>{t("opsAccounts.saveSafety")}</AsyncButton></div></div></section></div>
                {accountCheck ? <CheckList blockedLabel={t("opsAccounts.accountBlocked")} blockingGroupLabel={t("opsAccounts.blockingChecks")} checks={accountCheck.checks} passedGroupLabel={t("opsAccounts.passedChecks")} ready={accountCheck.ready_for_publication_setup} readyLabel={t("opsAccounts.accountReady")} warningGroupLabel={t("opsAccounts.warningChecks")} /> : null}
              </section> : null}

              </div>

            </section>
          ) : null}

          <section className="ops-accounts-board ops-accounts-lanes-board">
              <header className="ops-accounts-board__head">
                <div><h2><AccountIcon kind="shield" />{t("opsAccounts.platformAccounts")}</h2><p>{t("opsAccounts.setupFootnote")}</p></div>
                <div className="ops-accounts-board__commands">
                  <button className="ops-accounts-add-page" onClick={openCreate} type="button"><AccountIcon kind="add" /><span>{t("opsAccounts.addFacebookPage")}</span></button>
                  <nav className="ops-accounts-actions" aria-label={t("opsAccounts.triage")}>
                    <Link href={publicationLibraryHref(activeAccount?.id)}><AccountIcon kind="library" /><span>{t("opsAccounts.openPublicationLibrary")}</span></Link>
                    <Link href="/publishing/drafts"><AccountIcon kind="drafts" /><span>{t("opsAccounts.openPublishDrafts")}</span></Link>
                  </nav>
                </div>
              </header>
              {rows.length === 0 ? <p className="ops-accounts-empty">{t("opsAccounts.noPlatformAccountsConfigured")}</p> : (
                <div className="ops-accounts-table-shell">
                  <div className="ops-accounts-table__meta">
                    <span><AccountIcon kind="queue" />{t("opsAccounts.tableViewHint")}</span>
                    <strong>{t("opsAccounts.accountCount").replace("{count}", String(rows.length))}</strong>
                  </div>
                  <div className="ops-accounts-table__scroll">
                    <table className="ops-accounts-table">
                      <colgroup><col className="is-account" /><col className="is-state" /><col className="is-performance" /><col className="is-workload" /><col className="is-window" /><col className="is-action" /></colgroup>
                      <thead><tr><th scope="col">{t("opsAccounts.accountColumn")}</th><th scope="col">{t("opsAccounts.readiness")}</th><th scope="col">{t("opsAccounts.performance7d")}</th><th scope="col">{t("opsAccounts.workload")}</th><th scope="col">{t("opsAccounts.nextWindow")}</th><th aria-label={t("opsAccounts.setup")} scope="col" /></tr></thead>
                      {readinessLanes.filter((lane) => lane.items.length > 0).map((lane) => {
                        const collapsed = collapsedLanes.has(lane.key);
                        return <tbody className={`is-${lane.key}`} key={lane.key}>
                          <tr className="ops-accounts-table__group"><th colSpan={6} scope="rowgroup"><button aria-expanded={!collapsed} onClick={() => toggleReadinessLane(lane.key)} type="button"><AccountIcon kind={lane.icon} /><b>{lane.label}</b><small>{lane.hint}</small><em>{lane.items.length}</em><AccountIcon className="ops-accounts-table__chevron" kind="chevron" /></button></th></tr>
                          {!collapsed ? lane.items.map((account) => {
                            const nextWindow = account.safetyStatus?.next_publish_at ?? account.safetyStatus?.cooldown_until ?? account.cooldown_until;
                            const assignedCount = account.healthSummary?.assigned_draft_count ?? 0;
                            const scheduledCount = account.healthSummary?.scheduled_draft_count ?? 0;
                            const successRate = account.healthSummary ? Math.round(account.healthSummary.success_rate_percent) : null;
                            const avatarUrl = accountAvatarUrl(account);
                            const attentionReason = account.safetyStatus?.blockers[0] ?? account.hold_reason ?? account.healthSummary?.recent_error_code ?? account.healthSummary?.reasons[0] ?? null;
                            return (
                              <tr className="ops-accounts-table__row" key={account.id}>
                                <td><div className="ops-accounts-table__identity"><span aria-hidden="true" className="ops-accounts-table__avatar"><b>{accountAvatarLabel(account.display_name)}</b>{avatarUrl ? <img alt="" loading="lazy" onError={(event) => { event.currentTarget.hidden = true; }} referrerPolicy="no-referrer" src={avatarUrl} /> : null}<i><AccountIcon kind="facebook" /></i></span><div><strong title={account.display_name}>{account.display_name}</strong><small>{t("opsAccounts.pageId")} · {account.external_account_id}</small></div></div></td>
                                <td><div className="ops-accounts-table__state"><div><AccountsChip label={account.safetyStatus?.state ?? account.status} tone={account.safetyStatus ? safetyTone(account.safetyStatus) : statusTone(account.status)} />{account.healthStatus ? <AccountsChip label={account.healthStatus} tone={account.healthStatus === "HEALTHY" ? "good" : account.healthStatus === "DEGRADED" ? "warn" : "danger"} /> : null}</div><small title={attentionReason ?? undefined}>{attentionReason ?? t("opsAccounts.noActiveBlockers")}</small></div></td>
                                <td><div className="ops-accounts-table__performance"><div><strong>{successRate == null ? "—" : `${successRate}%`}</strong><small>{account.healthSummary ? t("opsAccounts.attemptsFailed7d").replace("{attempts}", String(account.healthSummary.attempts_7d)).replace("{failed}", String(account.healthSummary.failed_7d)) : t("opsAccounts.noPerformanceData")}</small></div><span aria-hidden="true"><i style={{ width: `${successRate ?? 0}%` }} /></span></div></td>
                                <td><div className="ops-accounts-table__workload"><strong><AccountIcon kind="queue" />{assignedCount + scheduledCount}</strong><small>{t("opsAccounts.assignedScheduledCounts").replace("{assigned}", String(assignedCount)).replace("{scheduled}", String(scheduledCount))}</small></div></td>
                                <td><div className="ops-accounts-table__window"><span aria-hidden="true" /><div><strong>{nextWindow ? formatDateTime(nextWindow) : t("opsAccounts.readyNow")}</strong><small>{account.safetyStatus ? `${t("opsAccounts.warmupStage")} · ${formatChipLabel(account.safetyStatus.warmup_stage)}` : t("opsAccounts.nextWindow")}</small></div></div></td>
                                <td><button aria-label={`${t("opsAccounts.setup")} · ${account.display_name}`} className="ops-accounts-table__action" onClick={() => openEdit(account)} title={`${t("opsAccounts.setup")} · ${account.display_name}`} type="button"><AccountIcon kind="settings" /></button></td>
                              </tr>
                            );
                          }) : null}
                        </tbody>;
                      })}
                    </table>
                  </div>
                </div>
              )}
          </section>
        </main>
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}
