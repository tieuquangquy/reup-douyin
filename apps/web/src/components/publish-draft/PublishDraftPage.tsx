"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from "react";
import { useT } from "../../lib/i18n";
import {
  createPublishDraft,
  createRiskDecision,
  fetchLatestRender,
  fetchPlatformAccounts,
  fetchPublishDrafts,
  fetchPublishHistory,
  fetchPublishTargets,
  fetchRiskSummary,
  markPublishDraftReady,
  publishDraftNow,
  reconcilePublishDraft,
  refreshPublishAttemptStatus,
  runRiskScan,
  schedulePublishDraft,
  unschedulePublishDraft,
  updatePublishDraft,
  updateRiskFlagStatus
} from "../../lib/api";
import {
  buildEditablePublishDraft,
  hasDraftChanges,
  remainingPostChars,
  remainingHashtagSlots,
  resolvePublishAccountId,
  schedulePayload,
  toPublishDraftUpdatePayload,
  validatePublishDraft
} from "../../lib/publishDraftState";
import { humanizeStatus } from "../../lib/statusLabels";
import { useAsyncAction } from "../../lib/useAsyncAction";
import type { RenderOutput } from "../../types/final-review";
import type {
  EditablePublishDraft,
  PlatformAccount,
  PublicationSummary,
  PublishAttempt,
  PublishDraft,
  PublishTarget,
  PublishTargetPlatform
} from "../../types/publish-draft";
import type { OperatorRiskDecisionType, RiskFlag, RiskSummary } from "../../types/risk";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { CaptionEditor } from "./CaptionEditor";
import { HashtagEditor } from "./HashtagEditor";
import { PublishDestSelect } from "./PublishDestSelect";
import { PublishDraftGate } from "./PublishDraftGate";
import { PublishDraftHeader } from "./PublishDraftHeader";
import { PublishDraftErrorState } from "./PublishDraftStates";
import { PublishPreviewPanel } from "./PublishPreviewPanel";
import { PublishSchedulePanel } from "./PublishSchedulePanel";
import { PublishTargetSelector } from "./PublishTargetSelector";

function PublishBayIcon({ kind }: { kind: "route" | "account" | "reconcile" | "refresh" }) {
  if (kind === "account") {
    return (
      <svg className="publish-draft-desk__bay-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M10 3.8a2.8 2.8 0 1 1 0 5.6 2.8 2.8 0 0 1 0-5.6ZM4.8 16.2c.6-2.6 2.6-4 5.2-4s4.6 1.4 5.2 4"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.6"
        />
      </svg>
    );
  }
  if (kind === "reconcile") {
    return (
      <svg className="publish-draft-desk__bay-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.4 8.1H3.2V6.8M3.4 8A5.6 5.6 0 1 1 5 13.4"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.7"
        />
      </svg>
    );
  }
  if (kind === "refresh") {
    return (
      <svg className="publish-draft-desk__bay-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M15.2 8.2A5.4 5.4 0 1 0 14 13.2M15.2 4.8v3.4h-3.4"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.7"
        />
      </svg>
    );
  }
  return (
    <svg className="publish-draft-desk__bay-icon" viewBox="0 0 20 20" aria-hidden="true">
      <rect x="6.2" y="2.6" width="7.6" height="14.8" rx="2.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9.1 15.4h1.8" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  );
}

export type PublishDraftPageHandle = {
  refresh: () => Promise<void>;
};

export const PublishDraftPage = forwardRef<
  PublishDraftPageHandle,
  { sourceVideoId: string; initialDraftId?: string }
