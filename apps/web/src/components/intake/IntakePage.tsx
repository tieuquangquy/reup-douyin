          "use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  compareIntakeRuns,
  createIntakeSavedPreset,
  deleteIntakeSavedPreset,
  discoverIntakeCandidates,
  fetchDouyinAccounts,
  fetchFilterPresets,
  fetchIntakeBootstrap,
  fetchIntakeRun,
  fetchIntakeRuns,
  runIntakeReadyCheck,
  startDouyinBrowserConnect,
  updateIntakeSavedPreset
  ,
  validateDouyinAccount
} from "../../lib/api";
import {
  DEFAULT_INTAKE_FORM,
  buildIntakeDiscoverRequest,
  formatPresetName,
  hasIntakeErrors,
  parseRecentIntakeSetup,
  validateIntakeForm
} from "../../lib/intakeState";
import { useT } from "../../lib/i18n";
import type {
  IntakeDiscoverResponse,
  IntakeFormValues,
  IntakeLatestSuccessShortcutResponse,
  IntakeRecentProfileResponse,
  IntakeReadyCheckResponse,
  IntakeRunCompareResponse,
  IntakeRunDetailResponse,
  IntakeRunSummaryResponse,
  IntakeSavedPresetResponse,
  IntakeValidationErrors,
  RecentIntakeSetup
} from "../../types/intake";
import type { DouyinAccount } from "../../types/douyin-accounts";
import type { FilterPreset } from "../../types/review-board";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PageShell } from "../app-shell/PageShell";

const RECENT_INTAKE_STORAGE_KEY = "reup-douyin:last-intake-setup";
const SHOW_LEGACY_DOUYIN_DEBUG_SURFACES = process.env.NEXT_PUBLIC_DOUYIN_ENABLE_LEGACY_DEBUG_SURFACES === "true";

