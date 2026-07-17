"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  cancelDouyinBrowserConnect,
  captureDouyinCurrentPage,
  createDouyinAccount,
  deleteDouyinAccount,
  detectDouyinCurrentPage,
  enqueueDouyinAccountsRevalidateDueJob,
  fetchActiveDouyinBrowserConnect,
  fetchDouyinBrowserConnect,
  fetchDouyinAccounts,
  markDouyinAccountChallengeSolved,
  recheckDouyinAccountChallenge,
  resetDouyinBrowserConnectState,
  restartDouyinBrowserConnect,
  retryDouyinBrowserConnectValidation,
  startDouyinBrowserConnect,
  validateDouyinAccount
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { DouyinAccount, DouyinBrowserConnectSession, DouyinCurrentPageDetectionResponse } from "../../types/douyin-accounts";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PageShell } from "../app-shell/PageShell";
import { StatusBadge } from "../app-shell/StatusBadge";

type FormState = {
  displayName: string;
  sessionCookie: string;
  userAgent: string;
  proxyUrl: string;
  isDefault: boolean;
  notes: string;
};

type BrowserConnectFormState = {
  displayName: string;
  userAgent: string;
  proxyUrl: string;
  isDefault: boolean;
};

const EMPTY_FORM: FormState = {
  displayName: "",
  sessionCookie: "",
  userAgent: "",
  proxyUrl: "",
  isDefault: false,
  notes: ""
};

const EMPTY_BROWSER_FORM: BrowserConnectFormState = {
  displayName: "",
  userAgent: "",
  proxyUrl: "",
  isDefault: false
};

const TERMINAL_CONNECT_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED"]);
const SHOW_LEGACY_DOUYIN_DEBUG_SURFACES = process.env.NEXT_PUBLIC_DOUYIN_ENABLE_LEGACY_DEBUG_SURFACES === "true";

