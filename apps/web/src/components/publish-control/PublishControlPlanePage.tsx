"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  assignPublishDraft,
  bulkAssignPublishDrafts,
  fetchPublishControlQueue,
  fetchRoutingRules,
  unassignPublishDraft,
  updatePlatformAccount,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import { defaultAssignmentReason, healthTone, queueAttentionCount } from "../../lib/publishControlState";
import { humanizeStatus } from "../../lib/statusLabels";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import type { AccountHealthSummary, PublishControlQueue, PublishQueueItem, RoutingRule } from "../../types/publish-control";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, type OpsTone } from "../ops-console/OpsShared";

type QueueFilter = "UNASSIGNED" | "ASSIGNED" | "ALL";

function mapHealthTone(status: string): OpsTone {
  return healthTone(status as AccountHealthSummary["health_status"]);
}

function ControlKpi({
  label,
  value,
  detail,
  tone = "muted",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: OpsTone;
}) {
  return (
    <article className={`ops-control-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function ControlPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-control-panel">
      <div className="ops-control-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-control-panel__body">{children}</div>
    </section>
  );
}

function ControlChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ops-control-chip tone-${tone}`}>{label}</span>;
}

export function PublishControlPlanePage() {
  const t = useT();
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkAccountId, setBulkAccountId] = useState("");
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("UNASSIGNED");
  const [actionError, setActionError] = useState<string | null>(null);
  const action = useAsyncAction();
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load(mode: LatestRequestMode = queue ? "refresh" : "initial") {
    await request.run(
      async () => Promise.all([fetchPublishControlQueue(), fetchRoutingRules()]),
      ([queuePayload, rulesPayload]) => {
        setQueue(queuePayload);
        setRules(rulesPayload.rules);
        setBulkAccountId((current) => current || queuePayload.accounts[0]?.platform_account_id || "");
      },
      mode
    ).catch(() => undefined);
  }

  useEffect(() => {
    void load("initial");
  }, [t]);

  const allDrafts = useMemo(
    () => [...(queue?.unassigned_drafts ?? []), ...(queue?.assigned_drafts ?? []), ...(queue?.scheduled_drafts ?? [])],
    [queue],
  );
  const selectedCount = selectedIds.size;
  const warningCount = queueAttentionCount(allDrafts);
  const attentionDrafts = queue?.needs_attention ?? [];
  const holdAccounts = (queue?.accounts ?? []).filter((account) => account.is_on_hold || account.health_status === "UNHEALTHY");

  const queueItems = useMemo(() => {
    if (!queue) return [];
    if (queueFilter === "UNASSIGNED") return queue.unassigned_drafts;
    if (queueFilter === "ASSIGNED") return queue.assigned_drafts;
    return [...queue.unassigned_drafts, ...queue.assigned_drafts];
  }, [queue, queueFilter]);

  async function assignRecommended(item: PublishQueueItem) {
    if (!item.recommended_platform_account_id) return;
    await action.run(`assign-${item.publish_draft_id}`, async () => {
      setActionError(null);
      try {
        await assignPublishDraft(item.publish_draft_id, {
          platform_account_id: item.recommended_platform_account_id!,
          reason: defaultAssignmentReason(item),
          assigned_by: "local_operator",
        });
        notify({ message: t("publishControlPage.assignSuccess"), tone: "success" });
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("publishControlPage.assignError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function unassign(item: PublishQueueItem) {
    await action.run(`unassign-${item.publish_draft_id}`, async () => {
      setActionError(null);
      try {
        await unassignPublishDraft(item.publish_draft_id);
        notify({ message: t("publishControlPage.unassignSuccess"), tone: "success" });
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("publishControlPage.unassignError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function bulkAssign() {
    if (!bulkAccountId || selectedIds.size === 0) return;
    await action.run("bulk-assign", async () => {
      setActionError(null);
      try {
        await bulkAssignPublishDrafts({
          publish_draft_ids: Array.from(selectedIds),
          platform_account_id: bulkAccountId,
          reason: "Bulk manual routing from publish control plane",
          assigned_by: "local_operator",
        });
        setSelectedIds(new Set());
        notify({ message: t("publishControlPage.bulkAssignSuccess"), tone: "success" });
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("publishControlPage.bulkAssignError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function toggleHold(account: AccountHealthSummary) {
    await action.run(`hold-${account.platform_account_id}`, async () => {
      setActionError(null);
      try {
        await updatePlatformAccount(account.platform_account_id, {
          is_on_hold: !account.is_on_hold,
          hold_reason: account.is_on_hold ? null : "Manual hold from publish control plane",
        });
        notify({
          message: account.is_on_hold ? t("publishControlPage.holdRemoved") : t("publishControlPage.holdPlaced"),
          tone: "success",
        });
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("publishControlPage.holdError");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  function toggle(id: string) {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  }

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load("refresh")} />
  );
  const boundaryStatus = request.initialLoading && !queue ? "loading" : request.error && !queue ? "error" : "success";
  const inlineError = actionError ?? (queue ? request.error?.message ?? null : null);

  const showAttention = attentionDrafts.length > 0 || holdAccounts.length > 0;

  return (
    <OpsConsoleShell actions={refreshAction} description={t("publishControlPage.pageDesc")} title={t("publishControlPage.pageTitle")}>
      <AsyncContentBoundary
        refreshing={request.refreshing}
        status={boundaryStatus}
        skeletonVariant="dashboard"
        loadingLabel={t("publishControlPage.loadingDetail")}
        errorState={<OpsState title={t("publishControlPage.unavailable")} detail={request.error?.message ?? t("publishControlPage.loadError")} retry={() => void load("initial")} />}
      >
      <main className="ops-page ops-control-page">
        {inlineError ? <div className="inline-error">{inlineError}</div> : null}

        <p className="ops-control-freshness">
          {t("publishControlPage.metricsGenerated")}{" "}
          <time dateTime={queue?.generated_at}>{formatDateTime(queue?.generated_at)}</time>
        </p>

        {queue ? (
          <>
            <section className="ops-control-kpis" aria-label={t("publishControlPage.pageTitle")}>
              <ControlKpi
                label={t("publishControlPage.accountsLabel")}
                value={String(queue.accounts.length)}
                detail={t("publishControlPage.configuredPages")}
                tone="muted"
              />
              <ControlKpi
                label={t("publishControlPage.unassignedLabel")}
                value={String(queue.unassigned_total ?? queue.unassigned_drafts.length)}
                detail={t("publishControlPage.readyDraftsNeedAccount")}
                tone={(queue.unassigned_total ?? queue.unassigned_drafts.length) > 0 ? "warn" : "good"}
              />
              <ControlKpi
                label={t("publishControlPage.assignedLabel")}
                value={String(queue.assigned_total ?? queue.assigned_drafts.length)}
                detail={t("publishControlPage.readyDraftsRouted")}
                tone="muted"
              />
              <ControlKpi
                label={t("publishControlPage.scheduledLabel")}
                value={String(queue.scheduled_total ?? queue.scheduled_drafts.length)}
                detail={t("publishControlPage.plannedPerAccount")}
                tone="muted"
              />
              <ControlKpi
                label={t("publishControlPage.needsAttention")}
                value={String(queue.needs_attention_total ?? queue.needs_attention.length)}
                detail={t("publishControlPage.failedOrBlocked")}
                tone={(queue.needs_attention_total ?? queue.needs_attention.length) > 0 ? "danger" : "good"}
              />
              <ControlKpi
                label={t("publishControlPage.routingWarnings")}
                value={String(warningCount)}
                detail={t("publishControlPage.overrideOrWarning")}
                tone={warningCount > 0 ? "warn" : "good"}
              />
            </section>

            <div className="ops-control-toolbar">
              <nav className="ops-control-filters" aria-label={t("publishControlPage.queueFilter")}>
                {(
                  [
                    { key: "UNASSIGNED" as const, label: t("publishControlPage.unassignedReady"), count: queue.unassigned_total ?? queue.unassigned_drafts.length },
                    { key: "ASSIGNED" as const, label: t("publishControlPage.assignedReady"), count: queue.assigned_total ?? queue.assigned_drafts.length },
                    {
                      key: "ALL" as const,
                      label: t("publishControlPage.filterAllReady"),
                      count: (queue.unassigned_total ?? queue.unassigned_drafts.length) + (queue.assigned_total ?? queue.assigned_drafts.length),
                    },
                  ] as const
                ).map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    className={`ops-control-filter${queueFilter === option.key ? " is-active" : ""}`}
                    onClick={() => setQueueFilter(option.key)}
                  >
                    {option.label} <strong>{option.count}</strong>
                  </button>
                ))}
              </nav>
              <nav className="ops-control-actions" aria-label={t("publishControlPage.triage")}>
                <Link href="/publishing/accounts">{t("publishControlPage.openAccounts")}</Link>
                <Link href="/ops/routing-rules">{t("publishControlPage.openRoutingRules")}</Link>
                <Link href="/ops/reconciliation">{t("publishControlPage.openReconciliation")}</Link>
              </nav>
            </div>

            <section className={`ops-control-main${showAttention ? " has-attention" : ""}`}>
              <div className="ops-control-primary">
                <ControlPanel title={t("publishControlPage.accountsOverview")}>
                  {queue.accounts.length === 0 ? (
                    <p className="ops-control-empty">{t("publishControlPage.noAccountsYet")}</p>
                  ) : (
                    <ul className="ops-control-accounts">
                      <li className="ops-control-account is-head" aria-hidden="true">
                        <span>{t("publishControlPage.account")}</span>
                        <span>{t("publishControlPage.health")}</span>
                        <span>{t("publishControlPage.success")}</span>
                        <span>{t("publishControlPage.assignedCount")}</span>
                        <span>{t("publishControlPage.scheduledCount")}</span>
                        <span>{t("publishControlPage.reconcileCount")}</span>
                        <span>{t("publishControlPage.action")}</span>
                      </li>
                      {queue.accounts.map((account) => (
                        <li
                          className={`ops-control-account${account.is_on_hold || account.health_status === "UNHEALTHY" ? " is-hot" : ""}`}
                          key={account.platform_account_id}
                        >
                          <div>
                            <strong className="ops-control-account__title">{account.display_name}</strong>
                            <em>{account.reasons[0] ?? t("publishControlPage.noHealthNote")}</em>
                          </div>
                          <ControlChip label={humanizeStatus(account.health_status)} tone={mapHealthTone(account.health_status)} />
                          <span>{account.success_rate_percent}%</span>
                          <span>{account.assigned_draft_count}</span>
                          <span>{account.scheduled_draft_count}</span>
                          <span>{account.needs_reconciliation_count}</span>
                          <AsyncButton
                            className="ops-control-row__action"
                            pending={action.isPending(`hold-${account.platform_account_id}`)}
                            pendingLabel={t("publishControlPage.updating")}
                            onClick={() => void toggleHold(account)}
                          >
                            {account.is_on_hold
                                ? t("publishControlPage.removeHold")
                                : t("publishControlPage.putOnHold")}
                          </AsyncButton>
                        </li>
                      ))}
                    </ul>
                  )}
                </ControlPanel>

                <ControlPanel title={t("publishControlPage.draftRoutingQueue")}>
                  <div className="ops-control-bulk">
                    <strong>
                      {selectedCount} {t("publishControlPage.bulkBarSelected")}
                    </strong>
                    <select
                      aria-label={t("publishControlPage.accountsLabel")}
                      value={bulkAccountId}
                      onChange={(event) => setBulkAccountId(event.target.value)}
                    >
                      {queue.accounts.map((account) => (
                        <option key={account.platform_account_id} value={account.platform_account_id}>
                          {account.display_name}
                        </option>
                      ))}
                    </select>
                    <AsyncButton
                      disabled={selectedCount === 0}
                      pending={action.isPending("bulk-assign")}
                      pendingLabel={t("publishControlPage.assigning")}
                      onClick={() => void bulkAssign()}
                    >
                      {t("publishControlPage.bulkAssign")}
                    </AsyncButton>
                    <button type="button" onClick={() => setSelectedIds(new Set())}>
                      {t("publishControlPage.clear")}
                    </button>
                  </div>

                  {queueItems.length === 0 ? (
                    <p className="ops-control-empty">{t("publishControlPage.noDraftsInBucket")}</p>
                  ) : (
                    <ul className="ops-control-queue">
                      <li className="ops-control-draft is-head" aria-hidden="true">
                        <span>{t("publishControlPage.select")}</span>
                        <span>{t("publishControlPage.draft")}</span>
                        <span>{t("publishControlPage.status")}</span>
                        <span>{t("publishControlPage.recommended")}</span>
                        <span>{t("publishControlPage.assigned")}</span>
                        <span>{t("publishControlPage.warnings")}</span>
                        <span>{t("publishControlPage.action")}</span>
                      </li>
                      {queueItems.map((item) => (
                        <li className="ops-control-draft" key={item.publish_draft_id}>
                          <input
                            type="checkbox"
                            aria-label={t("publishControlPage.select")}
                            checked={selectedIds.has(item.publish_draft_id)}
                            onChange={() => toggle(item.publish_draft_id)}
                          />
                          <div>
                            <Link href={`/publishing/drafts/${item.publish_draft_id}`}>
                              <strong>{item.title ?? item.publish_draft_id.slice(0, 8)}</strong>
                            </Link>
                            <em>{item.publish_draft_id.slice(0, 8)}</em>
                          </div>
                          <ControlChip label={humanizeStatus(item.status)} tone="muted" />
                          <span>{item.recommended_account_name ?? "—"}</span>
                          <span>{item.assigned_platform_account_id ? item.assigned_platform_account_id.slice(0, 8) : "—"}</span>
                          <span className="ops-control-draft__warn" title={item.warnings[0]}>
                            {item.warnings[0] ?? "—"}
                          </span>
                          <div className="ops-control-draft__actions">
                            <AsyncButton
                              className="ops-control-row__action"
                              disabled={!item.recommended_platform_account_id}
                              pending={action.isPending(`assign-${item.publish_draft_id}`)}
                              pendingLabel={t("publishControlPage.assigning")}
                              onClick={() => void assignRecommended(item)}
                            >
                              {t("publishControlPage.useRec")}
                            </AsyncButton>
                            <AsyncButton
                              className="ops-control-row__action"
                              disabled={!item.assigned_platform_account_id}
                              pending={action.isPending(`unassign-${item.publish_draft_id}`)}
                              pendingLabel={t("publishControlPage.updating")}
                              onClick={() => void unassign(item)}
                            >
                              {t("publishControlPage.unassign")}
                            </AsyncButton>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="ops-control-footnote">{t("publishControlPage.assignmentAuthorityFootnote")}</p>
                </ControlPanel>
              </div>

              {showAttention ? (
                <aside className="ops-control-side">
                  {attentionDrafts.length > 0 ? (
                    <ControlPanel title={t("publishControlPage.needsAttentionPanel")}>
                      <ul className="ops-control-attention">
                        {attentionDrafts.map((item) => (
                          <li key={item.publish_draft_id}>
                            <div>
                              <strong>{item.title ?? item.publish_draft_id.slice(0, 8)}</strong>
                              <em>
                                {humanizeStatus(item.status)} · {item.recommended_account_name ?? t("publishControlPage.noRecommendation")}
                              </em>
                            </div>
                            <Link href={`/publishing/drafts/${item.publish_draft_id}`}>{t("publishControlPage.openDraft")}</Link>
                          </li>
                        ))}
                      </ul>
                    </ControlPanel>
                  ) : null}

                  {holdAccounts.length > 0 ? (
                    <ControlPanel title={t("publishControlPage.accountAttention")}>
                      <ul className="ops-control-attention">
                        {holdAccounts.map((account) => (
                          <li key={account.platform_account_id}>
                            <div>
                              <strong>{account.display_name}</strong>
                              <em>
                                {humanizeStatus(account.health_status)}
                                {account.is_on_hold ? ` · ${t("publishControlPage.onHold")}` : ""}
                              </em>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </ControlPanel>
                  ) : null}

                  {queue.scheduled_drafts.length > 0 ? (
                    <ControlPanel title={t("publishControlPage.scheduledByAccount")}>
                      <ul className="ops-control-attention">
                        {queue.scheduled_drafts.map((item) => (
                          <li key={item.publish_draft_id}>
                            <div>
                              <strong>{item.title ?? item.publish_draft_id.slice(0, 8)}</strong>
                              <em>{humanizeStatus(item.status)}</em>
                            </div>
                            <Link href={`/publishing/drafts/${item.publish_draft_id}`}>{t("publishControlPage.openDraft")}</Link>
                          </li>
                        ))}
                      </ul>
                    </ControlPanel>
                  ) : null}

                  <ControlPanel title={t("publishControlPage.routingRules")}>
                    {rules.length === 0 ? (
                      <p className="ops-control-empty">{t("publishControlPage.noRoutingRules")}</p>
                    ) : (
                      <ul className="ops-control-rules">
                        {rules.map((rule) => (
                          <li key={rule.id}>
                            <strong>{rule.rule_name}</strong>
                            <span>
                              {humanizeStatus(rule.status)} · {t("publishControlPage.priority")} {rule.priority}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </ControlPanel>
                </aside>
              ) : (
                <aside className="ops-control-side">
                  <ControlPanel title={t("publishControlPage.routingRules")}>
                    {rules.length === 0 ? (
                      <p className="ops-control-empty">{t("publishControlPage.noRoutingRules")}</p>
                    ) : (
                      <ul className="ops-control-rules">
                        {rules.map((rule) => (
                          <li key={rule.id}>
                            <strong>{rule.rule_name}</strong>
                            <span>
                              {humanizeStatus(rule.status)} · {t("publishControlPage.priority")} {rule.priority}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </ControlPanel>
                </aside>
              )}
            </section>
          </>
        ) : null}
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