>(function PublishDraftPage({ sourceVideoId, initialDraftId }, ref) {
  const t = useT();
  const asyncAction = useAsyncAction();
  const { notify } = useNotice();
  const [draft, setDraft] = useState<PublishDraft | null>(null);
  const [editable, setEditable] = useState<EditablePublishDraft | null>(null);
  const [savedEditable, setSavedEditable] = useState<EditablePublishDraft | null>(null);
  const [targets, setTargets] = useState<PublishTarget[]>([]);
  const [render, setRender] = useState<RenderOutput | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [riskSummary, setRiskSummary] = useState<RiskSummary | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [platformAccounts, setPlatformAccounts] = useState<PlatformAccount[]>([]);
  const [publishAttempts, setPublishAttempts] = useState<PublishAttempt[]>([]);
  const [publicationSummary, setPublicationSummary] = useState<PublicationSummary | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [refreshingAttemptId, setRefreshingAttemptId] = useState<string | null>(null);
  const [reconcilingDraft, setReconcilingDraft] = useState(false);

  const loadData = useCallback(async (mode: "initial" | "refresh" = "initial") => {
    if (mode === "initial") setLoading(true);
    setError(null);
    try {
      const [nextTargets, drafts, latestRender] = await Promise.all([
        fetchPublishTargets(),
        fetchPublishDrafts(sourceVideoId),
        fetchLatestRender(sourceVideoId)
      ]);
      const latestDraft = (initialDraftId ? drafts.find((item) => item.id === initialDraftId) : null) ?? drafts[0] ?? null;
      const nextEditable = latestDraft ? buildEditablePublishDraft(latestDraft) : null;
      setTargets(nextTargets);
      setDraft(latestDraft);
      setEditable(nextEditable);
      setSavedEditable(nextEditable);
      setRender(latestRender);
      if (latestDraft) {
        setRiskSummary(await fetchRiskSummary("PUBLISH_DRAFT", latestDraft.id));
        const history = await fetchPublishHistory(latestDraft.id);
        setPublishAttempts(history.attempts);
        setPublicationSummary(history.summary);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.loadError"));
    } finally {
      if (mode === "initial") setLoading(false);
    }
  }, [sourceVideoId, initialDraftId, t]);

  useImperativeHandle(
    ref,
    () => ({
      refresh: async () => {
        await loadData("refresh");
      }
    }),
    [loadData]
  );

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const targetPlatform = editable?.targetPlatform ?? draft?.target_platform ?? null;
  useEffect(() => {
    if (!targetPlatform) {
      setPlatformAccounts([]);
      setSelectedAccountId("");
      return;
    }
    let cancelled = false;
    void fetchPlatformAccounts(targetPlatform)
      .then((accounts) => {
        if (cancelled) return;
        setPlatformAccounts(accounts);
        setSelectedAccountId((current) =>
          resolvePublishAccountId(draft?.assigned_platform_account_id, accounts, current)
        );
      })
      .catch(() => {
        if (!cancelled) {
          setPlatformAccounts([]);
          setSelectedAccountId("");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [targetPlatform, draft?.assigned_platform_account_id]);

  const target = useMemo(
    () => targets.find((item) => item.platform === editable?.targetPlatform) ?? targets[0] ?? null,
    [targets, editable]
  );
  const dirty = hasDraftChanges(editable, savedEditable);
  const validationErrors = editable ? validatePublishDraft(editable, target) : [];

  function patchEditable(patch: Partial<EditablePublishDraft>) {
    setEditable((current) => (current ? { ...current, ...patch } : current));
  }

  async function handleCreate(platform: PublishTargetPlatform) {
    setSaving(true);
    setError(null);
    try {
      const nextDraft = await createPublishDraft(sourceVideoId, platform);
      const nextEditable = buildEditablePublishDraft(nextDraft);
      setDraft(nextDraft);
      setEditable(nextEditable);
      setSavedEditable(nextEditable);
      setRiskSummary(await fetchRiskSummary("PUBLISH_DRAFT", nextDraft.id));
      const history = await fetchPublishHistory(nextDraft.id);
      setPublishAttempts(history.attempts);
      setPublicationSummary(history.summary);
      setMessage(t("publishDraftPage.createSuccess"));
      notify({ id: `publish-draft-create-${sourceVideoId}`, message: t("publishDraftPage.createSuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.createError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleSave() {
    if (!draft || !editable) return;
    setSaving(true);
    setError(null);
    try {
      const nextDraft = await updatePublishDraft(draft.id, toPublishDraftUpdatePayload(editable));
      const nextEditable = buildEditablePublishDraft(nextDraft);
      setDraft(nextDraft);
      setEditable(nextEditable);
      setSavedEditable(nextEditable);
      setMessage(t("publishDraftPage.saveSuccess"));
      notify({ id: `publish-draft-save-${draft.id}`, message: t("publishDraftPage.saveSuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.saveError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleSchedule() {
    if (!draft || !editable) return;
    setSaving(true);
    setError(null);
    try {
      const nextDraft = await schedulePublishDraft(draft.id, schedulePayload(editable));
      const nextEditable = buildEditablePublishDraft(nextDraft);
      setDraft(nextDraft);
      setEditable(nextEditable);
      setSavedEditable(nextEditable);
      setMessage(t("publishDraftPage.scheduleSuccess"));
      notify({ id: `publish-draft-schedule-${draft.id}`, message: t("publishDraftPage.scheduleSuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.scheduleError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleUnschedule() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const nextDraft = await unschedulePublishDraft(draft.id);
      const nextEditable = buildEditablePublishDraft(nextDraft);
      setDraft(nextDraft);
      setEditable(nextEditable);
      setSavedEditable(nextEditable);
      setMessage(t("publishDraftPage.unscheduleSuccess"));
      notify({ id: `publish-draft-unschedule-${draft.id}`, message: t("publishDraftPage.unscheduleSuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.unscheduleError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleMarkReady() {
    if (!draft || validationErrors.length > 0) return;
    if (riskSummary && !riskSummary.gate.can_continue) {
      setError(t("publishDraftPage.riskCheckReady"));
      return;
    }
    if (riskSummary?.gate.requires_operator_decision && !riskSummary.latest_decision) {
      setError(t("publishDraftPage.riskDecisionReady"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (dirty && editable) {
        const savedDraft = await updatePublishDraft(draft.id, toPublishDraftUpdatePayload(editable));
        const savedEditable = buildEditablePublishDraft(savedDraft);
        setDraft(savedDraft);
        setEditable(savedEditable);
        setSavedEditable(savedEditable);
      }
      const nextDraft = await markPublishDraftReady(draft.id);
      const nextEditable = buildEditablePublishDraft(nextDraft);
      setDraft(nextDraft);
      setEditable(nextEditable);
      setSavedEditable(nextEditable);
      setMessage(t("publishDraftPage.markReadySuccess"));
      notify({ id: `publish-draft-ready-${draft.id}`, message: t("publishDraftPage.markReadySuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.markReadyError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleRiskScan() {
    if (!draft) return;
    setRiskLoading(true);
    try {
      setRiskSummary(await runRiskScan("PUBLISH_DRAFT", draft.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.riskScanError"));
    } finally {
      setRiskLoading(false);
    }
  }

  async function handleRiskFlagAction(flag: RiskFlag, action: "acknowledge" | "resolve" | "waive") {
    if (!draft) return;
    setRiskLoading(true);
    try {
      await updateRiskFlagStatus(flag.id, action);
      setRiskSummary(await fetchRiskSummary("PUBLISH_DRAFT", draft.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.riskFlagError"));
    } finally {
      setRiskLoading(false);
    }
  }

  async function handleRiskDecision(decision: OperatorRiskDecisionType) {
    if (!draft) return;
    setRiskLoading(true);
    try {
      setRiskSummary(await createRiskDecision("PUBLISH_DRAFT", draft.id, decision));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.riskDecisionError"));
    } finally {
      setRiskLoading(false);
    }
  }

  async function handlePublishNow() {
    if (!draft || !selectedAccountId) return;
    setSaving(true);
    setError(null);
    try {
      const attempt = await publishDraftNow(draft.id, selectedAccountId);
      const history = await fetchPublishHistory(draft.id);
      setPublishAttempts(history.attempts);
      setPublicationSummary(history.summary);
      const message = attempt.status === "SUCCEEDED" ? t("publishDraftPage.publishSuccess") : `Publish attempt finished with status ${humanizeStatus(attempt.status)}.`;
      setMessage(message);
      notify({
        id: `publish-attempt-${attempt.id}`,
        message,
        tone: attempt.status === "SUCCEEDED" ? "success" : "warning"
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.publishError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleRefreshAttempt(attemptId: string) {
    if (!draft) return;
    setRefreshingAttemptId(attemptId);
    setError(null);
    try {
      const attempt = await refreshPublishAttemptStatus(attemptId);
      const history = await fetchPublishHistory(draft.id);
      setPublishAttempts(history.attempts);
      setPublicationSummary(history.summary);
      setMessage(`Facebook status refreshed: ${humanizeStatus(attempt.external_status ?? attempt.status)}.`);
      notify({
        id: `publish-attempt-refresh-${attempt.id}`,
        message: `Facebook status refreshed: ${humanizeStatus(attempt.external_status ?? attempt.status)}.`,
        tone: "info"
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.refreshError"));
    } finally {
      setRefreshingAttemptId(null);
    }
  }

  async function handleReconcileDraft() {
    if (!draft) return;
    setReconcilingDraft(true);
    setError(null);
    try {
      const history = await reconcilePublishDraft(draft.id);
      setPublishAttempts(history.attempts);
      setPublicationSummary(history.summary);
      setMessage(t("publishDraftPage.reconcileSuccess"));
      notify({ id: `publish-draft-reconcile-${draft.id}`, message: t("publishDraftPage.reconcileSuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.reconcileError"));
    } finally {
      setReconcilingDraft(false);
    }
  }

  if (loading) {
    return (
      <main className="publish-draft-desk is-stage">
        <AsyncContentBoundary status="loading" skeletonVariant="form" loadingLabel={t("publishDraftStates.loading")}>
          {null}
        </AsyncContentBoundary>
      </main>
    );
  }
  if (error && !targets.length) return <PublishDraftErrorState message={error} onRetry={loadData} />;

  const publishedAt = publicationSummary?.published_at ?? draft?.published_at ?? null;
  const permalink = publicationSummary?.current_external_permalink ?? draft?.current_external_permalink ?? null;
  const assignmentStatus = draft?.assignment_status ?? "UNASSIGNED";
  const remainingChars = editable ? remainingPostChars(editable, target) : null;
  const remainingTags = editable ? remainingHashtagSlots(editable, target) : null;
  const canPublish = Boolean(draft && draft.status === "READY" && selectedAccountId);
  const selectedAccount = platformAccounts.find((item) => item.id === selectedAccountId) ?? null;

  return (
    <main className="publish-draft-desk is-stage">
      <PublishDraftHeader
        sourceVideoId={sourceVideoId}
        draft={draft}
        editable={editable}
        dirty={dirty}
        saving={saving}
        savePending={asyncAction.isPending("save-draft")}
        readyPending={asyncAction.isPending("mark-ready")}
        publishPending={asyncAction.isPending("publish-now")}
        errors={validationErrors}
        remainingChars={remainingChars}
        remainingTags={remainingTags}
        canPublish={canPublish}
        onChange={patchEditable}
        onSave={() => void asyncAction.run("save-draft", handleSave)}
        onDiscard={() => setEditable(savedEditable)}
        onMarkReady={() => void asyncAction.run("mark-ready", handleMarkReady)}
        onPublishNow={draft ? () => void asyncAction.run("publish-now", handlePublishNow) : undefined}
      />
      {error ? <div className="publish-draft-desk__alert is-error">{error}</div> : null}
      {draft?.error_message ? (
        <div className="publish-draft-desk__alert is-error">{draft.error_message}</div>
      ) : null}
      {message ? <div className="publish-draft-desk__alert is-ok">{message}</div> : null}
      <section className="publish-draft-desk__stage">
        <aside className="publish-draft-desk__rail">
          {editable ? (
            <PublishPreviewPanel
              editable={editable}
              target={target}
              mediaAssetId={render?.media_asset_id}
              platformLabel={humanizeStatus(draft?.target_platform ?? editable.targetPlatform)}
              accountLabel={selectedAccount?.display_name ?? t("publishDraftPage.unassignedAccount")}
              accountHint={selectedAccount?.external_account_id ?? null}
            />
          ) : null}
        </aside>
        <div className="publish-draft-desk__copy">
          {!editable ? (
            <PublishTargetSelector
              targets={targets}
              editable={editable}
              disabled={saving}
              createPending={asyncAction.isPending("create-draft")}
              onChange={patchEditable}
              onCreate={(platform) => void asyncAction.run("create-draft", () => handleCreate(platform))}
            />
          ) : null}
          {editable ? (
            <div className="publish-draft-desk__dock is-pedestal">
              <div className="publish-draft-desk__composer">
                <CaptionEditor
                  editable={editable}
                  disabled={saving}
                  remainingChars={remainingChars}
                  onChange={patchEditable}
                />
                <HashtagEditor
                  editable={editable}
                  disabled={saving}
                  remainingTags={remainingTags}
                  onReplace={setEditable}
                />
              </div>
            </div>
          ) : null}
        </div>
        {draft ? (
            <section className="publish-draft-desk__ops publish-draft-desk__bay is-pedestal">
              <header className="publish-draft-desk__bay-head">
                <h2 className="publish-draft-desk__heading">
                  <svg className="publish-draft-desk__heading-icon" viewBox="0 0 20 20" aria-hidden="true">
                    <rect
                      x="6.2"
                      y="2.6"
                      width="7.6"
                      height="14.8"
                      rx="2.2"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.6"
                    />
                    <path d="M9.1 15.4h1.8" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
                  </svg>
                  {t("publishDraftPage.destination")}
                </h2>
                <span className={`publish-draft-desk__chip is-${assignmentStatus.toLowerCase()}`}>
                  {humanizeStatus(assignmentStatus)}
                </span>
              </header>
              <div className="publish-draft-desk__dest-sheet">
              <div className="publish-draft-desk__dest-identity">
              <div className="publish-draft-desk__route" aria-label={humanizeStatus(draft.target_platform)}>
                {editable ? (
                  <PublishTargetSelector
                    targets={targets}
                    editable={editable}
                    disabled={saving}
                    createPending={asyncAction.isPending("create-draft")}
                    onChange={patchEditable}
                    onCreate={(platform) => void asyncAction.run("create-draft", () => handleCreate(platform))}
                  />
                ) : null}
                {(render?.width && render.height) || render?.status ? (
                  <p className="publish-draft-desk__facts-line">
                    {render?.width && render.height ? `${render.width}×${render.height}` : ""}
                    {render?.width && render.height && render.status ? " · " : ""}
                    {render?.status ? humanizeStatus(render.status) : ""}
                  </p>
                ) : null}
              </div>
              <div className="publish-draft-desk__account">
                <div className="publish-draft-desk__cta-row">
                <div className="publish-field publish-draft-desk__dest-account publish-draft-desk__cta">
                  <span className="publish-draft-desk__label" id="dest-account-label">
                    {t("publishDraftPage.destinationAccount")}
                  </span>
                  <PublishDestSelect
                    id="platform-account"
                    className="publish-draft-desk__account-select"
                    labelledBy="dest-account-label"
                    value={selectedAccountId}
                    disabled={saving || platformAccounts.length === 0}
                    options={[
                      {
                        value: "",
                        label:
                          platformAccounts.length === 0
                            ? t("publishDraftPage.noActiveAccount")
                            : t("publishDraftPage.unassignedAccount")
                      },
                      ...platformAccounts.map((account) => ({
                        value: account.id,
                        label: account.display_name,
                        hint: `${account.external_account_id}${
                          draft.assigned_platform_account_id === account.id
                            ? ` · ${t("publishDraftPage.assigned")}`
                            : ""
                        }`
                      }))
                    ]}
                    onChange={setSelectedAccountId}
                  />
                </div>
                </div>
                {editable && target?.account_ref_required ? (
                  <label className="publish-field publish-draft-desk__account-ref">
                    {t("publishTargetSelector.accountRefPlaceholder")}
                    <input
                      value={editable.platformAccountRef}
                      onChange={(event) => patchEditable({ platformAccountRef: event.target.value })}
                      disabled={saving}
                    />
                  </label>
                ) : null}
                <div className="publish-draft-desk__dest-meta">
                  {publishedAt ? (
                    <span>
                      {t("publishDraftPage.publishedAt")}: {new Date(publishedAt).toLocaleString()}
                    </span>
                  ) : null}
                  {draft.last_publish_synced_at ? (
                    <span>
                      {t("publishDraftPage.syncedAt")}: {new Date(draft.last_publish_synced_at).toLocaleString()}
                    </span>
                  ) : null}
                  {permalink ? (
                    <a href={permalink} target="_blank" rel="noreferrer">
                      {t("publishDraftPage.openPublishedReel")}
                    </a>
                  ) : null}
                  {publicationSummary?.requires_operator_attention ? (
                    <span className="warning-text">{t("publishDraftPage.needsAttention")}</span>
                  ) : null}
                  {publicationSummary?.warnings.length ? (
                    <div className="small-meta">
                      {t("publishDraftPage.warnings")}: {publicationSummary.warnings.join(", ")}
                    </div>
                  ) : null}
                </div>
              </div>
              </div>
              {editable ? (
                <PublishSchedulePanel
                  compact
                  mode="fields"
                  draft={draft}
                  editable={editable}
                  disabled={saving}
                  schedulePending={asyncAction.isPending("schedule")}
                  unschedulePending={asyncAction.isPending("unschedule")}
                  onChange={patchEditable}
                  onSchedule={() => void asyncAction.run("schedule", handleSchedule)}
                  onUnschedule={() => void asyncAction.run("unschedule", handleUnschedule)}
                />
              ) : null}
              </div>
              {draft.status !== "READY" ? (
                <div className="warning-text">{t("publishDraftPage.draftMustBeReady")}</div>
              ) : null}
              <div className="publish-draft-desk__send">
              <div className="publish-draft-desk__command">
              <div className="publish-draft-desk__gate">
                <PublishDraftGate
                  summary={riskSummary}
                  loading={riskLoading}
                  onScan={() => void handleRiskScan()}
                  onFlagAction={(flag, action) => void handleRiskFlagAction(flag, action)}
                  onDecision={(decision) => void handleRiskDecision(decision)}
                />
              </div>
              {editable ? (
                <PublishSchedulePanel
                  compact
                  mode="actions"
                  draft={draft}
                  editable={editable}
                  disabled={saving}
                  schedulePending={asyncAction.isPending("schedule")}
                  unschedulePending={asyncAction.isPending("unschedule")}
                  onChange={patchEditable}
                  onSchedule={() => void asyncAction.run("schedule", handleSchedule)}
                  onUnschedule={() => void asyncAction.run("unschedule", handleUnschedule)}
                />
              ) : null}
                <AsyncButton
                  className="publish-draft-desk__action"
                  pending={reconcilingDraft}
                  pendingLabel={t("publishDraftPage.reconciling")}
                  disabled={publishAttempts.length === 0}
                  leadingIcon={<PublishBayIcon kind="reconcile" />}
                  onClick={() => void asyncAction.run("reconcile", handleReconcileDraft)}
                >
                  {t("publishDraftPage.reconcileDraft")}
                </AsyncButton>
              </div>
              <section className={`publish-draft-desk__attempts${publishAttempts.length === 0 ? " is-empty" : ""}`}>
                <header className="publish-draft-desk__attempts-head">
                  <h3 className="publish-draft-desk__heading">{t("publishDraftPage.attempts")}</h3>
                  <span className={`publish-draft-desk__chip ${publishAttempts.length === 0 ? "is-quiet" : "is-ready"}`}>
                    {publishAttempts.length}
                  </span>
                </header>
                  {publishAttempts.length === 0 ? (
                    <p className="publish-draft-desk__attempts-empty">{t("publishDraftPage.noAttemptsYet")}</p>
                  ) : (
                    <ul className="compact-list publish-draft-desk__attempts-list">
                      {publishAttempts.slice(0, 5).map((attempt) => (
                        <li key={attempt.id}>
                          <span>
                            #{attempt.attempt_number} {humanizeStatus(attempt.status)}
                            {attempt.external_status ? ` / ${humanizeStatus(attempt.external_status)}` : ""}
                            {attempt.external_reel_id ? ` - ${t("publishDraftPage.reel")} ${attempt.external_reel_id}` : ""}
                            {publicationSummary?.canonical_publish_attempt_id === attempt.id
                              ? ` - ${t("publishDraftPage.canonical")}`
                              : ""}
                            {publicationSummary?.latest_publish_attempt_id === attempt.id
                              ? ` - ${t("publishDraftPage.latest")}`
                              : ""}
                          </span>
                          {attempt.external_permalink ? (
                            <a href={attempt.external_permalink} target="_blank" rel="noreferrer">
                              {t("publishDraftPage.open")}
                            </a>
                          ) : null}
                          {attempt.reconciliation_required || attempt.status === "NEEDS_RECONCILIATION" ? (
                            <AsyncButton
                              className="publish-draft-desk__action"
                              pending={refreshingAttemptId === attempt.id}
                              pendingLabel={t("publishDraftPage.refreshing")}
                              leadingIcon={<PublishBayIcon kind="refresh" />}
                              onClick={() =>
                                void asyncAction.run(`refresh-${attempt.id}`, () => handleRefreshAttempt(attempt.id))
                              }
                            >
                              {t("publishDraftPage.refreshStatus")}
                            </AsyncButton>
                          ) : null}
                          {attempt.error_code ? ` - ${attempt.error_code}` : ""}
                        </li>
                      ))}
                    </ul>
                  )}
              </section>
              </div>
            </section>
          ) : null}
          {editable ? (
            <section className="publish-draft-desk__notes">
              <header className="publish-draft-desk__notes-head">
                <h2 className="publish-draft-desk__heading">{t("publishDraftPage.notes")}</h2>
                <span className="publish-draft-desk__chip is-quiet">{t("publishDraftPage.notesOptional")}</span>
              </header>
              <label className="publish-field publish-draft-desk__note">
                <span className="publish-draft-desk__label">{t("captionEditor.internalNotes")}</span>
                <textarea
                  value={editable.notes}
                  onChange={(event) => patchEditable({ notes: event.target.value })}
                  disabled={saving}
                  rows={3}
                />
              </label>
              <div className="publish-draft-desk__note-pair">
                <label className="publish-field publish-draft-desk__note">
                  <span className="publish-draft-desk__label">{t("publishDraftPage.platformNotes")}</span>
                  <textarea
                    value={editable.platformNotes}
                    onChange={(event) => patchEditable({ platformNotes: event.target.value })}
                    disabled={saving}
                    rows={2}
                  />
                </label>
                <label className="publish-field publish-draft-desk__note">
                  <span className="publish-draft-desk__label">{t("publishSchedulePanel.schedulingNotes")}</span>
                  <textarea
                    value={editable.schedulingNotes}
                    onChange={(event) => patchEditable({ schedulingNotes: event.target.value })}
                    disabled={saving}
                    rows={2}
                  />
                </label>
              </div>
            </section>
          ) : null}
      </section>
    </main>
  );
});