export function DouyinAccountsPage() {
  const t = useT();
  const [accounts, setAccounts] = useState<DouyinAccount[]>([]);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [startingBrowserConnect, setStartingBrowserConnect] = useState(false);
  const [checkingActiveConnect, setCheckingActiveConnect] = useState(false);
  const [resettingBrowserConnect, setResettingBrowserConnect] = useState(false);
  const [retryingValidation, setRetryingValidation] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [browserForm, setBrowserForm] = useState<BrowserConnectFormState>(EMPTY_BROWSER_FORM);
  const [browserConnect, setBrowserConnect] = useState<DouyinBrowserConnectSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [currentPageByAccount, setCurrentPageByAccount] = useState<Record<string, DouyinCurrentPageDetectionResponse>>({});
  const activeConnectSessionIdRef = useRef<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setAccounts(await fetchDouyinAccounts());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    void loadActiveBrowserConnect();
  }, []);

  useEffect(() => {
    if (!browserConnect || TERMINAL_CONNECT_STATUSES.has(browserConnect.status)) return;
    const interval = window.setInterval(() => {
      void pollBrowserConnect(browserConnect.id);
    }, 2000);
    return () => window.clearInterval(interval);
  }, [browserConnect?.id, browserConnect?.status]);

  useEffect(() => {
    activeConnectSessionIdRef.current = browserConnect?.id ?? null;
  }, [browserConnect?.id]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (!form.displayName.trim() || !form.sessionCookie.trim()) {
      setError(t("douyinAccounts.requiredError"));
      return;
    }
    setSaving(true);
    try {
      const created = await createDouyinAccount({
        display_name: form.displayName.trim(),
        session_cookie: form.sessionCookie.trim(),
        user_agent: form.userAgent.trim() || null,
        proxy_url: form.proxyUrl.trim() || null,
        is_default: form.isDefault,
        metadata_json: { connection_source: "manual_import" },
        notes: form.notes.trim() || null
      });
      setForm(EMPTY_FORM);
      setMessage(buildManualImportResultMessage(created, t));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.saveError"));
    } finally {
      setSaving(false);
    }
  }

  async function startBrowserConnect() {
    setError(null);
    setMessage(null);
    setStartingBrowserConnect(true);
    try {
      const connect = await startDouyinBrowserConnect(browserConnectPayload(browserForm));
      setBrowserConnect(connect);
      activeConnectSessionIdRef.current = connect.id;
      if (connect.can_resume) {
        setMessage(t("douyinAccounts.activeConnectFound"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.browserStartError"));
    } finally {
      setStartingBrowserConnect(false);
    }
  }

  async function openBrowserProfile(account: DouyinAccount) {
    setBusyId(account.id);
    setError(null);
    setMessage(null);
    setStartingBrowserConnect(true);
    try {
      const connect = await startDouyinBrowserConnect(browserConnectPayload(browserForm, account));
      setBrowserConnect(connect);
      activeConnectSessionIdRef.current = connect.id;
      setMessage(t("douyinAccounts.browserProfileOpened"));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.browserStartError"));
    } finally {
      setStartingBrowserConnect(false);
      setBusyId(null);
    }
  }

  async function loadActiveBrowserConnect() {
    setCheckingActiveConnect(true);
    try {
      const response = await fetchActiveDouyinBrowserConnect();
      if (response.session) {
        setBrowserConnect(response.session);
        activeConnectSessionIdRef.current = response.session.id;
      }
    } catch {
      // Active-session discovery is best-effort; normal account loading should not be blocked.
    } finally {
      setCheckingActiveConnect(false);
    }
  }

  async function resumeBrowserConnect() {
    if (!browserConnect) return;
    setError(null);
    setMessage(null);
    try {
      activeConnectSessionIdRef.current = browserConnect.id;
      const next = await fetchDouyinBrowserConnect(browserConnect.id);
      setBrowserConnect(next);
      setMessage(t("douyinAccounts.browserResumed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.browserResumeError"));
    }
  }

  async function forceRestartBrowserConnect() {
    if (!browserConnect) return;
    setError(null);
    setMessage(null);
    setStartingBrowserConnect(true);
    try {
      const targetAccount = accounts.find((account) => account.id === browserConnect.derived_account_id) ?? browserConnect.account ?? null;
      const next = await restartDouyinBrowserConnect(browserConnect.id, browserConnectPayload(browserForm, targetAccount ?? undefined));
      setBrowserConnect(next);
      activeConnectSessionIdRef.current = next.id;
      setMessage(t("douyinAccounts.browserRestarted"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.browserRestartError"));
    } finally {
      setStartingBrowserConnect(false);
    }
  }

  async function resetBrowserConnectState() {
    const confirmed = window.confirm(t("douyinAccounts.resetConnectConfirm"));
    if (!confirmed) return;
    setError(null);
    setMessage(null);
    setResettingBrowserConnect(true);
    try {
      const result = await resetDouyinBrowserConnectState();
      setBrowserConnect(null);
      activeConnectSessionIdRef.current = null;
      setMessage(
        result.reset_count > 0
          ? `${t("douyinAccounts.resetConnectDone")}: ${result.reset_count}`
          : t("douyinAccounts.resetConnectNothing")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.resetConnectError"));
    } finally {
      setResettingBrowserConnect(false);
    }
  }

  async function retryBrowserConnectValidation() {
    if (!browserConnect) return;
    setError(null);
    setMessage(null);
    setRetryingValidation(true);
    try {
      const next = await retryDouyinBrowserConnectValidation(browserConnect.id);
      setBrowserConnect(next);
      activeConnectSessionIdRef.current = next.id;
      if (next.status === "COMPLETED") {
        setMessage(t("douyinAccounts.validationRetryPassed"));
        await load();
      } else {
        setMessage(t("douyinAccounts.validationRetryFinished"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.validationRetryError"));
    } finally {
      setRetryingValidation(false);
    }
  }

  async function pollBrowserConnect(connectSessionId: string) {
    try {
      const next = await fetchDouyinBrowserConnect(connectSessionId);
      if (activeConnectSessionIdRef.current !== connectSessionId) {
        return;
      }
      setBrowserConnect(next);
      if (next.status === "COMPLETED") {
        setMessage(t("douyinAccounts.browserCompleted"));
        setBrowserForm(EMPTY_BROWSER_FORM);
        await load();
      } else if (next.outcome === "timed_out") {
        setMessage(t("douyinAccounts.browserTimedOut"));
      } else if (next.status === "CANCELLED") {
        setMessage(t("douyinAccounts.browserCancelled"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.browserPollError"));
    }
  }

  async function cancelBrowserConnect() {
    if (!browserConnect) return;
    setError(null);
    try {
      setBrowserConnect(await cancelDouyinBrowserConnect(browserConnect.id));
      setMessage(t("douyinAccounts.browserCancelled"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.browserCancelError"));
    }
  }

  async function validate(account: DouyinAccount) {
    setBusyId(account.id);
    setError(null);
    setMessage(null);
    try {
      const result = await validateDouyinAccount(account.id);
      const preflightSummary = result.account.manual_import_preflight?.summary;
      setMessage(
        result.valid
          ? (preflightSummary ?? t("douyinAccounts.validationPassed"))
          : `${t("douyinAccounts.validationFailed")}: ${preflightSummary ?? result.reason}`
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.validateError"));
    } finally {
      setBusyId(null);
    }
  }

  async function markChallengeSolved(account: DouyinAccount) {
    setBusyId(account.id);
    setError(null);
    setMessage(null);
    try {
      const result = await markDouyinAccountChallengeSolved(account.id);
      const postCheck = postChallengeRecheckResultLabel(result.post_challenge_recheck_result, t);
      const intakeReady = result.intake_ready_after_recheck ? t("douyinAccounts.intakeReadyAfterRecheck") : t("douyinAccounts.intakeStillBlockedAfterRecheck");
      const sameProfile = result.same_profile_reused ? t("douyinAccounts.sameProfileReused") : t("douyinAccounts.sameProfileNotConfirmed");
      setMessage(`${t("douyinAccounts.challengeSolvedPostcheckCompleted")}: ${postCheck} · ${sameProfile} · ${intakeReady}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.challengeActionError"));
    } finally {
      setBusyId(null);
    }
  }

  async function recheckChallenge(account: DouyinAccount) {
    setBusyId(account.id);
    setError(null);
    setMessage(null);
    try {
      const result = await recheckDouyinAccountChallenge(account.id);
      setMessage(
        result.valid
          ? `${t("douyinAccounts.challengeRecheckPassed")}: ${postChallengeRecheckResultLabel(result.post_challenge_recheck_result, t)}`
          : `${t("douyinAccounts.challengeRecheckStillBlocked")}: ${postChallengeRecheckResultLabel(result.post_challenge_recheck_result, t)} · ${result.reason ?? challengeStateLabel(result.challenge_state, t)}`
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.challengeActionError"));
    } finally {
      setBusyId(null);
    }
  }

  async function detectCurrentPage(account: DouyinAccount) {
    setBusyId(account.id);
    setError(null);
    setMessage(null);
    try {
      const result = await detectDouyinCurrentPage(account.id);
      setCurrentPageByAccount((current) => ({ ...current, [account.id]: result }));
      setMessage(buildCurrentPageDetectionMessage(result, t));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.currentPageDetectError"));
    } finally {
      setBusyId(null);
    }
  }

  async function captureCurrentPage(account: DouyinAccount) {
    setBusyId(account.id);
    setError(null);
    setMessage(null);
    try {
      const result = await captureDouyinCurrentPage(account.id, { persist: true, max_videos: 50 });
      setMessage(buildCurrentPageCaptureMessage(result, t));
      const detection = await detectDouyinCurrentPage(account.id);
      setCurrentPageByAccount((current) => ({ ...current, [account.id]: detection }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.currentPageCaptureError"));
    } finally {
      setBusyId(null);
    }
  }

  async function queueHealthSweep() {
    setBusyId("health-sweep");
    setError(null);
    setMessage(null);
    try {
      const job = await enqueueDouyinAccountsRevalidateDueJob({ due_only: true });
      setMessage(`${t("douyinAccounts.healthSweepQueued")}: ${job.job_id} (${job.queued_accounts_count ?? 0})`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.revalidateError"));
    } finally {
      setBusyId(null);
    }
  }

  function useInIntake(account: DouyinAccount) {
    const params = new URLSearchParams({ douyinAccountConnectionId: account.id });
    window.location.href = `/intake?${params.toString()}`;
  }

  async function deleteAccount(account: DouyinAccount) {
    const confirmed = window.confirm(buildDeleteConfirm(account, accounts, t));
    if (!confirmed) return;
    setBusyId(account.id);
    setError(null);
    setMessage(null);
    try {
      const result = await deleteDouyinAccount(account.id);
      const warningSuffix = result.warnings.length > 0 ? ` (${result.warnings.join(", ")})` : "";
      setMessage(`${t("douyinAccounts.deleteSuccess")}${warningSuffix}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("douyinAccounts.deleteError"));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <OperatorStudioShell
      actions={<a className="operator-inline-link" href="/intake">{t("douyinAccounts.openIntake")}</a>}
      description={t("douyinAccounts.description")}
      title={t("douyinAccounts.title")}
    >
      <PageShell description={t("douyinAccounts.pageDescription")} title={t("douyinAccounts.workflowTitle")}>
        {error ? <div className="inline-error">{error}</div> : null}
        {message ? <div className="inline-success">{message}</div> : null}
        <div className="intake-kicker" aria-label={t("douyinAccounts.healthSummary")}>
          <span>{t("douyinAccounts.healthyAccounts")}: {accounts.filter((account) => account.health_status === "HEALTHY").length}</span>
          <span>{t("douyinAccounts.warningAccounts")}: {accounts.filter((account) => account.warning_level === "WARN").length}</span>
          <span>{t("douyinAccounts.blockedAccounts")}: {accounts.filter((account) => account.warning_level === "BLOCK").length}</span>
        </div>
        {accounts.length > 0 && !accounts.some((account) => account.can_use_for_live_fetch) ? (
          <div className="inline-error">{t("douyinAccounts.noUsableAccounts")}</div>
        ) : null}

        <div className="intake-layout">
          <div className="intake-form">
            <section className="operator-panel">
              <div className="operator-panel-heading">
                <div>
                  <h2>{t("douyinAccounts.extensionTitle")}</h2>
                  <p>{t("douyinAccounts.extensionDescription")}</p>
                </div>
              </div>
              <ol className="intake-flow">
                <li>{t("douyinAccounts.extensionGuideInstall")}</li>
                <li>{t("douyinAccounts.extensionGuideBrowse")}</li>
                <li>{t("douyinAccounts.extensionGuideDetect")}</li>
                <li>{t("douyinAccounts.extensionGuideCapture")}</li>
              </ol>
              <p className="muted">{t("douyinAccounts.extensionPrivacyNote")}</p>
            </section>

            <details className="operator-panel">
              <summary><strong>{t("douyinAccounts.browserTitle")}</strong></summary>
              <p>{t("douyinAccounts.browserDescription")}</p>
              <div className="operator-panel-heading">
                <div>
                  <h2>{t("douyinAccounts.browserLegacyControlsTitle")}</h2>
                  <p>{t("douyinAccounts.browserLegacyControlsDescription")}</p>
                </div>
                <div className="intake-actions">
                  <button disabled={startingBrowserConnect} type="button" onClick={() => void startBrowserConnect()}>
                    {startingBrowserConnect ? t("douyinAccounts.browserStarting") : t("douyinAccounts.connectWithBrowser")}
                  </button>
                  <button disabled={resettingBrowserConnect} type="button" onClick={() => void resetBrowserConnectState()}>
                    {resettingBrowserConnect ? t("douyinAccounts.resetConnectRunning") : t("douyinAccounts.resetConnectState")}
                  </button>
                </div>
              </div>
              <div className="filter-grid">
                <label className="field">
                  <span>{t("douyinAccounts.displayName")}</span>
                  <input value={browserForm.displayName} onChange={(event) => setBrowserForm({ ...browserForm, displayName: event.target.value })} />
                </label>
                <label className="field">
                  <span>{t("douyinAccounts.userAgent")}</span>
                  <input value={browserForm.userAgent} onChange={(event) => setBrowserForm({ ...browserForm, userAgent: event.target.value })} />
                </label>
                <label className="field">
                  <span>{t("douyinAccounts.proxyUrl")}</span>
                  <input value={browserForm.proxyUrl} onChange={(event) => setBrowserForm({ ...browserForm, proxyUrl: event.target.value })} />
                </label>
              </div>
              <label className="intake-checkbox-field">
                <input checked={browserForm.isDefault} onChange={(event) => setBrowserForm({ ...browserForm, isDefault: event.target.checked })} type="checkbox" />
                <span>
                  <strong>{t("douyinAccounts.makeDefault")}</strong>
                  <small>{t("douyinAccounts.makeDefaultHelp")}</small>
                </span>
              </label>
            </details>

            <details className="operator-panel">
              <summary><strong>{t("douyinAccounts.troubleshootingTitle")}</strong></summary>
              <p>{t("douyinAccounts.troubleshootingDescription")}</p>
              <div className="intake-actions">
                {browserConnect?.can_resume ? (
                  <button type="button" onClick={() => void resumeBrowserConnect()}>{t("douyinAccounts.resumeConnect")}</button>
                ) : null}
                {browserConnect?.can_cancel ? (
                  <button type="button" onClick={() => void cancelBrowserConnect()}>{t("douyinAccounts.cancelConnect")}</button>
                ) : null}
                {browserConnect?.can_force_restart ? (
                  <button disabled={startingBrowserConnect} type="button" onClick={() => void forceRestartBrowserConnect()}>{t("douyinAccounts.forceRestartConnect")}</button>
                ) : null}
                {browserConnect?.can_retry_validation ? (
                  <button disabled={retryingValidation} type="button" onClick={() => void retryBrowserConnectValidation()}>
                    {retryingValidation ? t("douyinAccounts.retryingValidation") : t("douyinAccounts.retryValidation")}
                  </button>
                ) : null}
                <button disabled={busyId === "health-sweep"} type="button" onClick={() => void queueHealthSweep()}>{t("douyinAccounts.queueHealthSweep")}</button>
              </div>
              {checkingActiveConnect ? <p className="muted">{t("douyinAccounts.checkingActiveConnect")}</p> : null}
              {browserConnect ? (
                <div className={`field-warning${connectTone(browserConnect.status) === "danger" ? " danger" : connectTone(browserConnect.status) === "good" ? " good" : ""}`}>
                  <span className="status-pill">{browserConnect.is_stale ? t("douyinAccounts.staleConnectTitle") : t("douyinAccounts.activeConnectTitle")}</span>
                  <strong>{connectPrimaryMessage(browserConnect, t)}</strong>
                  <p>{connectSecondaryMessage(browserConnect, t)}</p>
                  <p>{t("douyinAccounts.connectPhase")}: {connectPhaseLabel(browserConnect.phase, t)}</p>
                  {typeof browserConnect.age_seconds === "number" ? <p>{t("douyinAccounts.ageSeconds")}: {browserConnect.age_seconds}</p> : null}
                  {typeof browserConnect.remaining_seconds === "number" ? <p>{t("douyinAccounts.remainingSeconds")}: {browserConnect.remaining_seconds}</p> : null}
                  {browserConnect.stale_reason ? <p>{t("douyinAccounts.staleReason")}: {browserConnect.stale_reason}</p> : null}
                  {browserConnect.validation_attempt_count > 0 ? <p>{t("douyinAccounts.validationAttempts")}: {browserConnect.validation_attempt_count}</p> : null}
                  {browserConnect.should_keep_browser_open ? <p className="field-warning">{t("douyinAccounts.keepBrowserOpen")}</p> : null}
                  {browserConnect.account ? <p>{t("douyinAccounts.connectedAs")}: {browserConnect.account.display_name}</p> : null}
                </div>
              ) : (
                <p className="muted">{t("douyinAccounts.noActiveConnectSession")}</p>
              )}
            </details>

            {SHOW_LEGACY_DOUYIN_DEBUG_SURFACES ? (
              <details className="operator-panel" id="manual-session-import">
                <summary><strong>{t("douyinAccounts.importTitle")}</strong></summary>
                <form className="intake-form" onSubmit={(event) => void submit(event)}>
                  <p>{t("douyinAccounts.importDescription")}</p>
                  <label className="field">
                    <span>{t("douyinAccounts.displayName")}</span>
                    <input value={form.displayName} onChange={(event) => setForm({ ...form, displayName: event.target.value })} />
                  </label>
                  <label className="field">
                    <span>{t("douyinAccounts.sessionCookie")}</span>
                    <textarea rows={5} value={form.sessionCookie} onChange={(event) => setForm({ ...form, sessionCookie: event.target.value })} />
                    <small>{t("douyinAccounts.sessionCookieHelp")}</small>
                  </label>
                  <label className="field">
                    <span>{t("douyinAccounts.userAgent")}</span>
                    <input value={form.userAgent} onChange={(event) => setForm({ ...form, userAgent: event.target.value })} />
                  </label>
                  <label className="field">
                    <span>{t("douyinAccounts.proxyUrl")}</span>
                    <input value={form.proxyUrl} onChange={(event) => setForm({ ...form, proxyUrl: event.target.value })} />
                  </label>
                  <label className="field">
                    <span>{t("douyinAccounts.notes")}</span>
                    <textarea rows={3} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
                  </label>
                  <label className="intake-checkbox-field">
                    <input checked={form.isDefault} onChange={(event) => setForm({ ...form, isDefault: event.target.checked })} type="checkbox" />
                    <span>
                      <strong>{t("douyinAccounts.makeDefault")}</strong>
                      <small>{t("douyinAccounts.makeDefaultHelp")}</small>
                    </span>
                  </label>
                  <div className="intake-actions">
                    <button className="primary" disabled={saving} type="submit">{saving ? t("douyinAccounts.saving") : t("douyinAccounts.importAccount")}</button>
                    <button disabled={saving} type="button" onClick={() => setForm(EMPTY_FORM)}>{t("common.cancel")}</button>
                  </div>
                </form>
              </details>
            ) : null}
          </div>

          <aside className="intake-side">
            <section className="operator-panel">
              <div className="operator-panel-heading">
                <div>
                  <h2>{t("douyinAccounts.guidanceTitle")}</h2>
                  <p>{t("douyinAccounts.guidanceDescription")}</p>
                </div>
              </div>
              <ol className="intake-flow">
                <li>{t("douyinAccounts.guideInstallExtension")}</li>
                <li>{t("douyinAccounts.guideValidate")}</li>
                <li>{t("douyinAccounts.guideDetect")}</li>
                <li>{t("douyinAccounts.guideCapture")}</li>
                <li>{t("douyinAccounts.guideSelect")}</li>
              </ol>
            </section>
          </aside>
        </div>

        <section className="operator-panel">
          <div className="operator-panel-heading">
            <div>
              <h2>{t("douyinAccounts.connectedAccounts")}</h2>
              <p>{t("douyinAccounts.connectedDescription")}</p>
            </div>
            <button type="button" onClick={() => void load()}>{loading ? t("common.loading") : t("common.refresh")}</button>
          </div>
          <table className="health-table">
            <thead>
              <tr>
                <th>{t("douyinAccounts.account")}</th>
                <th>{t("douyinAccounts.health")}</th>
                <th>{t("common.status")}</th>
                <th>{t("douyinAccounts.source")}</th>
                <th>{t("douyinAccounts.browserContext")}</th>
                <th>{t("douyinAccounts.cookie")}</th>
                <th>{t("douyinAccounts.lastValidated")}</th>
                <th>{t("douyinAccounts.nextValidation")}</th>
                <th>{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 ? <tr><td colSpan={9}>{t("douyinAccounts.noAccounts")}</td></tr> : null}
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td>
                    <strong>{account.display_name}</strong>
                    {account.is_default ? <span> - {t("douyinAccounts.default")}</span> : null}
                    {account.warning_summary_json?.reason ? <small className="muted block">{String(account.warning_summary_json.reason)}</small> : null}
                    {account.last_error_message ? (
                      <small className="muted block">
                        {account.last_error_code ? `${account.last_error_code}: ` : ""}
                        {account.last_error_message}
                      </small>
                    ) : null}
                    {SHOW_LEGACY_DOUYIN_DEBUG_SURFACES && account.manual_import_preflight ? (
                      <details style={{ marginTop: "0.5rem" }}>
                        <summary><strong>{manualImportPreflightTitle(account)}</strong></summary>
                        <small className="muted block">{account.manual_import_preflight.summary}</small>
                        <small className="muted block">Next: {account.manual_import_preflight.next_action}</small>
                        <small className="muted block">Format: {account.manual_import_preflight.detected_format ?? "-"}</small>
                        <small className="muted block">Cookie strength: {account.manual_import_preflight.cookie_strength ?? "-"}</small>
                        <small className="muted block">Checked: {formatDateTime(account.manual_import_preflight.checked_at)}</small>
                      </details>
                    ) : null}
                    {isProfileQuarantined(account) ? (
                      <div className="field-warning" style={{ marginTop: "0.5rem" }}>
                        <span className="status-pill">{t("douyinAccounts.profileQuarantineBadge")}</span>
                        <strong>{profileQuarantineStateLabel(account.browser_health_alignment.profile_quarantine_state, t)}</strong>
                        <small className="muted block">
                          {account.browser_health_alignment.profile_quarantine_clean_profile_recommendation ?? t("douyinAccounts.profileQuarantineRecommendation")}
                        </small>
                      </div>
                    ) : null}
                    <details style={{ marginTop: "0.5rem" }}>
                      <summary><strong>{t("douyinAccounts.browserHealthAlignment")}</strong></summary>
                      <small className="muted block">{account.browser_health_alignment.operator_summary}</small>
                      {account.browser_health_alignment.operator_detail ? (
                        <small className="muted block">{account.browser_health_alignment.operator_detail}</small>
                      ) : null}
                      <small className="muted block">
                        {t("douyinAccounts.interactiveBrowserState")}: {alignmentInteractiveStateLabel(account, t)}
                      </small>
                      <small className="muted block">
                        {t("douyinAccounts.automatedBrowserValidation")}: {alignmentAutomatedStateLabel(account, t)}
                      </small>
                      {SHOW_LEGACY_DOUYIN_DEBUG_SURFACES ? (
                        <small className="muted block">
                          {t("douyinAccounts.detachedHttpState")}: {alignmentDetachedHttpStateLabel(account, t)}
                        </small>
                      ) : null}
                      <small className="muted block">
                        {t("douyinAccounts.validationPath")}: {alignmentPathLabel(account.browser_health_alignment.effective_validation_path, t)}
                      </small>
                      <small className="muted block">
                        {t("douyinAccounts.intakePath")}: {alignmentPathLabel(account.browser_health_alignment.expected_intake_path, t)}
                      </small>
                      <small className="muted block">
                        {t("douyinAccounts.pathAlignment")}: {account.browser_health_alignment.validation_intake_aligned ? t("common.yes") : t("common.no")}
                      </small>
                      {account.browser_health_alignment.stale_blocked_state_cleared ? (
                        <small className="muted block">{t("douyinAccounts.staleBlockedStateClearedHelp")}</small>
                      ) : null}
                      {account.browser_health_alignment.auto_reopen_attempted ? (
                        <small className="muted block">
                          {t("douyinAccounts.autoReopenAttempted")}: {t("common.yes")}
                          {account.browser_health_alignment.auto_reopen_status ? ` · ${autoReopenStatusLabel(account.browser_health_alignment.auto_reopen_status, t)}` : ""}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.auto_reopen_attempted ? (
                        <small className="muted block">
                          {t("douyinAccounts.autoReopenSucceeded")}: {account.browser_health_alignment.auto_reopen_succeeded ? t("common.yes") : t("common.no")}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.auto_reopen_attempted ? (
                        <small className="muted block">
                          {t("douyinAccounts.runtimeReattached")}: {account.browser_health_alignment.runtime_reattached ? t("common.yes") : t("common.no")}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.auto_reopen_attempted ? (
                        <small className="muted block">
                          {t("douyinAccounts.validationContinued")}: {account.browser_health_alignment.validation_continued_after_reopen ? t("common.yes") : t("common.no")}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.managed_runtime_status ? (
                        <small className="muted block">
                          {t("douyinAccounts.managedRuntimeStatus")}: {managedRuntimeStatusLabel(account.browser_health_alignment.managed_runtime_status, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.profile_conflict_status ? (
                        <small className="muted block">
                          {t("douyinAccounts.profileConflictStatus")}: {profileConflictStatusLabel(account.browser_health_alignment.profile_conflict_status, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.runtime_attach_status ? (
                        <small className="muted block">
                          {t("douyinAccounts.runtimeAttachStatus")}: {runtimeAttachStatusLabel(account.browser_health_alignment.runtime_attach_status, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.page_recovery_status ? (
                        <small className="muted block">
                          {t("douyinAccounts.pageRecoveryStatus")}: {pageRecoveryStatusLabel(account.browser_health_alignment.page_recovery_status, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.challenge_state ? (
                        <small className="muted block">
                          {t("douyinAccounts.challengeState")}: {challengeStateLabel(account.browser_health_alignment.challenge_state, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.challenge_category ? (
                        <small className="muted block">
                          {t("douyinAccounts.challengeCategory")}: {challengeCategoryLabel(account.browser_health_alignment.challenge_category, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.challenge_count > 0 ? (
                        <small className="muted block">
                          {t("douyinAccounts.challengeCount")}: {account.browser_health_alignment.challenge_count}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.challenge_cooldown_until ? (
                        <small className="muted block">
                          {t("douyinAccounts.challengeCooldownUntil")}: {formatDateTime(account.browser_health_alignment.challenge_cooldown_until)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.profile_quarantine_detected ? (
                        <small className="muted block">
                          {t("douyinAccounts.profileQuarantineState")}: {profileQuarantineStateLabel(account.browser_health_alignment.profile_quarantine_state, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.profile_quarantine_reason ? (
                        <small className="muted block">
                          {t("douyinAccounts.profileQuarantineReason")}: {profileQuarantineReasonLabel(account.browser_health_alignment.profile_quarantine_reason, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.profile_quarantine_recommended_next_action ? (
                        <small className="muted block">
                          {t("douyinAccounts.recommendedNextAction")}: {recommendedNextActionLabel(account.browser_health_alignment.profile_quarantine_recommended_next_action, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.challenge_recheck_started_at ? (
                        <small className="muted block">
                          {t("douyinAccounts.challengeRecheckStarted")}: {formatDateTime(account.browser_health_alignment.challenge_recheck_started_at)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.challenge_recheck_attempt_id ? (
                        <small className="muted block">
                          {t("douyinAccounts.challengeRecheckResolved")}: {account.browser_health_alignment.challenge_recheck_resolved ? t("common.yes") : t("common.no")}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.post_challenge_recheck_result ? (
                        <small className="muted block">
                          {t("douyinAccounts.postChallengeRecheckResult")}: {postChallengeRecheckResultLabel(account.browser_health_alignment.post_challenge_recheck_result, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.mark_challenge_solved_attempted ? (
                        <small className="muted block">
                          {t("douyinAccounts.sameProfileReusedDiagnostic")}: {account.browser_health_alignment.same_profile_reused ? t("common.yes") : t("common.no")}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.mark_challenge_solved_attempted ? (
                        <small className="muted block">
                          {t("douyinAccounts.runtimeReopenedForRecheck")}: {account.browser_health_alignment.runtime_reopened_for_recheck ? t("common.yes") : t("common.no")}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.mark_challenge_solved_attempted ? (
                        <small className="muted block">
                          {t("douyinAccounts.intakeReadyAfterRecheckDiagnostic")}: {account.browser_health_alignment.intake_ready_after_recheck ? t("common.yes") : t("common.no")}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.recommended_next_action ? (
                        <small className="muted block">
                          {t("douyinAccounts.recommendedNextAction")}: {recommendedNextActionLabel(account.browser_health_alignment.recommended_next_action, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.final_validation_category ? (
                        <small className="muted block">
                          {t("douyinAccounts.finalValidationCategory")}: {finalValidationCategoryLabel(account.browser_health_alignment.final_validation_category, t)}
                        </small>
                      ) : null}
                      {account.browser_health_alignment.last_browser_validation_status ? (
                        <small className="muted block">
                          {t("douyinAccounts.lastBrowserValidation")}: {account.browser_health_alignment.last_browser_validation_status}
                          {account.browser_health_alignment.last_browser_validation_at ? ` · ${formatDateTime(account.browser_health_alignment.last_browser_validation_at)}` : ""}
                        </small>
                      ) : null}
                    </details>
                    {currentPageByAccount[account.id] ? (
                      <div className="field-warning" style={{ marginTop: "0.5rem" }}>
                        <span className="status-pill">{t("douyinAccounts.currentPage")}</span>
                        <strong>{currentPageTypeLabel(currentPageByAccount[account.id].detected_page_type, t)}</strong>
                        <small className="muted block">{currentPageByAccount[account.id].operator_message}</small>
                        {currentPageByAccount[account.id].normalized_profile_url ? (
                          <small className="muted block">{t("douyinAccounts.currentPageProfile")}: {currentPageByAccount[account.id].normalized_profile_url}</small>
                        ) : null}
                        <small className="muted block">{t("douyinAccounts.currentPageVideos")}: {currentPageByAccount[account.id].video_link_count}</small>
                        {currentPageByAccount[account.id].page_url ? (
                          <small className="muted block">{currentPageByAccount[account.id].page_url}</small>
                        ) : null}
                      </div>
                    ) : null}
                  </td>
                  <td><StatusBadge label={healthLabel(account)} tone={healthTone(account)} /></td>
                  <td><StatusBadge label={accountStatusLabel(account, t)} tone={statusTone(account.status)} /></td>
                  <td>{connectionSourceLabel(account)}</td>
                  <td>
                    <StatusBadge label={browserContextLabel(account, t)} tone={browserContextTone(account)} />
                    {account.browser_context_last_used_at ? <small className="muted block">{formatDateTime(account.browser_context_last_used_at)}</small> : null}
                  </td>
                  <td>{account.session_cookie_present ? account.session_cookie_preview ?? "****" : t("common.no")}</td>
                  <td>{formatDateTime(account.last_validated_at)}</td>
                  <td>{formatDateTime(account.next_validation_due_at)}</td>
                  <td>
                    {(() => {
                      const currentPage = currentPageByAccount[account.id];
                      const quarantined = isProfileQuarantined(account);
                      const managedRuntimeActive = currentPage?.managed_runtime_status === "managed_runtime_active" || account.browser_health_alignment.managed_runtime_status === "managed_runtime_active";
                      const captureReady = Boolean(!quarantined && currentPage?.supported_capture && currentPage?.managed_runtime_status === "managed_runtime_active");
                      return (
                        <>
                          <button disabled={busyId === account.id || startingBrowserConnect} type="button" onClick={() => void openBrowserProfile(account)}>
                            {account.browser_context_status === "profile_saved" ? t("douyinAccounts.reopenBrowserProfile") : t("douyinAccounts.openBrowserProfile")}
                          </button>
                          <button disabled={busyId === account.id || !managedRuntimeActive} title={!managedRuntimeActive ? t("douyinAccounts.detectCurrentPageRuntimeMissing") : undefined} type="button" onClick={() => void detectCurrentPage(account)}>{t("douyinAccounts.detectCurrentPage")}</button>
                          <button disabled={busyId === account.id || !captureReady} title={quarantined ? t("douyinAccounts.profileQuarantineCaptureBlocked") : !captureReady ? t("douyinAccounts.captureCurrentPageDisabled") : undefined} type="button" onClick={() => void captureCurrentPage(account)}>{t("douyinAccounts.captureCurrentPage")}</button>
                        </>
                      );
                    })()}
                    {SHOW_LEGACY_DOUYIN_DEBUG_SURFACES ? (
                      <button disabled={busyId === account.id || isChallengeCooldownActive(account)} title={isChallengeCooldownActive(account) ? t("douyinAccounts.challengeCooldownActionBlocked") : undefined} type="button" onClick={() => void validate(account)}>{t("douyinAccounts.validate")}</button>
                    ) : null}
                    {isActionableChallenge(account) ? (
                      <button disabled={busyId === account.id} type="button" onClick={() => void markChallengeSolved(account)}>{t("douyinAccounts.markChallengeSolved")}</button>
                    ) : null}
                    {account.browser_health_alignment.challenge_state === "challenge_recently_solved_pending_recheck" ? (
                      <button disabled={busyId === account.id} type="button" onClick={() => void recheckChallenge(account)}>{t("douyinAccounts.recheckChallenge")}</button>
                    ) : null}
                    <button disabled={busyId === account.id || isChallengeCooldownActive(account) || isProfileQuarantined(account)} title={isProfileQuarantined(account) ? t("douyinAccounts.profileQuarantineUseInIntakeBlocked") : isChallengeCooldownActive(account) ? t("douyinAccounts.challengeCooldownActionBlocked") : undefined} type="button" onClick={() => useInIntake(account)}>{t("douyinAccounts.useInIntake")}</button>
                    <button disabled={resettingBrowserConnect} type="button" onClick={() => void resetBrowserConnectState()}>
                      {resettingBrowserConnect ? t("douyinAccounts.resetConnectRunning") : t("douyinAccounts.resetConnectState")}
                    </button>
                    <button className="danger" disabled={busyId === account.id} type="button" onClick={() => void deleteAccount(account)}>{t("douyinAccounts.deleteAccount")}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </PageShell>
    </OperatorStudioShell>
  );
}

function connectStatusLabel(status: string): string {
  return status.replaceAll("_", " ").toLowerCase();
}

function buildDeleteConfirm(account: DouyinAccount, accounts: DouyinAccount[], t: (key: string) => string): string {
  const lines = [
    t("douyinAccounts.deleteConfirmTitle"),
    "",
    `${t("douyinAccounts.account")}: ${account.display_name}`,
    t("douyinAccounts.deleteConfirmBody"),
    t("douyinAccounts.deleteConfirmSoftDelete"),
  ];
  if (account.is_default) {
    lines.push(t("douyinAccounts.deleteDefaultWarning"));
  }
  if (account.can_use_for_live_fetch) {
    lines.push(t("douyinAccounts.deleteUsableWarning"));
  }
  const usableCount = accounts.filter((item) => item.can_use_for_live_fetch).length;
  if (account.can_use_for_live_fetch && usableCount === 1) {
    lines.push(t("douyinAccounts.deleteOnlyUsableWarning"));
  }
  lines.push("", t("douyinAccounts.deleteConfirmPrompt"));
  return lines.join("\n");
}

function browserConnectPayload(browserForm: BrowserConnectFormState, account?: DouyinAccount) {
  return {
    account_connection_id: account?.id ?? null,
    display_name: account?.display_name ?? (browserForm.displayName.trim() || null),
    user_agent: account?.user_agent ?? (browserForm.userAgent.trim() || null),
    proxy_url: account?.proxy_url ?? (browserForm.proxyUrl.trim() || null),
    is_default: account?.is_default ?? browserForm.isDefault,
    timeout_seconds: 180
  };
}

function buildCurrentPageDetectionMessage(result: DouyinCurrentPageDetectionResponse, t: (key: string) => string): string {
  const pageType = currentPageTypeLabel(result.detected_page_type, t);
  const captureState = result.supported_capture ? t("douyinAccounts.currentPageCaptureReady") : result.recommended_action_label;
  return `${t("douyinAccounts.currentPageDetected")}: ${pageType} · ${captureState} · ${result.operator_message}`;
}

function buildCurrentPageCaptureMessage(
  result: { videos_discovered_count: number; videos_created_count: number; videos_updated_count: number; candidates_matched_count: number; next_suggested_route: string },
  t: (key: string) => string
): string {
  return `${t("douyinAccounts.currentPageCaptured")}: ${result.videos_discovered_count} ${t("douyinAccounts.currentPageVideos")}, ${result.videos_created_count} ${t("douyinAccounts.created")}, ${result.videos_updated_count} ${t("douyinAccounts.updated")}, ${result.candidates_matched_count} ${t("douyinAccounts.matchedCandidates")}. ${t("douyinAccounts.nextReviewRoute")}: ${result.next_suggested_route}`;
}

function currentPageTypeLabel(pageType: string, t: (key: string) => string): string {
  if (pageType === "login_page") return t("douyinAccounts.pageTypeLogin");
  if (pageType === "challenge_page") return t("douyinAccounts.pageTypeChallenge");
  if (pageType === "home_feed_page") return t("douyinAccounts.pageTypeHomeFeed");
  if (pageType === "profile_page") return t("douyinAccounts.pageTypeProfile");
  if (pageType === "profile_feed_page") return t("douyinAccounts.pageTypeProfileFeed");
  if (pageType === "video_detail_page") return t("douyinAccounts.pageTypeVideoDetail");
  if (pageType === "unsupported_page") return t("douyinAccounts.pageTypeUnsupported");
  return t("douyinAccounts.pageTypeUnknown");
}

function buildManualImportResultMessage(account: DouyinAccount, t: (key: string) => string): string {
  if (account.manual_import_preflight) {
    return `${t("douyinAccounts.saved")}: ${account.manual_import_preflight.summary}`;
  }
  if (account.can_use_for_live_fetch) {
    return `${t("douyinAccounts.saved")}: ${account.account_health_label}`;
  }
  const reason = account.last_error_message || account.last_validation_status || account.account_health_label;
  return `${t("douyinAccounts.saved")}: ${reason}`;
}

function manualImportPreflightTitle(account: DouyinAccount): string {
  if (!account.manual_import_preflight) return "Legacy manual import preflight";
  return account.manual_import_preflight.fetch_usable
    ? "Legacy manual import preflight passed"
    : `Legacy manual import preflight: ${account.manual_import_preflight.code}`;
}

function alignmentInteractiveStateLabel(account: DouyinAccount, t: (key: string) => string): string {
  const state = account.browser_health_alignment.interactive_browser_state;
  if (state === "live") return t("douyinAccounts.alignmentInteractiveLive");
  if (state === "saved") return t("douyinAccounts.alignmentInteractiveSaved");
  return t("douyinAccounts.alignmentInteractiveMissing");
}

function alignmentAutomatedStateLabel(account: DouyinAccount, t: (key: string) => string): string {
  const state = account.browser_health_alignment.automated_browser_validation_state;
  if (state === "passed") return t("douyinAccounts.alignmentAutomatedPassed");
  if (state === "challenge_cooldown_active") return t("douyinAccounts.alignmentAutomatedChallengeCooldownActive");
  if (state === "challenge_cooldown") return t("douyinAccounts.alignmentAutomatedChallengeCooldown");
  if (state === "challenge_repeat_limit_reached") return t("douyinAccounts.alignmentAutomatedChallengeRepeatLimit");
  if (state === "manual_verification_pending_recheck") return t("douyinAccounts.alignmentAutomatedPendingRecheck");
  if (state === "runtime_reopened") return t("douyinAccounts.alignmentAutomatedRuntimeReopened");
  if (state === "profile_reopen_failed") return t("douyinAccounts.alignmentAutomatedProfileReopenFailed");
  if (state === "profile_opened_outside_managed_runtime") return t("douyinAccounts.alignmentAutomatedExternalProfileOpen");
  if (state === "runtime_attach_failed") return t("douyinAccounts.alignmentAutomatedRuntimeAttachFailed");
  if (state === "runtime_missing") return t("douyinAccounts.alignmentAutomatedRuntimeMissing");
  if (state === "captcha_required") return t("douyinAccounts.alignmentAutomatedCaptchaRequired");
  if (state === "challenge_required") return t("douyinAccounts.alignmentAutomatedChallengeRequired");
  if (state === "manual_verification_required") return t("douyinAccounts.alignmentAutomatedManualVerificationRequired");
  if (state === "inconclusive") return t("douyinAccounts.alignmentAutomatedInconclusive");
  if (state === "retryable_blocked") return t("douyinAccounts.alignmentAutomatedRetryableBlocked");
  if (state === "blocked") return t("douyinAccounts.alignmentAutomatedBlocked");
  if (state === "login_required") return t("douyinAccounts.alignmentAutomatedLoginRequired");
  if (state === "unknown") return t("douyinAccounts.alignmentAutomatedUnknown");
  return t("douyinAccounts.alignmentAutomatedNotAvailable");
}

function alignmentDetachedHttpStateLabel(account: DouyinAccount, t: (key: string) => string): string {
  const state = account.browser_health_alignment.detached_http_state;
  if (state === "passed") return t("douyinAccounts.alignmentHttpPassed");
  if (state === "failed") return t("douyinAccounts.alignmentHttpFailed");
  if (state === "available") return t("douyinAccounts.alignmentHttpAvailable");
  return t("douyinAccounts.alignmentHttpNotApplicable");
}

function alignmentPathLabel(path: string, t: (key: string) => string): string {
  if (path === "browser_profile") return t("douyinAccounts.alignmentPathBrowserProfile");
  if (path === "detached_http") return t("douyinAccounts.alignmentPathDetachedHttp");
  return t("douyinAccounts.alignmentPathUnknown");
}

function autoReopenStatusLabel(status: string, t: (key: string) => string): string {
  if (status === "attempted") return t("douyinAccounts.autoReopenStatusAttempted");
  if (status === "runtime_missing_reopen_required") return t("douyinAccounts.autoReopenStatusRuntimeMissing");
  if (status === "browser_validation_runtime_reopened" || status === "reopen_success") return t("douyinAccounts.autoReopenStatusReopened");
  if (status === "failed" || status === "reopen_failed") return t("douyinAccounts.autoReopenStatusFailed");
  if (status === "reattach_failed") return t("douyinAccounts.autoReopenStatusReattachFailed");
  return status.replaceAll("_", " ");
}

function managedRuntimeStatusLabel(status: string, t: (key: string) => string): string {
  if (status === "managed_runtime_active") return t("douyinAccounts.managedRuntimeActive");
  if (status === "managed_runtime_missing") return t("douyinAccounts.managedRuntimeMissing");
  if (status === "managed_runtime_stale") return t("douyinAccounts.managedRuntimeStale");
  if (status === "managed_runtime_reopen_failed") return t("douyinAccounts.managedRuntimeReopenFailed");
  if (status === "profile_opened_outside_managed_runtime") return t("douyinAccounts.managedRuntimeExternalProfileOpen");
  return status.replaceAll("_", " ");
}

function profileConflictStatusLabel(status: string, t: (key: string) => string): string {
  if (status === "profile_opened_outside_managed_runtime") return t("douyinAccounts.profileConflictExternalOpen");
  if (status === "profile_locked_by_existing_process") return t("douyinAccounts.profileConflictProfileLocked");
  return status.replaceAll("_", " ");
}

function runtimeAttachStatusLabel(status: string, t: (key: string) => string): string {
  if (status === "managed_runtime_active") return t("douyinAccounts.runtimeAttachManagedActive");
  if (status === "live_runtime_attached") return t("douyinAccounts.runtimeAttachLiveAttached");
  if (status === "runtime_missing_reopen_required") return t("douyinAccounts.runtimeAttachMissingReopenRequired");
  if (status === "runtime_attach_failed") return t("douyinAccounts.runtimeAttachFailed");
  return status.replaceAll("_", " ");
}

function pageRecoveryStatusLabel(status: string, t: (key: string) => string): string {
  if (status === "live_runtime_attached") return t("douyinAccounts.pageRecoveryExistingPageUsable");
  if (status === "page_reacquired_same_context") return t("douyinAccounts.pageRecoveryPageReacquired");
  if (status === "page_created_same_context") return t("douyinAccounts.pageRecoveryNewPageCreated");
  if (status === "live_context_page_reacquired") return t("douyinAccounts.pageRecoveryPageReacquired");
  if (status === "live_context_new_page_created") return t("douyinAccounts.pageRecoveryNewPageCreated");
  if (status === "first_page_closed_but_recovered") return t("douyinAccounts.pageRecoveryFirstPageRecovered");
  if (status === "first_page_closed_but_context_alive") return t("douyinAccounts.pageRecoveryFirstPageContextAlive");
  return status.replaceAll("_", " ");
}

function finalValidationCategoryLabel(category: string, t: (key: string) => string): string {
  if (category === "browser_validation_success") return t("douyinAccounts.finalCategorySuccess");
  if (category === "browser_validation_blocked") return t("douyinAccounts.finalCategoryBlocked");
  if (category === "browser_validation_login_required") return t("douyinAccounts.finalCategoryLoginRequired");
  if (category === "browser_validation_inconclusive") return t("douyinAccounts.finalCategoryInconclusive");
  if (category === "browser_validation_captcha_required") return t("douyinAccounts.finalCategoryCaptchaRequired");
  if (category === "browser_validation_challenge_required") return t("douyinAccounts.finalCategoryChallengeRequired");
  if (category === "browser_validation_manual_verification_required") return t("douyinAccounts.finalCategoryManualVerificationRequired");
  if (category === "runtime_attach_failed") return t("douyinAccounts.finalCategoryRuntimeAttachFailed");
  if (category === "profile_reopen_failed") return t("douyinAccounts.finalCategoryProfileReopenFailed");
  if (category === "browser_validation_runtime_unavailable") return t("douyinAccounts.finalCategoryRuntimeUnavailable");
  return category.replaceAll("_", " ");
}

function challengeCategoryLabel(category: string, t: (key: string) => string): string {
  if (category === "captcha_required") return t("douyinAccounts.challengeCategoryCaptcha");
  if (category === "challenge_required") return t("douyinAccounts.challengeCategoryChallenge");
  if (category === "manual_verification_required") return t("douyinAccounts.challengeCategoryManualVerification");
  return category.replaceAll("_", " ");
}

function challengeStateLabel(state: string | null, t: (key: string) => string): string {
  if (!state) return t("common.unknown");
  if (state === "challenge_waiting_for_manual_verification") return t("douyinAccounts.challengeStateWaiting");
  if (state === "challenge_recently_solved_pending_recheck") return t("douyinAccounts.challengeStatePendingRecheck");
  if (state === "challenge_cooldown") return t("douyinAccounts.challengeStateCooldown");
  if (state === "challenge_cooldown_active") return t("douyinAccounts.challengeStateCooldownActive");
  if (state === "challenge_repeat_limit_reached") return t("douyinAccounts.challengeStateRepeatLimit");
  return state.replaceAll("_", " ");
}

function isActionableChallenge(account: DouyinAccount): boolean {
  const state = account.browser_health_alignment.challenge_state;
  return state === "challenge_waiting_for_manual_verification" || state === "challenge_cooldown" || state === "challenge_cooldown_active" || state === "challenge_repeat_limit_reached";
}

function isChallengeCooldownActive(account: DouyinAccount): boolean {
  const state = account.browser_health_alignment.challenge_state;
  if (state === "challenge_cooldown_active") return true;
  if (state !== "challenge_cooldown" && state !== "challenge_repeat_limit_reached") return false;
  const cooldownUntil = account.browser_health_alignment.challenge_cooldown_until;
  if (!cooldownUntil) return false;
  const cooldownTime = new Date(cooldownUntil).getTime();
  return !Number.isNaN(cooldownTime) && cooldownTime > Date.now();
}

function postChallengeRecheckResultLabel(result: string | null, t: (key: string) => string): string {
  if (!result) return t("common.unknown");
  if (result === "challenge_postcheck_success") return t("douyinAccounts.postcheckSuccess");
  if (result === "challenge_postcheck_still_required") return t("douyinAccounts.postcheckStillRequired");
  if (result === "challenge_postcheck_login_required") return t("douyinAccounts.postcheckLoginRequired");
  if (result === "challenge_postcheck_cooldown_active") return t("douyinAccounts.postcheckCooldownActive");
  if (result === "challenge_postcheck_profile_mismatch") return t("douyinAccounts.postcheckProfileMismatch");
  if (result === "challenge_postcheck_runtime_unavailable") return t("douyinAccounts.postcheckRuntimeUnavailable");
  if (result === "challenge_postcheck_blocked") return t("douyinAccounts.postcheckBlocked");
  if (result === "challenge_postcheck_inconclusive") return t("douyinAccounts.postcheckInconclusive");
  if (result === "challenge_postcheck_failed_unknown") return t("douyinAccounts.postcheckFailedUnknown");
  return result.replaceAll("_", " ");
}

function profileQuarantineStateLabel(state: string, t: (key: string) => string): string {
  if (state === "active_preferred") return t("douyinAccounts.profileQuarantineStateActivePreferred");
  if (state === "active_warning") return t("douyinAccounts.profileQuarantineStateActiveWarning");
  if (state === "quarantine_candidate") return t("douyinAccounts.profileQuarantineStateCandidate");
  if (state === "quarantined") return t("douyinAccounts.profileQuarantineStateQuarantined");
  if (state === "quarantined_recoverable") return t("douyinAccounts.profileQuarantineStateRecoverable");
  if (state === "quarantined_replaced") return t("douyinAccounts.profileQuarantineStateReplaced");
  return state.replaceAll("_", " ");
}

function profileQuarantineReasonLabel(reason: string, t: (key: string) => string): string {
  if (reason === "challenge_repeat_limit_reached") return t("douyinAccounts.profileQuarantineReasonRepeatLimit");
  if (reason === "challenge_count_threshold_reached") return t("douyinAccounts.profileQuarantineReasonChallengeCount");
  if (reason === "browser_context_blocked_threshold_reached") return t("douyinAccounts.profileQuarantineReasonBlockedCount");
  return reason.replaceAll("_", " ");
}

function recommendedNextActionLabel(action: string, t: (key: string) => string): string {
  if (action === "create_clean_managed_browser_profile") return t("douyinAccounts.nextActionCreateCleanProfile");
  if (action === "solve_captcha_in_browser_profile") return t("douyinAccounts.nextActionSolveCaptcha");
  if (action === "complete_challenge_in_browser_profile") return t("douyinAccounts.nextActionCompleteChallenge");
  if (action === "complete_manual_verification_in_browser_profile") return t("douyinAccounts.nextActionManualVerification");
  if (action === "retry_browser_validation_after_manual_solve") return t("douyinAccounts.nextActionRetryAfterManualSolve");
  if (action === "wait_then_complete_challenge_in_browser_profile") return t("douyinAccounts.nextActionWaitThenCompleteChallenge");
  if (action === "wait_or_mark_challenge_solved_after_manual_completion") return t("douyinAccounts.nextActionWaitOrMarkChallengeSolved");
  if (action === "running_browser_validation_after_manual_solve") return t("douyinAccounts.nextActionRunningPostcheck");
  if (action === "complete_challenge_in_browser_profile_then_mark_solved") return t("douyinAccounts.nextActionCompleteThenMarkSolved");
  if (action === "reconnect_saved_browser_profile_login") return t("douyinAccounts.nextActionReconnectLogin");
  if (action === "reopen_saved_browser_profile_then_retry_recheck") return t("douyinAccounts.nextActionReopenThenRetryRecheck");
  if (action === "review_browser_profile_block_before_retry") return t("douyinAccounts.nextActionReviewBlockBeforeRetry");
  if (action === "retry_browser_validation_after_manual_review") return t("douyinAccounts.nextActionRetryAfterManualReview");
  return action.replaceAll("_", " ");
}

function connectTone(status: string): "good" | "warn" | "danger" | "muted" {
  if (status === "COMPLETED") return "good";
  if (status === "FAILED") return "danger";
  if (status === "CANCELLED") return "warn";
  return "warn";
}

function connectPrimaryMessage(session: DouyinBrowserConnectSession, t: (key: string) => string): string {
  if (session.status === "COMPLETED") return t("douyinAccounts.browserCompleted");
  if (session.outcome === "timed_out") return t("douyinAccounts.browserTimedOut");
  if (session.error_code === "validation_retry_ready") return t("douyinAccounts.phaseValidationRetryReady");
  if (session.status === "FAILED") return `${t("douyinAccounts.browserFailed")}: ${session.error_code ?? t("common.unknown")}`;
  if (session.status === "CANCELLED") return t("douyinAccounts.browserCancelled");
  return `${t("douyinAccounts.connectStatus")}: ${connectStatusLabel(session.status)}`;
}

function connectSecondaryMessage(session: DouyinBrowserConnectSession, t: (key: string) => string): string {
  if (session.phase === "login_detected") {
    return t("douyinAccounts.loginDetectedHelp");
  }
  if (session.phase === "stabilizing_auth") {
    return t("douyinAccounts.stabilizingAuthHelp");
  }
  if (session.phase === "validation_retry_ready") {
    return t("douyinAccounts.validationRetryReadyHelp");
  }
  if (
    session.status === "FAILED"
    && ["post_login_blocked", "browser_context_blocked_response"].includes(session.error_code ?? "")
  ) {
    return t("douyinAccounts.postLoginBlockedRetryHelp");
  }
  if (
    session.status === "FAILED"
    && session.error_code === "validation_failed"
    && (session.error_message ?? "").includes("browser_context_blocked")
  ) {
    return t("douyinAccounts.postLoginBlockedRetryHelp");
  }
  if (
    session.status === "FAILED"
    && ["browser_runtime_unavailable", "dependency_missing", "browser_binary_missing", "runtime_launch_failed"].includes(session.error_code ?? "")
  ) {
    return t("douyinAccounts.browserRuntimeUnavailableHelp");
  }
  if (
    session.status === "FAILED"
    && ["launch_failed", "runtime_probe_failed", "runtime_not_supported"].includes(session.error_code ?? "")
  ) {
    return t("douyinAccounts.browserRuntimeUnavailableHelp");
  }
  if (session.status === "FAILED" && session.error_code === "browser_closed") {
    return t("douyinAccounts.browserClosedHelp");
  }
  if (session.outcome === "timed_out") {
    return t("douyinAccounts.browserTimeoutHelp");
  }
  return session.error_message ?? session.last_error ?? session.instructions;
}

function connectPhaseLabel(phase: DouyinBrowserConnectSession["phase"], t: (key: string) => string): string {
  if (phase === "starting_browser") return t("douyinAccounts.phaseStarting");
  if (phase === "waiting_for_login") return t("douyinAccounts.phaseWaitingLogin");
  if (phase === "login_detected") return t("douyinAccounts.phaseLoginDetected");
  if (phase === "stabilizing_auth") return t("douyinAccounts.phaseStabilizingAuth");
  if (phase === "capturing_session") return t("douyinAccounts.phaseCapturing");
  if (phase === "validating_session") return t("douyinAccounts.phaseValidating");
  if (phase === "validation_retry_ready") return t("douyinAccounts.phaseValidationRetryReady");
  if (phase === "completed") return t("douyinAccounts.phaseCompleted");
  if (phase === "cancelled") return t("douyinAccounts.phaseCancelled");
  return t("douyinAccounts.phaseFailed");
}

function connectionSourceLabel(account: DouyinAccount): string {
  const source = account.metadata_json?.connection_source;
  if (source === "browser_assisted") return "Browser";
  if (source === "manual_import") return SHOW_LEGACY_DOUYIN_DEBUG_SURFACES ? "Manual (legacy)" : "Browser required";
  return account.browser_context_status === "profile_saved" || account.browser_context_available ? "Browser" : "Browser required";
}

function browserContextLabel(account: DouyinAccount, t: (key: string) => string): string {
  if (account.browser_context_available) return t("douyinAccounts.browserContextLive");
  if (account.browser_context_status === "profile_saved") return t("douyinAccounts.browserProfileSaved");
  if (account.browser_context_status === "stale") return t("douyinAccounts.browserContextStale");
  if (account.browser_context_status === "invalid" || account.browser_context_status === "closed") return t("douyinAccounts.browserContextClosed");
  return t("douyinAccounts.browserContextNone");
}

function browserContextTone(account: DouyinAccount): "good" | "warn" | "danger" | "muted" {
  if (account.browser_context_available) return "good";
  if (account.browser_context_status === "profile_saved") return "warn";
  if (account.browser_context_status === "stale") return "warn";
  if (account.browser_context_status === "invalid") return "danger";
  return "muted";
}

function healthLabel(account: DouyinAccount): string {
  return account.account_health_label || account.health_status;
}

function isProfileQuarantined(account: DouyinAccount): boolean {
  return account.browser_health_alignment.profile_quarantine_blocks_primary_flow;
}

function accountStatusLabel(account: DouyinAccount, t: (key: string) => string): string {
  if (isProfileQuarantined(account)) return t("douyinAccounts.statusProfileQuarantined");
  const challengeState = account.browser_health_alignment.challenge_state;
  if (challengeState === "challenge_cooldown_active") return t("douyinAccounts.statusChallengeCooldownActive");
  if (challengeState === "challenge_recently_solved_pending_recheck") return t("douyinAccounts.statusChallengePendingRecheck");
  if (challengeState === "challenge_repeat_limit_reached") return t("douyinAccounts.statusChallengeRepeatLimit");
  if (challengeState === "challenge_cooldown") return t("douyinAccounts.statusChallengeCooldown");
  if (challengeState === "challenge_waiting_for_manual_verification") return t("douyinAccounts.statusChallengeManualVerification");
  if (account.status === "ACTIVE") return t("douyinAccounts.statusActive");
  if (account.status === "INVALID") return t("douyinAccounts.statusInvalid");
  if (account.status === "EXPIRED") return t("douyinAccounts.statusExpired");
  if (account.status === "DISABLED") return t("douyinAccounts.statusDisabled");
  if (account.status === "BLOCKED") return t("douyinAccounts.statusBlocked");
  return account.status;
}

function healthTone(account: DouyinAccount): "good" | "warn" | "danger" | "muted" {
  if (account.health_status === "HEALTHY") return "good";
  if (account.health_status === "STALE" || account.health_status === "EXPIRING_SOON") return "warn";
  if (account.warning_level === "BLOCK") return "danger";
  return "muted";
}

function statusTone(status: string): "good" | "warn" | "danger" | "muted" {
  if (status === "ACTIVE") return "good";
  if (status === "INVALID" || status === "BLOCKED") return "danger";
  if (status === "EXPIRED" || status === "DISABLED") return "warn";
  return "muted";
}

function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
