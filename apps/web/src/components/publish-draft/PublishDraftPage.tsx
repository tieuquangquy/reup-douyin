"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  fetchSourceVideoAssetManifest,
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
  schedulePayload,
  toPublishDraftUpdatePayload,
  validatePublishDraft
} from "../../lib/publishDraftState";
import { humanizeStatus } from "../../lib/statusLabels";
import { useAsyncAction } from "../../lib/useAsyncAction";
import type { RenderOutput, SourceVideoAssetManifest } from "../../types/final-review";
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
import { RiskSummaryCard } from "../risk/RiskSummaryCard";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { CaptionEditor } from "./CaptionEditor";
import { HashtagEditor } from "./HashtagEditor";
import { PublishDraftHeader } from "./PublishDraftHeader";
import { PublishDraftErrorState } from "./PublishDraftStates";
import { PublishMediaSummary } from "./PublishMediaSummary";
import { PublishPreviewPanel } from "./PublishPreviewPanel";
import { PublishSchedulePanel } from "./PublishSchedulePanel";
import { PublishTargetSelector } from "./PublishTargetSelector";

export function PublishDraftPage({ sourceVideoId, initialDraftId }: { sourceVideoId: string; initialDraftId?: string }) {
  const t = useT();
  const asyncAction = useAsyncAction();
  const { notify } = useNotice();
  const [draft, setDraft] = useState<PublishDraft | null>(null);
  const [editable, setEditable] = useState<EditablePublishDraft | null>(null);
  const [savedEditable, setSavedEditable] = useState<EditablePublishDraft | null>(null);
  const [targets, setTargets] = useState<PublishTarget[]>([]);
  const [render, setRender] = useState<RenderOutput | null>(null);
  const [manifest, setManifest] = useState<SourceVideoAssetManifest | null>(null);
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

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextTargets, drafts, latestRender, assetManifest] = await Promise.all([
        fetchPublishTargets(),
        fetchPublishDrafts(sourceVideoId),
        fetchLatestRender(sourceVideoId),
        fetchSourceVideoAssetManifest(sourceVideoId)
      ]);
      const latestDraft = (initialDraftId ? drafts.find((item) => item.id === initialDraftId) : null) ?? drafts[0] ?? null;
      const nextEditable = latestDraft ? buildEditablePublishDraft(latestDraft) : null;
      setTargets(nextTargets);
      setDraft(latestDraft);
      setEditable(nextEditable);
      setSavedEditable(nextEditable);
      setRender(latestRender);
      setManifest(assetManifest);
      if (latestDraft) {
        setRiskSummary(await fetchRiskSummary("PUBLISH_DRAFT", latestDraft.id));
        const [accounts, history] = await Promise.all([
          fetchPlatformAccounts("FACEBOOK_REELS"),
          fetchPublishHistory(latestDraft.id)
        ]);
        setPlatformAccounts(accounts);
        setPublishAttempts(history.attempts);
        setPublicationSummary(history.summary);
        setSelectedAccountId(accounts[0]?.id ?? "");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftPage.loadError"));
    } finally {
      setLoading(false);
    }
  }, [sourceVideoId, initialDraftId, t]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

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
      const accounts = await fetchPlatformAccounts("FACEBOOK_REELS");
      setPlatformAccounts(accounts);
      const history = await fetchPublishHistory(nextDraft.id);
      setPublishAttempts(history.attempts);
      setPublicationSummary(history.summary);
      setSelectedAccountId(accounts[0]?.id ?? "");
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
      <main className="publish-page">
        <AsyncContentBoundary status="loading" skeletonVariant="form" loadingLabel={t("publishDraftStates.loading")}>
          {null}
        </AsyncContentBoundary>
      </main>
    );
  }
  if (error && !targets.length) return <PublishDraftErrorState message={error} onRetry={loadData} />;

  return (
    <main className="publish-page">
      <PublishDraftHeader
        draft={draft}
        editable={editable}
        dirty={dirty}
        saving={saving}
        savePending={asyncAction.isPending("save-draft")}
        readyPending={asyncAction.isPending("mark-ready")}
        errors={validationErrors}
        onSave={() => void asyncAction.run("save-draft", handleSave)}
        onDiscard={() => setEditable(savedEditable)}
        onMarkReady={() => void asyncAction.run("mark-ready", handleMarkReady)}
      />
      {error ? <div className="inline-error">{error}</div> : null}
      {message ? <div className="publish-ready-banner">{message}</div> : null}
      <section className="publish-layout">
        <div className="publish-main">
          <PublishTargetSelector
            targets={targets}
            editable={editable}
            disabled={saving}
            createPending={asyncAction.isPending("create-draft")}
            onChange={patchEditable}
            onCreate={(platform) => void asyncAction.run("create-draft", () => handleCreate(platform))}
          />
          {editable ? (
            <>
              <CaptionEditor editable={editable} disabled={saving} onChange={patchEditable} />
              <HashtagEditor editable={editable} disabled={saving} onReplace={setEditable} />
              {draft ? (
                <PublishSchedulePanel
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
            </>
          ) : null}
        </div>
        <aside className="publish-side">
          <PublishMediaSummary render={render} manifest={manifest} draft={draft} />
          {draft ? (
            <RiskSummaryCard
              summary={riskSummary}
              loading={riskLoading}
              onScan={() => void handleRiskScan()}
              onFlagAction={(flag, action) => void handleRiskFlagAction(flag, action)}
              onDecision={(decision) => void handleRiskDecision(decision)}
            />
          ) : null}
          {draft ? (
            <section className="publish-panel">
              <h2>{t("publishDraftPage.facebookPagePublish")}</h2>
              {publicationSummary ? (
                <div className="publish-status-summary">
                  <strong>{humanizeStatus(publicationSummary.draft_status)}</strong>
                  <span>{t("publishDraftPage.platform")}: {humanizeStatus(publicationSummary.current_publication_status)}</span>
                  {publicationSummary.current_external_permalink ? (
                    <a href={publicationSummary.current_external_permalink} target="_blank" rel="noreferrer">
                      {t("publishDraftPage.openPublishedReel")}
                    </a>
                  ) : null}
                  {publicationSummary.requires_operator_attention ? (
                    <span className="warning-text">{t("publishDraftPage.needsAttention")}</span>
                  ) : null}
                  {publicationSummary.warnings.length > 0 ? (
                    <div className="small-meta">{t("publishDraftPage.warnings")}: {publicationSummary.warnings.join(", ")}</div>
                  ) : null}
                </div>
              ) : null}
              <label className="field-label" htmlFor="platform-account">{t("publishDraftPage.pageAccount")}</label>
              <select
                id="platform-account"
                value={selectedAccountId}
                disabled={saving || platformAccounts.length === 0}
                onChange={(event) => setSelectedAccountId(event.target.value)}
              >
                {platformAccounts.length === 0 ? <option value="">{t("publishDraftPage.noActiveAccount")}</option> : null}
                {platformAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.display_name} ({account.external_account_id})
                  </option>
                ))}
              </select>
              <AsyncButton
                className="primary-action"
                pending={asyncAction.isPending("publish-now")}
                pendingLabel={t("publishDraftPage.publishNow")}
                disabled={draft.status !== "READY" || !selectedAccountId}
                onClick={() => void asyncAction.run("publish-now", handlePublishNow)}
              >
                {t("publishDraftPage.publishNow")}
              </AsyncButton>
              <div className="small-meta">
                {draft.status !== "READY" ? t("publishDraftPage.draftMustBeReady") : t("publishDraftPage.publishesApprovedRender")}
              </div>
              <AsyncButton
                className="secondary-action"
                pending={reconcilingDraft}
                pendingLabel={t("publishDraftPage.reconciling")}
                disabled={publishAttempts.length === 0}
                onClick={() => void asyncAction.run("reconcile", handleReconcileDraft)}
              >
                {t("publishDraftPage.reconcileDraft")}
              </AsyncButton>
              <h3>{t("publishDraftPage.attempts")}</h3>
              {publishAttempts.length === 0 ? (
                <div className="small-meta">{t("publishDraftPage.noAttemptsYet")}</div>
              ) : (
                <ul className="compact-list">
                  {publishAttempts.slice(0, 5).map((attempt) => (
                    <li key={attempt.id}>
                      <span>
                        #{attempt.attempt_number} {humanizeStatus(attempt.status)}
                        {attempt.external_status ? ` / ${humanizeStatus(attempt.external_status)}` : ""}
                        {attempt.external_reel_id ? ` - ${t("publishDraftPage.reel")} ${attempt.external_reel_id}` : ""}
                        {publicationSummary?.canonical_publish_attempt_id === attempt.id ? ` - ${t("publishDraftPage.canonical")}` : ""}
                        {publicationSummary?.latest_publish_attempt_id === attempt.id ? ` - ${t("publishDraftPage.latest")}` : ""}
                      </span>
                      {attempt.external_permalink ? (
                        <a href={attempt.external_permalink} target="_blank" rel="noreferrer">
                          {t("publishDraftPage.open")}
                        </a>
                      ) : null}
                      {attempt.reconciliation_required || attempt.status === "NEEDS_RECONCILIATION" ? (
                        <AsyncButton
                          className="secondary-action"
                          pending={refreshingAttemptId === attempt.id}
                          pendingLabel={t("publishDraftPage.refreshing")}
                          onClick={() => void asyncAction.run(`refresh-${attempt.id}`, () => handleRefreshAttempt(attempt.id))}
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
          ) : null}
          {editable ? <PublishPreviewPanel editable={editable} target={target} /> : null}
        </aside>
      </section>
    </main>
  );
}