export function IntakePage() {
  const t = useT();
  const [values, setValues] = useState<IntakeFormValues>(DEFAULT_INTAKE_FORM);
  const [errors, setErrors] = useState<IntakeValidationErrors>({});
  const [presets, setPresets] = useState<FilterPreset[]>([]);
  const [accounts, setAccounts] = useState<DouyinAccount[]>([]);
  const [presetError, setPresetError] = useState<string | null>(null);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [recentSetup, setRecentSetup] = useState<RecentIntakeSetup | null>(null);
  const [savedPresets, setSavedPresets] = useState<IntakeSavedPresetResponse[]>([]);
  const [recentProfiles, setRecentProfiles] = useState<IntakeRecentProfileResponse[]>([]);
  const [latestSuccessShortcuts, setLatestSuccessShortcuts] = useState<IntakeLatestSuccessShortcutResponse[]>([]);
  const [savingPreset, setSavingPreset] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<IntakeDiscoverResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [runHistory, setRunHistory] = useState<IntakeRunSummaryResponse[]>([]);
  const [runHistoryLoading, setRunHistoryLoading] = useState(false);
  const [runHistoryError, setRunHistoryError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [selectedRunDetail, setSelectedRunDetail] = useState<IntakeRunDetailResponse | null>(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [runDetailError, setRunDetailError] = useState<string | null>(null);
  const [compareLeftRunId, setCompareLeftRunId] = useState<string>("");
  const [compareRightRunId, setCompareRightRunId] = useState<string>("");
  const [compareResult, setCompareResult] = useState<IntakeRunCompareResponse | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [readyCheck, setReadyCheck] = useState<IntakeReadyCheckResponse | null>(null);
  const [readyCheckLoading, setReadyCheckLoading] = useState(false);
  const [readyCheckError, setReadyCheckError] = useState<string | null>(null);
  const [readyCheckActionBusy, setReadyCheckActionBusy] = useState(false);
  const [readyCheckActionMessage, setReadyCheckActionMessage] = useState<string | null>(null);

  async function loadAccounts(preferredAccountId?: string | null) {
    const items = await fetchDouyinAccounts();
    setAccounts(items);

    const selectedFromPreferred = preferredAccountId
      ? items.find((item) => item.id === preferredAccountId)
      : undefined;
    const selectedFallback = items.find((item) => item.is_default && item.can_use_for_live_fetch) ?? items.find((item) => item.can_use_for_live_fetch);
    const selected = selectedFromPreferred ?? selectedFallback;

    if (selected) {
      setValues((current) => current.douyinAccountConnectionId ? current : { ...current, douyinAccountConnectionId: selected.id });
    }
  }

  useEffect(() => {
    setRecentSetup(parseRecentIntakeSetup(window.localStorage.getItem(RECENT_INTAKE_STORAGE_KEY)));
  }, []);

  useEffect(() => {
    let active = true;
    const queryAccountConnectionId = new URLSearchParams(window.location.search).get("douyinAccountConnectionId");

    loadAccounts(queryAccountConnectionId)
      .then(() => {
        if (!active) return;
      })
      .catch((err) => {
        if (!active) return;
        setAccountError(err instanceof Error ? err.message : t("intake.accountLoadError"));
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    fetchFilterPresets()
      .then((items) => {
        if (!active) return;
        setPresets(items);
        if (items.length > 0 && !items.some((item) => item.name === DEFAULT_INTAKE_FORM.presetName)) {
          setValues((current) => ({ ...current, presetName: items[0].name }));
        }
      })
      .catch((err) => {
        if (!active) return;
        setPresetError(err instanceof Error ? err.message : t("intake.presetLoadError"));
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    fetchIntakeBootstrap()
      .then((payload) => {
        if (!active) return;
        setSavedPresets(payload.saved_presets);
        setRecentProfiles(payload.recent_profiles);
        setLatestSuccessShortcuts(payload.latest_success_shortcuts);
      })
      .catch(() => {
        if (!active) return;
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setRunHistoryLoading(true);
    setRunHistoryError(null);
    fetchIntakeRuns(12)
      .then((items) => {
        if (!active) return;
        setRunHistory(items);
        if (items.length === 0) return;
        setSelectedRunId((current) => current || items[0].crawl_session_id);
        setCompareLeftRunId((current) => current || items[0].crawl_session_id);
        setCompareRightRunId((current) => {
          if (current) return current;
          if (items.length > 1) return items[1].crawl_session_id;
          return items[0].crawl_session_id;
        });
      })
      .catch((err) => {
        if (!active) return;
        setRunHistoryError(err instanceof Error ? err.message : t("intake.runHistoryLoadError"));
      })
      .finally(() => {
        if (!active) return;
        setRunHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [t]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRunDetail(null);
      setRunDetailError(null);
      return;
    }
    let active = true;
    setRunDetailLoading(true);
    setRunDetailError(null);
    fetchIntakeRun(selectedRunId)
      .then((payload) => {
        if (!active) return;
        setSelectedRunDetail(payload);
      })
      .catch((err) => {
        if (!active) return;
        setSelectedRunDetail(null);
        setRunDetailError(err instanceof Error ? err.message : t("intake.runDetailLoadError"));
      })
      .finally(() => {
        if (!active) return;
        setRunDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedRunId, t]);

  useEffect(() => {
    if (!compareLeftRunId || !compareRightRunId || compareLeftRunId === compareRightRunId) {
      setCompareResult(null);
      setCompareError(null);
      return;
    }
    let active = true;
    setCompareLoading(true);
    setCompareError(null);
    compareIntakeRuns(compareLeftRunId, compareRightRunId)
      .then((payload) => {
        if (!active) return;
        setCompareResult(payload);
      })
      .catch((err) => {
        if (!active) return;
        setCompareResult(null);
        setCompareError(err instanceof Error ? err.message : t("intake.runCompareLoadError"));
      })
      .finally(() => {
        if (!active) return;
        setCompareLoading(false);
      });
    return () => {
      active = false;
    };
  }, [compareLeftRunId, compareRightRunId, t]);

  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.name === values.presetName) ?? null,
    [presets, values.presetName]
  );
  const forceLiveBlocked = values.forceLiveRefresh && !selectedAccountCanUse(values, accounts);
  const accountWarning = selectedAccountHealthWarning(values, accounts, t);

  function updateField(field: keyof IntakeFormValues, value: IntakeFormValues[keyof IntakeFormValues]) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined, form: undefined }));
  }

  async function runDiscovery() {
    const nextErrors = validateIntakeForm(values);
    setErrors(nextErrors);
    setSubmitError(null);
    setResult(null);
    if (hasIntakeErrors(nextErrors)) return;
    if (values.forceLiveRefresh && !selectedAccountCanUse(values, accounts)) {
      setErrors({ form: t("intake.accountRequiredForLive") });
      return;
    }

    setSubmitting(true);
    try {
      const payload = buildIntakeDiscoverRequest(values);
      const nextResult = await discoverIntakeCandidates(payload);
      setResult(nextResult);
      const nextRecent = {
        profileUrl: values.profileUrl.trim(),
        presetName: values.presetName,
        discoveredAt: new Date().toISOString()
      };
      window.localStorage.setItem(RECENT_INTAKE_STORAGE_KEY, JSON.stringify(nextRecent));
      setRecentSetup(nextRecent);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : t("intake.discoverError"));
    } finally {
      setSubmitting(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runDiscovery();
  }

  async function executeReadyCheck() {
    setReadyCheckLoading(true);
    setReadyCheckError(null);
    setReadyCheckActionMessage(null);
    try {
      const summary = await runIntakeReadyCheck({
        profile_url: values.profileUrl.trim() || null,
        douyin_account_connection_id: values.douyinAccountConnectionId || null
      });
      setReadyCheck(summary);
    } catch (err) {
      setReadyCheckError(err instanceof Error ? err.message : t("intake.readyCheckError"));
    } finally {
      setReadyCheckLoading(false);
    }
  }

  async function reopenReadyCheckProfile() {
    if (!readyCheck?.resolved_account_id) return;
    setReadyCheckActionBusy(true);
    setReadyCheckError(null);
    setReadyCheckActionMessage(null);
    try {
      await startDouyinBrowserConnect({ account_connection_id: readyCheck.resolved_account_id });
      setReadyCheckActionMessage(t("intake.readyCheckReopenDone"));
      await loadAccounts(readyCheck.resolved_account_id);
    } catch (err) {
      setReadyCheckError(err instanceof Error ? err.message : t("intake.readyCheckReopenError"));
    } finally {
      setReadyCheckActionBusy(false);
    }
  }

  async function validateReadyCheckAccount() {
    if (!readyCheck?.resolved_account_id) return;
    setReadyCheckActionBusy(true);
    setReadyCheckError(null);
    setReadyCheckActionMessage(null);
    try {
      await validateDouyinAccount(readyCheck.resolved_account_id);
      await loadAccounts(readyCheck.resolved_account_id);
      setReadyCheckActionMessage(t("intake.readyCheckValidateDone"));
      const summary = await runIntakeReadyCheck({
        profile_url: values.profileUrl.trim() || null,
        douyin_account_connection_id: readyCheck.resolved_account_id
      });
      setReadyCheck(summary);
    } catch (err) {
      setReadyCheckError(err instanceof Error ? err.message : t("intake.readyCheckValidateError"));
    } finally {
      setReadyCheckActionBusy(false);
    }
  }

  function reset() {
    setValues(DEFAULT_INTAKE_FORM);
    setErrors({});
    setResult(null);
    setSubmitError(null);
    setReadyCheck(null);
    setReadyCheckError(null);
    setReadyCheckActionMessage(null);
  }

  function useRecentSetup() {
    if (!recentSetup) return;
    setValues((current) => ({
      ...current,
      profileUrl: recentSetup.profileUrl,
      presetName: recentSetup.presetName
    }));
    setErrors({});
    setResult(null);
    setSubmitError(null);
  }

  function applySavedPreset(preset: IntakeSavedPresetResponse) {
    const cfg = preset.filter_config as Partial<Record<string, unknown>>;
    const nextValues: IntakeFormValues = {
      ...values,
      profileUrl: preset.profile_url,
      presetName: preset.preset_name ?? "",
      forceLiveRefresh: preset.force_live_refresh,
      douyinAccountConnectionId: preset.douyin_account_connection_id ?? "",
      dateFrom: typeof cfg.start_date === "string" ? cfg.start_date.slice(0, 10) : "",
      dateTo: typeof cfg.end_date === "string" ? cfg.end_date.slice(0, 10) : "",
      minViews: typeof cfg.min_views === "number" ? String(cfg.min_views) : "",
      maxViews: typeof cfg.max_views === "number" ? String(cfg.max_views) : "",
      minLikes: typeof cfg.min_likes === "number" ? String(cfg.min_likes) : "",
      maxLikes: typeof cfg.max_likes === "number" ? String(cfg.max_likes) : "",
      minComments: typeof cfg.min_comments === "number" ? String(cfg.min_comments) : "",
      maxComments: typeof cfg.max_comments === "number" ? String(cfg.max_comments) : "",
      minShares: typeof cfg.min_shares === "number" ? String(cfg.min_shares) : "",
      maxShares: typeof cfg.max_shares === "number" ? String(cfg.max_shares) : "",
      minDurationSeconds: typeof cfg.min_duration_seconds === "number" ? String(cfg.min_duration_seconds) : "",
      maxDurationSeconds: typeof cfg.max_duration_seconds === "number" ? String(cfg.max_duration_seconds) : "",
      minEngagementRate: typeof cfg.min_engagement_rate === "number" ? String(Math.round(cfg.min_engagement_rate * 10000) / 100) : "",
      maxEngagementRate: typeof cfg.max_engagement_rate === "number" ? String(Math.round(cfg.max_engagement_rate * 10000) / 100) : "",
      hasSpeech: cfg.has_speech === true ? "yes" : cfg.has_speech === false ? "no" : "any",
      maxTextDensity:
        cfg.max_text_density === "low" || cfg.max_text_density === "medium" || cfg.max_text_density === "high"
          ? cfg.max_text_density
          : "",
      excludeHeavyWatermark: cfg.exclude_heavy_watermark !== false,
      excludeHighProcessingComplexity: cfg.exclude_high_processing_complexity !== false,
      excludeHighCopyrightRisk: cfg.exclude_high_copyright_risk !== false
    };
    setValues(nextValues);
    setErrors({});
    setResult(null);
    setSubmitError(null);
  }

  async function saveCurrentAsPreset() {
    const trimmedProfileUrl = values.profileUrl.trim();
    if (!trimmedProfileUrl) {
      setErrors((current) => ({ ...current, profileUrl: "Profile URL is required." }));
      return;
    }
    const presetName = window.prompt("Saved preset name", "");
    if (!presetName || !presetName.trim()) return;

    setSavingPreset(true);
    try {
      const payload = buildIntakeDiscoverRequest(values);
      const created = await createIntakeSavedPreset({
        name: presetName.trim(),
        profile_url: trimmedProfileUrl,
        preset_name: payload.preset_name,
        filter_config: payload.filter_config,
        force_live_refresh: payload.force_live_refresh,
        douyin_account_connection_id: payload.douyin_account_connection_id,
        notes: null
      });
      setSavedPresets((current) => [created, ...current]);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to save intake preset");
    } finally {
      setSavingPreset(false);
    }
  }

  async function renameSavedPreset(preset: IntakeSavedPresetResponse) {
    const nextName = window.prompt("Rename preset", preset.name);
    if (!nextName || !nextName.trim() || nextName.trim() === preset.name) return;
    try {
      const updated = await updateIntakeSavedPreset(preset.id, { name: nextName.trim() });
      setSavedPresets((current) => current.map((item) => (item.id === preset.id ? updated : item)));
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to rename intake preset");
    }
  }

  async function removeSavedPreset(preset: IntakeSavedPresetResponse) {
    if (!window.confirm(`Delete saved preset "${preset.name}"?`)) return;
    try {
      await deleteIntakeSavedPreset(preset.id);
      setSavedPresets((current) => current.filter((item) => item.id !== preset.id));
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to delete intake preset");
    }
  }

  function applyRecentProfile(profile: IntakeRecentProfileResponse) {
    setValues((current) => ({ ...current, profileUrl: profile.profile_url }));
    setErrors({});
    setResult(null);
    setSubmitError(null);
  }

  function applyLatestShortcut(shortcut: IntakeLatestSuccessShortcutResponse) {
    if (!shortcut.submitted_profile_url) return;
    setValues((current) => ({ ...current, profileUrl: shortcut.submitted_profile_url ?? current.profileUrl }));
    setErrors({});
    setResult(null);
    setSubmitError(null);
  }

  function applyRunToForm(run: IntakeRunSummaryResponse | IntakeRunDetailResponse) {
    if (!run.submitted_profile_url) return;
    setValues((current) => ({
      ...current,
      profileUrl: run.submitted_profile_url ?? current.profileUrl,
      forceLiveRefresh: run.fetch_mode?.includes("forced") ?? current.forceLiveRefresh
    }));
    setErrors({});
    setResult(null);
    setSubmitError(null);
  }

  return (
    <OperatorStudioShell
      actions={<a className="operator-inline-link" href="/">{t("common.home")}</a>}
      description={t("intake.description")}
      title={t("intake.title")}
    >
      <PageShell description={t("intake.pageDescription")} title={t("intake.workflowTitle")}>
        <div className="intake-kicker" aria-label={t("intake.flowTitle")}>
          <span>{t("intake.stepPaste")}</span>
          <span>{t("intake.stepTune")}</span>
          <span>{t("intake.stepDiscover")}</span>
          <span>{t("intake.stepReview")}</span>
        </div>

        <div className="intake-layout">
          <form className="intake-form operator-panel" onSubmit={(event) => void submit(event)}>
            <section className="intake-section">
              <div className="operator-panel-heading">
                <div>
                  <h2>{t("intake.sourceSection")}</h2>
                  <p>{t("intake.sourceHelp")}</p>
                </div>
              </div>
              <label className="field intake-profile-field">
                <span>{t("intake.profileUrl")}</span>
                <input
                  aria-invalid={Boolean(errors.profileUrl)}
                  onChange={(event) => updateField("profileUrl", event.target.value)}
                  placeholder="https://www.douyin.com/user/MS4wLjABAAAA..."
                  type="url"
                  value={values.profileUrl}
                />
                {errors.profileUrl ? <small className="field-error">{errors.profileUrl}</small> : <small>{t("intake.profileUrlHelp")}</small>}
              </label>
              <CheckboxField
                checked={values.forceLiveRefresh}
                description={t("intake.forceLiveRefreshHelp")}
                label={t("intake.forceLiveRefresh")}
                onChange={(checked) => updateField("forceLiveRefresh", checked)}
              />
            </section>

            <section className="intake-section">
              <div className="operator-panel-heading">
                <div>
                  <h2>{t("intake.douyinAccount")}</h2>
                  <p>{t("intake.douyinAccountHelp")}</p>
                </div>
                <a className="operator-inline-link" href="/accounts/douyin">{t("intake.manageDouyinAccounts")}</a>
              </div>
              <SelectField
                label={t("intake.accountSelector")}
                onChange={(value) => updateField("douyinAccountConnectionId", value)}
                value={values.douyinAccountConnectionId}
                options={[
                  { label: t("intake.useDefaultAccount"), value: "" },
                  ...accounts.map((account) => ({
                    disabled: !account.can_use_for_live_fetch,
                    label: `${account.display_name} · ${account.status}${account.is_default ? ` · ${t("intake.defaultAccount")}` : ""}`,
                    value: account.id
                  }))
                ]}
              />
              {accountError ? <p className="field-warning">{accountError}</p> : null}
              {accounts.length === 0 ? <p className="field-warning">{t("intake.noDouyinAccounts")}</p> : null}
              {accounts.length > 0 && !accounts.some((account) => account.can_use_for_live_fetch) ? <p className="field-warning">{t("intake.noActiveDouyinAccounts")}</p> : null}
              {accountWarning ? <p className="field-warning">{accountWarning}</p> : null}
              {accounts.some((account) => account.browser_context_available || account.browser_context_status === "profile_saved") ? <p className="field-warning good">{t("intake.liveBrowserContextAvailable")}</p> : null}
              {accounts.length > 0 ? (
                <div className="intake-account-health-list">
                  {accounts.map((account) => (
                    <small key={account.id}>
                      {account.display_name}: {account.health_status}{account.can_use_for_live_fetch ? "" : ` - ${t("common.needsWork")}`}
                    </small>
                  ))}
                </div>
              ) : null}
              <div className="intake-actions">
                <button disabled={readyCheckLoading || readyCheckActionBusy} onClick={() => void executeReadyCheck()} type="button">
                  {readyCheckLoading ? t("intake.readyCheckRunning") : t("intake.readyCheck")}
                </button>
                {readyCheck ? (
                  <button disabled={readyCheckLoading || readyCheckActionBusy} onClick={() => void executeReadyCheck()} type="button">
                    {t("intake.readyCheckRetry")}
                  </button>
                ) : null}
                {readyCheck?.safe_to_run_intake_now ? (
                  <button
                    disabled={submitting || readyCheckLoading || readyCheckActionBusy}
                    onClick={() => void runDiscovery()}
                    type="button"
                  >
                    {t("intake.readyCheckRunNow")}
                  </button>
                ) : null}
                {readyCheck?.recommended_action === "revalidate_account" && readyCheck.resolved_account_id ? (
                  <button disabled={readyCheckLoading || readyCheckActionBusy} onClick={() => void validateReadyCheckAccount()} type="button">
                    {t("intake.readyCheckValidate")}
                  </button>
                ) : null}
                {readyCheck && readyCheck.browser_reopen_needed && readyCheck.browser_reopen_result !== "reopened" && readyCheck.resolved_account_id ? (
                  <button disabled={readyCheckLoading || readyCheckActionBusy} onClick={() => void reopenReadyCheckProfile()} type="button">
                    {t("intake.readyCheckReopen")}
                  </button>
                ) : null}
                {readyCheck ? <a className="operator-inline-link" href="/accounts/douyin">{t("intake.manageDouyinAccounts")}</a> : null}
              </div>
              {readyCheckError ? <p className="field-warning">{readyCheckError}</p> : null}
              {readyCheckActionMessage ? <p className="field-warning good">{readyCheckActionMessage}</p> : null}
              {readyCheck ? <ReadyCheckSummaryCard result={readyCheck} /> : null}
            </section>

            <section className="intake-section">
              <div className="operator-panel-heading">
                <div>
                  <h2>{t("intake.preset")}</h2>
                  <p>{t("intake.presetHelp")}</p>
                </div>
              </div>
              <div className="intake-preset-grid" role="radiogroup" aria-label={t("intake.preset")}>
                <PresetCard
                  active={values.presetName === ""}
                  description={t("intake.noPresetDesc")}
                  label={t("intake.noPreset")}
                  onSelect={() => updateField("presetName", "")}
                />
                {presets.map((preset) => (
                  <PresetCard
                    active={values.presetName === preset.name}
                    description={preset.description}
                    key={preset.name}
                    label={formatPresetName(preset.name)}
                    onSelect={() => updateField("presetName", preset.name)}
                  />
                ))}
              </div>
              {selectedPreset?.use_when ? <p className="intake-preset-use">{selectedPreset.use_when}</p> : null}
              <p className="muted">{t("intake.builtInPresetHint")}</p>
              {presetError ? <p className="field-warning">{t("intake.presetFallback")}: {presetError}</p> : null}
            </section>

            <section className="intake-section">
              <div className="operator-panel-heading">
                <div>
                  <h2>{t("intake.filtersSection")}</h2>
                  <p>{t("intake.filtersHelp")}</p>
                </div>
              </div>
              <div className="intake-filter-groups">
                <div className="intake-filter-group">
                  <h3>{t("intake.timeRange")}</h3>
                  <div className="intake-grid">
                    <label className="field">
                      <span>{t("intake.fromDate")}</span>
                      <input
                        aria-invalid={Boolean(errors.dateFrom)}
                        onChange={(event) => updateField("dateFrom", event.target.value)}
                        type="date"
                        value={values.dateFrom}
                      />
                      {errors.dateFrom ? <small className="field-error">{errors.dateFrom}</small> : null}
                    </label>
                    <label className="field">
                      <span>{t("intake.toDate")}</span>
                      <input
                        aria-invalid={Boolean(errors.dateTo)}
                        onChange={(event) => updateField("dateTo", event.target.value)}
                        type="date"
                        value={values.dateTo}
                      />
                      {errors.dateTo ? <small className="field-error">{errors.dateTo}</small> : null}
                    </label>
                  </div>
                </div>

                <div className="intake-filter-group">
                  <h3>{t("intake.viewsRange")}</h3>
                  <div className="intake-grid">
                    <NumberField
                      error={errors.minViews}
                      label={t("intake.minViews")}
                      onChange={(value) => updateField("minViews", value)}
                      value={values.minViews}
                    />
                    <NumberField
                      error={errors.maxViews}
                      label={t("intake.maxViews")}
                      onChange={(value) => updateField("maxViews", value)}
                      value={values.maxViews}
                    />
                  </div>
                </div>

                <div className="intake-filter-group">
                  <h3>{t("intake.likesRange")}</h3>
                  <div className="intake-grid">
                    <NumberField
                      error={errors.minLikes}
                      label={t("intake.minLikes")}
                      onChange={(value) => updateField("minLikes", value)}
                      value={values.minLikes}
                    />
                    <NumberField
                      error={errors.maxLikes}
                      label={t("intake.maxLikes")}
                      onChange={(value) => updateField("maxLikes", value)}
                      value={values.maxLikes}
                    />
                  </div>
                </div>

                <div className="intake-filter-group">
                  <h3>{t("intake.audienceSignals")}</h3>
                  <p>{t("intake.audienceSignalsHelp")}</p>
                  <div className="intake-grid">
                    <NumberField
                      error={errors.minComments}
                      label={t("intake.minComments")}
                      onChange={(value) => updateField("minComments", value)}
                      value={values.minComments}
                    />
                    <NumberField
                      error={errors.maxComments}
                      label={t("intake.maxComments")}
                      onChange={(value) => updateField("maxComments", value)}
                      value={values.maxComments}
                    />
                    <NumberField
                      error={errors.minShares}
                      label={t("intake.minShares")}
                      onChange={(value) => updateField("minShares", value)}
                      value={values.minShares}
                    />
                    <NumberField
                      error={errors.maxShares}
                      label={t("intake.maxShares")}
                      onChange={(value) => updateField("maxShares", value)}
                      value={values.maxShares}
                    />
                    <NumberField
                      error={errors.minEngagementRate}
                      label={t("intake.minEngagementRate")}
                      onChange={(value) => updateField("minEngagementRate", value)}
                      value={values.minEngagementRate}
                    />
                    <NumberField
                      error={errors.maxEngagementRate}
                      label={t("intake.maxEngagementRate")}
                      onChange={(value) => updateField("maxEngagementRate", value)}
                      value={values.maxEngagementRate}
                    />
                  </div>
                </div>

                <div className="intake-filter-group">
                  <h3>{t("intake.processingFit")}</h3>
                  <p>{t("intake.processingFitHelp")}</p>
                  <div className="intake-grid">
                    <NumberField
                      error={errors.minDurationSeconds}
                      label={t("intake.minDuration")}
                      onChange={(value) => updateField("minDurationSeconds", value)}
                      value={values.minDurationSeconds}
                    />
                    <NumberField
                      error={errors.maxDurationSeconds}
                      label={t("intake.maxDuration")}
                      onChange={(value) => updateField("maxDurationSeconds", value)}
                      value={values.maxDurationSeconds}
                    />
                    <SelectField
                      label={t("intake.hasSpeech")}
                      onChange={(value) => updateField("hasSpeech", value as IntakeFormValues["hasSpeech"])}
                      value={values.hasSpeech}
                      options={[
                        { label: t("intake.any"), value: "any" },
                        { label: t("intake.hasSpeechYes"), value: "yes" },
                        { label: t("intake.hasSpeechNo"), value: "no" }
                      ]}
                    />
                    <SelectField
                      label={t("intake.maxTextDensity")}
                      onChange={(value) => updateField("maxTextDensity", value as IntakeFormValues["maxTextDensity"])}
                      value={values.maxTextDensity}
                      options={[
                        { label: t("intake.any"), value: "" },
                        { label: t("intake.textLow"), value: "low" },
                        { label: t("intake.textMedium"), value: "medium" },
                        { label: t("intake.textHigh"), value: "high" }
                      ]}
                    />
                  </div>
                  <div className="intake-checkbox-grid">
                    <CheckboxField
                      checked={values.excludeHeavyWatermark}
                      description={t("intake.excludeHeavyWatermarkHelp")}
                      label={t("intake.excludeHeavyWatermark")}
                      onChange={(checked) => updateField("excludeHeavyWatermark", checked)}
                    />
                    <CheckboxField
                      checked={values.excludeHighProcessingComplexity}
                      description={t("intake.excludeHighComplexityHelp")}
                      label={t("intake.excludeHighComplexity")}
                      onChange={(checked) => updateField("excludeHighProcessingComplexity", checked)}
                    />
                    <CheckboxField
                      checked={values.excludeHighCopyrightRisk}
                      description={t("intake.excludeHighCopyrightRiskHelp")}
                      label={t("intake.excludeHighCopyrightRisk")}
                      onChange={(checked) => updateField("excludeHighCopyrightRisk", checked)}
                    />
                  </div>
                </div>
              </div>
            </section>

            {errors.form ? <div className="inline-error compact">{errors.form}</div> : null}
            <div className="intake-actions">
              <button className="primary intake-primary-action" disabled={submitting || forceLiveBlocked} type="submit">
                {submitting ? t("intake.discovering") : t("intake.discover")}
              </button>
              <button disabled={submitting || savingPreset} onClick={() => void saveCurrentAsPreset()} type="button">
                {savingPreset ? t("intake.savingPreset") : t("intake.saveAsPreset")}
              </button>
              <button disabled={submitting} onClick={reset} type="button">{t("intake.reset")}</button>
              {result ? <a className="operator-inline-link" href={result.next_suggested_route}>{t("intake.openFreshReviewBoard")}</a> : null}
            </div>
          </form>

          <aside className="intake-side">
            <StatusPanel error={submitError} result={result} submitting={submitting} />
            <RunHistoryPanel
              loading={runHistoryLoading}
              error={runHistoryError}
              runs={runHistory}
              selectedRunId={selectedRunId}
              onSelectRun={setSelectedRunId}
              onApplyRun={applyRunToForm}
            />
            <RunTroubleshootingPanel
              loading={runDetailLoading}
              error={runDetailError}
              run={selectedRunDetail}
              onApplyRun={applyRunToForm}
            />
            <RunComparePanel
              runs={runHistory}
              leftRunId={compareLeftRunId}
              rightRunId={compareRightRunId}
              onChangeLeft={setCompareLeftRunId}
              onChangeRight={setCompareRightRunId}
              loading={compareLoading}
              error={compareError}
              result={compareResult}
            />
            <SavedPresetPanel
              presets={savedPresets}
              onApply={applySavedPreset}
              onRename={(preset) => void renameSavedPreset(preset)}
              onDelete={(preset) => void removeSavedPreset(preset)}
            />
            <RecentProfilePanel profiles={recentProfiles} onApply={applyRecentProfile} />
            <LatestSuccessPanel shortcuts={latestSuccessShortcuts} onApply={applyLatestShortcut} />
            <RecentSetupPanel recentSetup={recentSetup} onUseRecent={useRecentSetup} />
            <GuidancePanel />
          </aside>
        </div>
      </PageShell>
    </OperatorStudioShell>
  );
}

function PresetCard({
  active,
  label,
  description,
  onSelect
}: {
  active: boolean;
  label: string;
  description: string;
  onSelect: () => void;
}) {
  return (
    <button
      aria-checked={active}
      className={`intake-preset-card${active ? " active" : ""}`}
      onClick={onSelect}
      role="radio"
      type="button"
    >
      <strong>{label}</strong>
      <small>{description}</small>
    </button>
  );
}

function NumberField({
  label,
  value,
  error,
  onChange
}: {
  label: string;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        aria-invalid={Boolean(error)}
        min="0"
        onChange={(event) => onChange(event.target.value)}
        type="number"
        value={value}
      />
      {error ? <small className="field-error">{error}</small> : null}
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: Array<{ label: string; value: string; disabled?: boolean }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select onChange={(event) => onChange(event.target.value)} value={value}>
        {options.map((option) => (
          <option disabled={option.disabled} key={option.value || "any"} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}

function CheckboxField({
  checked,
  label,
  description,
  onChange
}: {
  checked: boolean;
  label: string;
  description: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="intake-checkbox-field">
      <input checked={checked} onChange={(event) => onChange(event.target.checked)} type="checkbox" />
      <span>
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
    </label>
  );
}

function ReadyCheckSummaryCard({ result }: { result: IntakeReadyCheckResponse }) {
  const t = useT();
  const statusTone = result.readiness_status === "NOT_READY" || result.readiness_status === "CHALLENGE_BLOCKED" || result.readiness_status === "PROFILE_QUARANTINED" ? "danger" : result.readiness_status === "FALLBACK_READY" ? "warn" : "good";
  return (
    <div className={`intake-status ${statusTone}`}>
      <span className="intake-status-eyebrow">{t("intake.readyCheckSummaryTitle")}</span>
      <h2>{readyCheckStatusLabel(result.readiness_status, t)}</h2>
      <p>{result.summary_message}</p>
      <div className="metadata-list">
        <div>
          <dt>{t("intake.readyCheckRecommendedAccount")}</dt>
          <dd>{result.resolved_account_label ?? t("common.unknown")}</dd>
        </div>
        <div>
          <dt>{t("intake.readyCheckBrowserProfile")}</dt>
          <dd>{result.browser_profile_status ?? t("common.unknown")}</dd>
        </div>
        {SHOW_LEGACY_DOUYIN_DEBUG_SURFACES || result.intended_fetch_path !== "http_html" ? (
          <div>
            <dt>{t("intake.fetchExecutionPath")}</dt>
            <dd>{result.intended_fetch_path ? fetchExecutionPathLabel(result.intended_fetch_path, t) : t("common.unknown")}</dd>
          </div>
        ) : null}
        <div>
          <dt>{t("intake.readyCheckNextAction")}</dt>
          <dd>{result.recommended_action_label}</dd>
        </div>
        {result.account_health ? (
          <div>
            <dt>{t("intake.fetchReadiness")}</dt>
            <dd>{result.account_health}</dd>
          </div>
        ) : null}
        <div>
          <dt>{t("intake.browserReopen")}</dt>
          <dd>
            {result.browser_reopen_needed
              ? result.browser_reopen_attempted
                ? result.browser_reopen_result ?? t("intake.browserReopenAttempted")
                : t("intake.readyCheckNeedsReopen")
              : t("intake.readyCheckNoReopenNeeded")}
          </dd>
        </div>
        {result.preflight_cached ? (
          <div>
            <dt>{t("intake.preflightCache")}</dt>
            <dd>{t("intake.preflightCacheReused")}</dd>
          </div>
        ) : null}
        {result.watchdog_result ? (
          <div>
            <dt>{t("intake.browserWatchdog")}</dt>
            <dd>{watchdogLabel(result.watchdog_result, t)}</dd>
          </div>
        ) : null}
        {result.challenge_state ? (
          <div>
            <dt>{t("intake.challengeState")}</dt>
            <dd>{challengeStateLabel(result.challenge_state, t)}</dd>
          </div>
        ) : null}
        {result.challenge_category ? (
          <div>
            <dt>{t("intake.challengeCategory")}</dt>
            <dd>{challengeCategoryLabel(result.challenge_category, t)}</dd>
          </div>
        ) : null}
        {typeof result.challenge_count === "number" ? (
          <div>
            <dt>{t("intake.challengeCount")}</dt>
            <dd>{result.challenge_count}</dd>
          </div>
        ) : null}
        {result.challenge_cooldown_until ? (
          <div>
            <dt>{t("intake.challengeCooldownUntil")}</dt>
            <dd>{formatIntakeDateTime(result.challenge_cooldown_until)}</dd>
          </div>
        ) : null}
        {result.profile_quarantine_detected ? (
          <div>
            <dt>{t("intake.profileQuarantineState")}</dt>
            <dd>{profileQuarantineStateLabel(result.profile_quarantine_state, t)}</dd>
          </div>
        ) : null}
        {result.profile_quarantine_reason ? (
          <div>
            <dt>{t("intake.profileQuarantineReason")}</dt>
            <dd>{profileQuarantineReasonLabel(result.profile_quarantine_reason, t)}</dd>
          </div>
        ) : null}
      </div>
      {result.account_fallback_notice ? <p className="muted">{result.account_fallback_notice}</p> : null}
      {result.profile_quarantine_clean_profile_recommendation ? <p className="field-warning">{result.profile_quarantine_clean_profile_recommendation}</p> : null}
      {result.preflight_failure_message && (result.readiness_status === "NOT_READY" || result.readiness_status === "CHALLENGE_BLOCKED" || result.readiness_status === "PROFILE_QUARANTINED") ? <p className="muted">{result.preflight_failure_message}</p> : null}
      {result.readiness_status === "PROFILE_QUARANTINED" ? (
        <p className="field-warning">
          {t("intake.profileQuarantineHint")} <a className="operator-inline-link" href="/accounts/douyin">{t("intake.profileQuarantineCreateCleanProfile")}</a>
        </p>
      ) : null}
      {result.readiness_status === "CHALLENGE_BLOCKED" && result.resolved_account_id ? (
        <p className="field-warning">
          {t("intake.challengeResumeHint")} <a className="operator-inline-link" href={`/accounts/douyin?accountId=${result.resolved_account_id}`}>{t("intake.challengeOpenAccount")}</a>
        </p>
      ) : null}
    </div>
  );
}

function StatusPanel({
  error,
  result,
  submitting
}: {
  error: string | null;
  result: IntakeDiscoverResponse | null;
  submitting: boolean;
}) {
  const t = useT();
  if (submitting) {
    return (
      <section className="operator-panel intake-status">
        <span className="intake-status-eyebrow">{t("intake.status")}</span>
        <h2>{t("intake.statusRunning")}</h2>
        <p>{t("intake.statusRunningBody")}</p>
      </section>
    );
  }
  if (error) {
    return (
      <section className="operator-panel intake-status danger">
        <span className="intake-status-eyebrow">{t("intake.status")}</span>
        <h2>{t("intake.statusError")}</h2>
        <p>{error}</p>
        <p className="muted">{t("intake.errorRecovery")}</p>
      </section>
    );
  }
  if (result) {
    const fetchStageIssue = isFetchStageIssue(result.fetch_stage_code);
    const noCandidates = result.candidates_matched_count === 0;
    const emptyExistingData = result.fetch_mode === "existing_data" && result.videos_discovered_count === 0;
    const statusTitle = fetchStageIssue
      ? fetchStageTitle(result.fetch_stage_code, t)
      : noCandidates
        ? t("intake.statusNoCandidates")
        : t("intake.statusSuccess");
    const statusBody = fetchStageIssue
      ? result.fetch_stage_message ?? t("intake.fetchStageIssueBody")
      : noCandidates
        ? t("intake.noCandidatesBody")
        : t("intake.successBody");
    return (
      <section className={`operator-panel intake-status${fetchStageIssue || noCandidates ? " warn" : " good"}`}>
        <span className="intake-status-eyebrow">{t("intake.status")}</span>
        <h2>{statusTitle}</h2>
        <p>{statusBody}</p>
        <div className="intake-result-grid">
          <SummaryStat label={t("intake.profileAccepted")} value={result.normalized_profile_identifier ?? result.source_profile_id} />
          <SummaryStat label={t("intake.fetchMode")} value={fetchModeLabel(result.fetch_mode, t)} />
          {result.fetch_execution_path && (SHOW_LEGACY_DOUYIN_DEBUG_SURFACES || result.fetch_execution_path !== "http_html") ? (
            <SummaryStat label={t("intake.fetchExecutionPath")} value={fetchExecutionPathLabel(result.fetch_execution_path, t)} />
          ) : null}
          {result.strategy_policy && (SHOW_LEGACY_DOUYIN_DEBUG_SURFACES || !result.strategy_policy.startsWith("http_")) ? (
            <SummaryStat label={t("intake.fetchStrategyPolicy")} value={fetchStrategyPolicyLabel(result.strategy_policy, t)} />
          ) : null}
          {result.preflight_ran ? (
            <SummaryStat label={t("intake.preflight")} value={preflightLabel(result.preflight_result, t)} />
          ) : null}
          {result.preflight_cached ? (
            <SummaryStat label={t("intake.preflightCache")} value={t("intake.preflightCacheReused")} />
          ) : null}
          <SummaryStat label={t("intake.videosDiscovered")} value={String(result.videos_discovered_count)} />
          <SummaryStat label={t("intake.videosNormalized")} value={String(result.videos_normalized_count)} />
          <SummaryStat label={t("intake.videosPersisted")} value={String(result.videos_persisted_count)} />
          <SummaryStat label={t("intake.candidatesMatched")} value={String(result.candidates_matched_count)} />
          <SummaryStat label={t("intake.candidatesRejected")} value={String(result.candidates_rejected_count)} />
        </div>
        {result.fetch_stage_code ? (
          <div className="metadata-list">
            <div>
              <dt>{t("intake.fetchStage")}</dt>
              <dd>{result.fetch_stage ?? t("common.unknown")}</dd>
            </div>
            <div>
              <dt>{t("intake.fetchStageCode")}</dt>
              <dd>{result.fetch_stage_code}</dd>
            </div>
            <div>
              <dt>{t("intake.parserStrategy")}</dt>
              <dd>{result.parser_strategy ?? t("common.unknown")}</dd>
            </div>
            {SHOW_LEGACY_DOUYIN_DEBUG_SURFACES && result.fallback_from_execution_path ? (
              <div>
                <dt>{t("intake.fallbackFrom")}</dt>
                <dd>{fetchExecutionPathLabel(result.fallback_from_execution_path, t)}</dd>
              </div>
            ) : null}
            {SHOW_LEGACY_DOUYIN_DEBUG_SURFACES && result.http_fallback_attempted ? (
              <div>
                <dt>{t("intake.httpFallback")}</dt>
                <dd>{result.http_fallback_reason ?? t("intake.httpFallbackUsed")}</dd>
              </div>
            ) : null}
            {result.fetch_readiness_category ? (
              <div>
                <dt>{t("intake.fetchReadiness")}</dt>
                <dd>{fetchReadinessLabel(result.fetch_readiness_category, t)}</dd>
              </div>
            ) : null}
            {result.browser_reopen_attempted ? (
              <div>
                <dt>{t("intake.browserReopen")}</dt>
                <dd>{result.browser_reopen_result ?? t("intake.browserReopenAttempted")}</dd>
              </div>
            ) : null}
            {result.watchdog_result ? (
              <div>
                <dt>{t("intake.browserWatchdog")}</dt>
                <dd>{watchdogLabel(result.watchdog_result, t)}</dd>
              </div>
            ) : null}
            {result.watchdog_status ? (
              <div>
                <dt>{t("intake.runtimeState")}</dt>
                <dd>{result.watchdog_status}{result.watchdog_reason ? `: ${result.watchdog_reason}` : ""}</dd>
              </div>
            ) : null}
            {result.runtime_reconciled ? (
              <div>
                <dt>{t("intake.runtimeReconciled")}</dt>
                <dd>{t("common.yes")}</dd>
              </div>
            ) : null}
          </div>
        ) : null}
        {result.resolved_douyin_account_connection_id ? (
          <div className="metadata-list">
            <div>
              <dt>{t("intake.accountSelectionMode")}</dt>
              <dd>{result.douyin_account_selection_mode ?? t("common.unknown")}</dd>
            </div>
            <div>
              <dt>{t("intake.selectedAccount")}</dt>
              <dd>{result.selected_douyin_account_connection_id ?? t("intake.defaultAccount")}</dd>
            </div>
            <div>
              <dt>{t("intake.resolvedAccount")}</dt>
              <dd>{result.resolved_douyin_account_connection_id}</dd>
            </div>
          </div>
        ) : null}
        {result.douyin_account_fallback_notice ? <p className="field-warning">{result.douyin_account_fallback_notice}</p> : null}
        {emptyExistingData ? <p className="field-warning">{t("intake.emptyExistingWarning")}</p> : null}
        {result.warning ? <p className="muted">{result.warning}</p> : null}
        <a className="operator-inline-link intake-status-cta" href={result.next_suggested_route}>{t("intake.openFreshReviewBoard")}</a>
      </section>
    );
  }
  return (
    <section className="operator-panel intake-status">
      <span className="intake-status-eyebrow">{t("intake.status")}</span>
      <h2>{t("intake.statusIdle")}</h2>
      <p>{t("intake.statusIdleBody")}</p>
    </section>
  );
}

function fetchModeLabel(fetchMode: string, t: (key: string) => string): string {
  if (fetchMode === "existing_data") return t("intake.fetchModeExisting");
  if (fetchMode === "forced_live_fetch" || fetchMode === "forced_live_fetch_using_account") return t("intake.fetchModeForced");
  if (fetchMode === "live_fetch" || fetchMode === "live_fetch_using_account") return t("intake.fetchModeLive");
  return fetchMode;
}

function readyCheckStatusLabel(status: string, t: (key: string) => string): string {
  if (status === "READY") return t("intake.readyCheckStatusReady");
  if (status === "READY_AFTER_REOPEN") return t("intake.readyCheckStatusReadyAfterReopen");
  if (status === "FALLBACK_READY") return t("intake.readyCheckStatusFallbackReady");
  if (status === "CHALLENGE_BLOCKED") return t("intake.readyCheckStatusChallengeBlocked");
  if (status === "PROFILE_QUARANTINED") return t("intake.readyCheckStatusProfileQuarantined");
  if (status === "NOT_READY") return t("intake.readyCheckStatusNotReady");
  return status;
}

function fetchExecutionPathLabel(path: string, t: (key: string) => string): string {
  if (path === "browser_profile") return t("intake.fetchExecutionBrowserProfile");
  if (path === "http_then_browser_fallback") return t("intake.fetchExecutionHttpThenBrowser");
  if (path === "http_html") return t("intake.fetchExecutionHttpHtml");
  return path;
}

function fetchStrategyPolicyLabel(policy: string, t: (key: string) => string): string {
  if (policy === "browser_primary") return t("intake.fetchStrategyBrowserPrimary");
  if (policy === "http_primary_with_browser_fallback") return t("intake.fetchStrategyHttpPrimary");
  if (policy === "http_only") return t("intake.fetchStrategyHttpOnly");
  return policy;
}

function preflightLabel(result: string | null, t: (key: string) => string): string {
  if (result === "passed") return t("intake.preflightPassed");
  if (result === "failed") return t("intake.preflightFailed");
  return result ?? t("common.unknown");
}

function fetchReadinessLabel(category: string, t: (key: string) => string): string {
  if (category === "fetch_ready_browser_profile") return t("intake.fetchReadyBrowserProfile");
  if (category === "fetch_ready_after_browser_reopen") return t("intake.fetchReadyAfterBrowserReopen");
  if (category === "fetch_ready_http_fallback") return t("intake.fetchReadyHttpFallback");
  if (category === "fetch_blocked_by_browser_challenge") return t("intake.fetchBlockedByBrowserChallenge");
  if (category === "fetch_blocked_by_profile_quarantine") return t("intake.fetchBlockedByProfileQuarantine");
  if (category === "fetch_not_ready") return t("intake.fetchNotReady");
  return category;
}

function profileQuarantineStateLabel(state: string, t: (key: string) => string): string {
  if (state === "active_preferred") return t("intake.profileQuarantineStateActivePreferred");
  if (state === "active_warning") return t("intake.profileQuarantineStateActiveWarning");
  if (state === "quarantine_candidate") return t("intake.profileQuarantineStateCandidate");
  if (state === "quarantined") return t("intake.profileQuarantineStateQuarantined");
  if (state === "quarantined_recoverable") return t("intake.profileQuarantineStateRecoverable");
  if (state === "quarantined_replaced") return t("intake.profileQuarantineStateReplaced");
  return state.replaceAll("_", " ");
}

function profileQuarantineReasonLabel(reason: string, t: (key: string) => string): string {
  if (reason === "challenge_repeat_limit_reached") return t("intake.profileQuarantineReasonRepeatLimit");
  if (reason === "challenge_count_threshold_reached") return t("intake.profileQuarantineReasonChallengeCount");
  if (reason === "browser_context_blocked_threshold_reached") return t("intake.profileQuarantineReasonBlockedCount");
  return reason.replaceAll("_", " ");
}

function challengeStateLabel(state: string, t: (key: string) => string): string {
  if (state === "challenge_waiting_for_manual_verification") return t("intake.challengeStateWaiting");
  if (state === "challenge_recently_solved_pending_recheck") return t("intake.challengeStatePendingRecheck");
  if (state === "challenge_cooldown") return t("intake.challengeStateCooldown");
  if (state === "challenge_repeat_limit_reached") return t("intake.challengeStateRepeatLimit");
  return state.replaceAll("_", " ");
}

function challengeCategoryLabel(category: string, t: (key: string) => string): string {
  if (category === "captcha_required") return t("intake.challengeCategoryCaptcha");
  if (category === "challenge_required") return t("intake.challengeCategoryChallenge");
  if (category === "manual_verification_required") return t("intake.challengeCategoryManualVerification");
  return category.replaceAll("_", " ");
}

function formatIntakeDateTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function watchdogLabel(result: string, t: (key: string) => string): string {
  if (result === "healthy") return t("intake.watchdogHealthy");
  if (result === "missing") return t("intake.watchdogMissing");
  if (result === "stale") return t("intake.watchdogStale");
  if (result === "invalid") return t("intake.watchdogInvalid");
  if (result === "closed") return t("intake.watchdogClosed");
  return result;
}

function isFetchStageIssue(fetchStageCode: string | null): boolean {
  return Boolean(fetchStageCode && !["success", "filter_zero_candidates"].includes(fetchStageCode));
}

function fetchStageTitle(fetchStageCode: string | null, t: (key: string) => string): string {
  switch (fetchStageCode) {
    case "blocked_response":
      return t("intake.statusFetchBlocked");
    case "login_required":
      return t("intake.statusLoginRequired");
    case "parse_failed":
      return t("intake.statusParseFailed");
    case "parse_zero_videos":
      return t("intake.statusZeroVideos");
    case "true_zero_videos":
      return t("intake.statusTrueZeroVideos");
    default:
      return t("intake.statusFetchIssue");
  }
}

function selectedAccountCanUse(values: IntakeFormValues, accounts: DouyinAccount[]): boolean {
  if (!values.douyinAccountConnectionId) {
    return accounts.some((account) => account.is_default && account.can_use_for_live_fetch) || accounts.some((account) => account.can_use_for_live_fetch);
  }
  return accounts.some((account) => account.id === values.douyinAccountConnectionId && account.can_use_for_live_fetch);
}

function selectedAccountHealthWarning(
  values: IntakeFormValues,
  accounts: DouyinAccount[],
  t: (key: string) => string
): string | null {
  const account = values.douyinAccountConnectionId
    ? accounts.find((item) => item.id === values.douyinAccountConnectionId)
    : accounts.find((item) => item.is_default);
  if (!account) return null;
  if (account.browser_health_alignment.profile_quarantine_blocks_primary_flow) {
    return `${account.display_name}: ${t("intake.readyCheckStatusProfileQuarantined")}. ${t("intake.profileQuarantineCreateCleanProfile")}`;
  }
  if (account.health_status === "STALE" || account.health_status === "EXPIRING_SOON") {
    return `${account.display_name}: ${account.health_status}. ${t("intake.revalidateSoon")}`;
  }
  if (!account.can_use_for_live_fetch) {
    return `${account.display_name}: ${account.health_status}. ${t("intake.connectOrValidateAnother")}`;
  }
  return null;
}

function RecentSetupPanel({
  recentSetup,
  onUseRecent
}: {
  recentSetup: RecentIntakeSetup | null;
  onUseRecent: () => void;
}) {
  const t = useT();
  if (!recentSetup) {
    return (
      <section className="operator-panel intake-recent">
        <div className="operator-panel-heading">
          <div>
            <h2>{t("intake.recentTitle")}</h2>
            <p>{t("intake.noRecentSetup")}</p>
          </div>
        </div>
      </section>
    );
  }
  return (
    <section className="operator-panel intake-recent">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("intake.recentTitle")}</h2>
          <p>{t("intake.recentDescription")}</p>
        </div>
      </div>
      <div className="intake-recent-card">
        <strong>{formatPresetName(recentSetup.presetName)}</strong>
        <small>{recentSetup.profileUrl}</small>
      </div>
      <button type="button" onClick={onUseRecent}>{t("intake.useRecent")}</button>
    </section>
  );
}

function SavedPresetPanel({
  presets,
  onApply,
  onRename,
  onDelete
}: {
  presets: IntakeSavedPresetResponse[];
  onApply: (preset: IntakeSavedPresetResponse) => void;
  onRename: (preset: IntakeSavedPresetResponse) => void;
  onDelete: (preset: IntakeSavedPresetResponse) => void;
}) {
  const t = useT();
  return (
    <section className="operator-panel intake-recent">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("intake.savedPresetsTitle")}</h2>
          <p>{t("intake.savedPresetsDescription")}</p>
        </div>
      </div>
      {presets.length === 0 ? <p className="muted">{t("intake.noSavedPresets")}</p> : null}
      {presets.map((preset) => (
        <div className="intake-recent-card" key={preset.id}>
          <strong>{preset.name}</strong>
          <small>{preset.profile_url}</small>
          <div className="intake-actions">
            <button onClick={() => onApply(preset)} type="button">{t("intake.applySavedPreset")}</button>
            <button onClick={() => onRename(preset)} type="button">{t("intake.renameSavedPreset")}</button>
            <button onClick={() => onDelete(preset)} type="button">{t("intake.deleteSavedPreset")}</button>
          </div>
        </div>
      ))}
    </section>
  );
}

function RecentProfilePanel({
  profiles,
  onApply
}: {
  profiles: IntakeRecentProfileResponse[];
  onApply: (profile: IntakeRecentProfileResponse) => void;
}) {
  const t = useT();
  return (
    <section className="operator-panel intake-recent">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("intake.recentProfilesTitle")}</h2>
          <p>{t("intake.recentProfilesDescription")}</p>
        </div>
      </div>
      {profiles.length === 0 ? <p className="muted">{t("intake.noRecentProfiles")}</p> : null}
      {profiles.map((profile) => (
        <div className="intake-recent-card" key={profile.source_profile_id}>
          <strong>{profile.display_name ?? profile.normalized_profile_identifier ?? "Profile"}</strong>
          <small>{profile.profile_url}</small>
          <button onClick={() => onApply(profile)} type="button">{t("intake.useProfile")}</button>
        </div>
      ))}
    </section>
  );
}

function LatestSuccessPanel({
  shortcuts,
  onApply
}: {
  shortcuts: IntakeLatestSuccessShortcutResponse[];
  onApply: (shortcut: IntakeLatestSuccessShortcutResponse) => void;
}) {
  const t = useT();
  return (
    <section className="operator-panel intake-recent">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("intake.latestSuccessTitle")}</h2>
          <p>{t("intake.latestSuccessDescription")}</p>
        </div>
      </div>
      {shortcuts.length === 0 ? <p className="muted">{t("intake.noLatestSuccessShortcuts")}</p> : null}
      {shortcuts.map((shortcut) => (
        <div className="intake-recent-card" key={shortcut.crawl_session_id}>
          <strong>{shortcut.normalized_profile_identifier ?? t("intake.recentFetchFallback")}</strong>
          <small>{shortcut.submitted_profile_url ?? t("intake.noCapturedUrl")}</small>
          <button disabled={!shortcut.submitted_profile_url} onClick={() => onApply(shortcut)} type="button">{t("intake.useLatestSuccess")}</button>
        </div>
      ))}
    </section>
  );
}

function GuidancePanel() {
  const t = useT();
  return (
    <section className="operator-panel">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("intake.flowTitle")}</h2>
          <p>{t("intake.flowDescription")}</p>
        </div>
      </div>
      <ol className="intake-flow">
        <li>{t("intake.flowStepSource")}</li>
        <li>{t("intake.flowStepFilter")}</li>
        <li>{t("intake.flowStepReview")}</li>
      </ol>
    </section>
  );
}

function RunHistoryPanel({
  loading,
  error,
  runs,
  selectedRunId,
  onSelectRun,
  onApplyRun
}: {
  loading: boolean;
  error: string | null;
  runs: IntakeRunSummaryResponse[];
  selectedRunId: string;
  onSelectRun: (id: string) => void;
  onApplyRun: (run: IntakeRunSummaryResponse) => void;
}) {
  const t = useT();
  const [showAllHistory, setShowAllHistory] = useState(false);

  const groupedRuns = useMemo(() => {
    const groups = new Map<string, { label: string; runs: IntakeRunSummaryResponse[] }>();
    for (const run of runs) {
      const label = run.normalized_profile_identifier ?? run.source_profile_display_name ?? t("intake.runUnknownProfile");
      const key = run.normalized_profile_identifier ?? run.source_profile_display_name ?? run.source_profile_id ?? `unknown:${run.crawl_session_id}`;
      const current = groups.get(key);
      if (current) {
        current.runs.push(run);
      } else {
        groups.set(key, { label, runs: [run] });
      }
    }

    return Array.from(groups.values()).map((group) => {
      const latestRun = group.runs[0];
      const failedRuns = group.runs.filter((item) => item.status === "FAILED");
      const latestFailedRun = failedRuns[0] ?? null;
      const successCount = group.runs.filter((item) => item.status === "SUCCEEDED").length;
      return {
        label: group.label,
        latestRun,
        latestFailedRun,
        runCount: group.runs.length,
        successCount,
        failureCount: failedRuns.length
      };
    });
  }, [runs, t]);

  const compactGroups = groupedRuns.slice(0, 5);

  return (
    <section className="operator-panel intake-recent">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("intake.runHistoryTitle")}</h2>
          <p>{t("intake.runHistoryDescription")}</p>
        </div>
      </div>
      {loading ? <p className="muted">{t("intake.runHistoryLoading")}</p> : null}
      {error ? <p className="field-warning">{error}</p> : null}
      {!loading && runs.length === 0 ? <p className="muted">{t("intake.runHistoryEmpty")}</p> : null}

      {compactGroups.map((group) => (
        <div className="intake-recent-card" key={`${group.label}-${group.latestRun.crawl_session_id}`}>
          <strong>{group.label}</strong>
          <small>{formatRunMeta(group.latestRun, t)}</small>
          <small>{`${t("intake.runGroupSummaryPrefix")}: ${group.runCount} · ${t("intake.runGroupSummarySuccess")}: ${group.successCount} · ${t("intake.runGroupSummaryFailed")}: ${group.failureCount}`}</small>
          {group.latestFailedRun ? (
            <small>{`${t("intake.runErrorCode")}: ${group.latestFailedRun.error_code ?? t("intake.runNoError")}`}</small>
          ) : (
            <small>{t("intake.runNoRecentFailure")}</small>
          )}
          <div className="intake-actions">
            <button
              onClick={() => onSelectRun(group.latestRun.crawl_session_id)}
              type="button"
              disabled={selectedRunId === group.latestRun.crawl_session_id}
            >
              {selectedRunId === group.latestRun.crawl_session_id ? t("intake.runSelected") : t("intake.runViewDetails")}
            </button>
            <button onClick={() => onApplyRun(group.latestRun)} type="button" disabled={!group.latestRun.submitted_profile_url}>
              {t("intake.runReuseSource")}
            </button>
          </div>
        </div>
      ))}

      {runs.length > 5 ? (
        <div className="intake-actions">
          <button onClick={() => setShowAllHistory((current) => !current)} type="button">
            {showAllHistory
              ? t("intake.runViewLessHistory")
              : `${t("intake.runViewAllHistoryPrefix")} (${Math.min(5, runs.length)}/${runs.length})`}
          </button>
        </div>
      ) : null}

      {showAllHistory ? (
        <div className="intake-recent-card">
          <strong>{t("intake.runFullHistoryTitle")}</strong>
          {runs.map((run) => (
            <div className="intake-recent-card" key={run.crawl_session_id}>
              <strong>{run.normalized_profile_identifier ?? run.source_profile_display_name ?? t("intake.runUnknownProfile")}</strong>
              <small>{formatRunMeta(run, t)}</small>
              <small>{run.error_code ? `${t("intake.runErrorCode")}: ${run.error_code}` : t("intake.runNoError")}</small>
              <div className="intake-actions">
                <button onClick={() => onSelectRun(run.crawl_session_id)} type="button" disabled={selectedRunId === run.crawl_session_id}>
                  {selectedRunId === run.crawl_session_id ? t("intake.runSelected") : t("intake.runViewDetails")}
                </button>
                <button onClick={() => onApplyRun(run)} type="button" disabled={!run.submitted_profile_url}>
                  {t("intake.runReuseSource")}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function RunTroubleshootingPanel({
  loading,
  error,
  run,
  onApplyRun
}: {
  loading: boolean;
  error: string | null;
  run: IntakeRunDetailResponse | null;
  onApplyRun: (run: IntakeRunDetailResponse) => void;
}) {
  const t = useT();
  return (
    <section className="operator-panel intake-recent">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("intake.troubleshootingTitle")}</h2>
          <p>{t("intake.troubleshootingDescription")}</p>
        </div>
      </div>
      {loading ? <p className="muted">{t("intake.troubleshootingLoading")}</p> : null}
      {error ? <p className="field-warning">{error}</p> : null}
      {!loading && !error && !run ? <p className="muted">{t("intake.troubleshootingEmpty")}</p> : null}
      {run ? (
        <>
          <div className="intake-recent-card">
            <strong>{run.troubleshooting.category}</strong>
            <small>{`${t("intake.troubleshootingSeverity")}: ${run.troubleshooting.severity}`}</small>
            <small>{run.troubleshooting.why}</small>
            <small>{run.error_message ?? t("intake.troubleshootingNoErrorMessage")}</small>
          </div>
          {run.troubleshooting.recommended_actions.length > 0 ? (
            <ol className="intake-flow">
              {run.troubleshooting.recommended_actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ol>
          ) : null}
          <div className="intake-actions">
            <button onClick={() => onApplyRun(run)} type="button" disabled={!run.submitted_profile_url}>{t("intake.runReuseSource")}</button>
            <a className="operator-inline-link" href="/accounts/douyin">{t("intake.manageDouyinAccounts")}</a>
          </div>
        </>
      ) : null}
    </section>
  );
}

function RunComparePanel({
  runs,
  leftRunId,
  rightRunId,
  onChangeLeft,
  onChangeRight,
  loading,
  error,
  result
}: {
  runs: IntakeRunSummaryResponse[];
  leftRunId: string;
  rightRunId: string;
  onChangeLeft: (value: string) => void;
  onChangeRight: (value: string) => void;
  loading: boolean;
  error: string | null;
  result: IntakeRunCompareResponse | null;
}) {
  const t = useT();
  return (
    <section className="operator-panel intake-recent">
      <div className="operator-panel-heading">
        <div>
          <h2>{t("intake.runCompareTitle")}</h2>
          <p>{t("intake.runCompareDescription")}</p>
        </div>
      </div>
      <SelectField
        label={t("intake.runCompareLeft")}
        value={leftRunId}
        onChange={onChangeLeft}
        options={runs.map((run) => ({
          label: `${run.normalized_profile_identifier ?? run.source_profile_display_name ?? run.crawl_session_id} · ${run.status}`,
          value: run.crawl_session_id
        }))}
      />
      <SelectField
        label={t("intake.runCompareRight")}
        value={rightRunId}
        onChange={onChangeRight}
        options={runs.map((run) => ({
          label: `${run.normalized_profile_identifier ?? run.source_profile_display_name ?? run.crawl_session_id} · ${run.status}`,
          value: run.crawl_session_id
        }))}
      />
      {leftRunId && rightRunId && leftRunId === rightRunId ? <p className="muted">{t("intake.runCompareSameSelection")}</p> : null}
      {loading ? <p className="muted">{t("intake.runCompareLoading")}</p> : null}
      {error ? <p className="field-warning">{error}</p> : null}
      {result ? (
        <div className="intake-result-grid">
          <SummaryStat label={t("intake.runCompareStatusChanged")} value={result.status_changed ? t("common.yes") : t("common.no")} />
          <SummaryStat label={t("intake.runCompareDurationDelta")} value={String(result.duration_seconds_delta ?? 0)} />
          <SummaryStat label={t("intake.runCompareVideosDelta")} value={String(result.videos_discovered_delta)} />
          <SummaryStat label={t("intake.runCompareMatchedDelta")} value={String(result.candidates_matched_delta)} />
        </div>
      ) : null}
    </section>
  );
}

function formatRunMeta(run: IntakeRunSummaryResponse, t: (key: string) => string): string {
  const status = `${t("intake.runStatus")}: ${run.status}`;
  const fetchMode = `${t("intake.fetchMode")}: ${run.fetch_mode ?? t("common.unknown")}`;
  const matched = `${t("intake.candidatesMatched")}: ${run.candidates_matched_count}`;
  return `${status} · ${fetchMode} · ${matched}`;
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="intake-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
