"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useT } from "../../lib/i18n";
import {
  assignPublishDraft,
  bulkAssignPublishDrafts,
  fetchPublishControlQueue,
  fetchRoutingRules,
  unassignPublishDraft,
  updatePlatformAccount
} from "../../lib/api";
import { defaultAssignmentReason, healthTone, queueAttentionCount } from "../../lib/publishControlState";
import { humanizeStatus } from "../../lib/statusLabels";
import type { AccountHealthSummary, PublishControlQueue, PublishQueueItem, RoutingRule } from "../../types/publish-control";

export function PublishControlPlanePage() {
  const t = useT();
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkAccountId, setBulkAccountId] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [queuePayload, rulesPayload] = await Promise.all([fetchPublishControlQueue(), fetchRoutingRules()]);
      setQueue(queuePayload);
      setRules(rulesPayload.rules);
      if (!bulkAccountId && queuePayload.accounts[0]) {
        setBulkAccountId(queuePayload.accounts[0].platform_account_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishControlPage.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  const allDrafts = useMemo(() => [...(queue?.unassigned_drafts ?? []), ...(queue?.assigned_drafts ?? []), ...(queue?.scheduled_drafts ?? [])], [queue]);
  const selectedCount = selectedIds.size;

  async function assignRecommended(item: PublishQueueItem) {
    if (!item.recommended_platform_account_id) return;
    setSavingId(item.publish_draft_id);
    setError(null);
    try {
      await assignPublishDraft(item.publish_draft_id, {
        platform_account_id: item.recommended_platform_account_id,
        reason: defaultAssignmentReason(item),
        assigned_by: "local_operator"
      });
      setMessage("Draft assigned.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to assign draft");
    } finally {
      setSavingId(null);
    }
  }

  async function unassign(item: PublishQueueItem) {
    setSavingId(item.publish_draft_id);
    setError(null);
    try {
      await unassignPublishDraft(item.publish_draft_id);
      setMessage("Draft unassigned.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to unassign draft");
    } finally {
      setSavingId(null);
    }
  }

  async function bulkAssign() {
    if (!bulkAccountId || selectedIds.size === 0) return;
    setSavingId("bulk");
    setError(null);
    try {
      await bulkAssignPublishDrafts({
        publish_draft_ids: Array.from(selectedIds),
        platform_account_id: bulkAccountId,
        reason: "Bulk manual routing from publish control plane",
        assigned_by: "local_operator"
      });
      setSelectedIds(new Set());
      setMessage("Selected drafts assigned.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to bulk assign drafts");
    } finally {
      setSavingId(null);
    }
  }

  async function toggleHold(account: AccountHealthSummary) {
    setSavingId(account.platform_account_id);
    setError(null);
    try {
      await updatePlatformAccount(account.platform_account_id, {
        is_on_hold: !account.is_on_hold,
        hold_reason: account.is_on_hold ? null : "Manual hold from publish control plane"
      });
      setMessage(account.is_on_hold ? "Account hold removed." : "Account placed on hold.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update account hold");
    } finally {
      setSavingId(null);
    }
  }

  function toggle(id: string) {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  }

  if (loading && !queue) {
    return <main className="control-page"><div className="state-panel skeleton">{t("publishControlPage.loading")}</div></main>;
  }

  if (error && !queue) {
    return (
      <main className="control-page">
        <div className="state-panel">
          <h1>{t("publishControlPage.unavailable")}</h1>
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>{t("publishControlPage.retry")}</button>
        </div>
      </main>
    );
  }

  return (
    <main className="control-page">
      <header className="control-header">
        <div>
          <span className="eyebrow">{t("publishControlPage.operations")}</span>
          <h1>{t("publishControlPage.pageTitle")}</h1>
          <p>{t("publishControlPage.pageDesc")}</p>
        </div>
        <button type="button" onClick={() => void load()}>{t("publishControlPage.refresh")}</button>
      </header>

      {error ? <div className="inline-error">{error}</div> : null}
      {message ? <div className="publish-ready-banner">{message}</div> : null}

      {queue ? (
        <>
          <section className="control-overview-grid">
            <Metric label={t("publishControlPage.accountsLabel")} value={queue.accounts.length.toString()} detail={t("publishControlPage.configuredPages")} />
            <Metric label={t("publishControlPage.unassignedLabel")} value={queue.unassigned_drafts.length.toString()} detail={t("publishControlPage.readyDraftsNeedAccount")} />
            <Metric label={t("publishControlPage.assignedLabel")} value={queue.assigned_drafts.length.toString()} detail={t("publishControlPage.readyDraftsRouted")} />
            <Metric label={t("publishControlPage.scheduledLabel")} value={queue.scheduled_drafts.length.toString()} detail={t("publishControlPage.plannedPerAccount")} />
            <Metric label={t("publishControlPage.needsAttention")} value={queue.needs_attention.length.toString()} detail={t("publishControlPage.failedOrBlocked")} />
            <Metric label={t("publishControlPage.routingWarnings")} value={queueAttentionCount(allDrafts).toString()} detail={t("publishControlPage.overrideOrWarning")} />
          </section>

          <section className="control-layout">
            <div className="control-main">
              <Panel title={t("publishControlPage.accountsOverview")}>
                <div className="account-grid">
                  {queue.accounts.map((account) => (
                    <AccountCard key={account.platform_account_id} account={account} saving={savingId === account.platform_account_id} onToggleHold={toggleHold} />
                  ))}
                  {queue.accounts.length === 0 ? <p className="muted">{t("publishControlPage.noAccountsYet")}</p> : null}
                </div>
              </Panel>

              <Panel title={t("publishControlPage.draftRoutingQueue")}>
                <div className="bulk-bar">
                  <strong>{selectedCount} {t("publishControlPage.bulkBarSelected")}</strong>
                  <select value={bulkAccountId} onChange={(event) => setBulkAccountId(event.target.value)}>
                    {queue.accounts.map((account) => (
                      <option key={account.platform_account_id} value={account.platform_account_id}>{account.display_name}</option>
                    ))}
                  </select>
                  <button type="button" disabled={selectedCount === 0 || savingId === "bulk"} onClick={() => void bulkAssign()}>
                    {savingId === "bulk" ? t("publishControlPage.assigning") : t("publishControlPage.bulkAssign")}
                  </button>
                  <button type="button" onClick={() => setSelectedIds(new Set())}>{t("publishControlPage.clear")}</button>
                </div>
                <DraftTable
                  title={t("publishControlPage.unassignedReady")}
                  items={queue.unassigned_drafts}
                  selectedIds={selectedIds}
                  savingId={savingId}
                  onToggle={toggle}
                  onAssignRecommended={assignRecommended}
                  onUnassign={unassign}
                />
                <DraftTable
                  title={t("publishControlPage.assignedReady")}
                  items={queue.assigned_drafts}
                  selectedIds={selectedIds}
                  savingId={savingId}
                  onToggle={toggle}
                  onAssignRecommended={assignRecommended}
                  onUnassign={unassign}
                />
              </Panel>
            </div>

            <aside className="control-side">
              <Panel title={t("publishControlPage.scheduledByAccount")}>
                <DraftMiniList items={queue.scheduled_drafts} empty={t("publishControlPage.noScheduled")} />
              </Panel>
              <Panel title={t("publishControlPage.needsAttentionPanel")}>
                <DraftMiniList items={queue.needs_attention} empty={t("publishControlPage.noBlocked")} />
              </Panel>
              <Panel title={t("publishControlPage.routingRules")}>
                {rules.length === 0 ? <p className="muted">{t("publishControlPage.noRoutingRules")}</p> : null}
                <ul className="compact-list">
                  {rules.map((rule) => (
                    <li key={rule.id}>
                      <strong>{rule.rule_name}</strong>
                      <span>{humanizeStatus(rule.status)} / priority {rule.priority}</span>
                    </li>
                  ))}
                </ul>
              </Panel>
            </aside>
          </section>
        </>
      ) : null}
    </main>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="health-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="health-panel"><h2>{title}</h2>{children}</section>;
}

function AccountCard({ account, saving, onToggleHold }: { account: AccountHealthSummary; saving: boolean; onToggleHold: (account: AccountHealthSummary) => Promise<void> }) {
  const t = useT();
  return (
    <div className="account-card">
      <div>
        <strong>{account.display_name}</strong>
        <span className={`pill ${healthTone(account.health_status)}`}>{humanizeStatus(account.health_status)}</span>
      </div>
      <dl>
        <div><dt>{t("publishControlPage.success")}</dt><dd>{account.success_rate_percent}%</dd></div>
        <div><dt>{t("publishControlPage.assignedCount")}</dt><dd>{account.assigned_draft_count}</dd></div>
        <div><dt>{t("publishControlPage.scheduledCount")}</dt><dd>{account.scheduled_draft_count}</dd></div>
        <div><dt>{t("publishControlPage.reconcileCount")}</dt><dd>{account.needs_reconciliation_count}</dd></div>
      </dl>
      <small>{account.reasons[0] ?? t("publishControlPage.noHealthNote")}</small>
      <button type="button" disabled={saving} onClick={() => void onToggleHold(account)}>
        {saving ? t("publishControlPage.updating") : account.is_on_hold ? t("publishControlPage.removeHold") : t("publishControlPage.putOnHold")}
      </button>
    </div>
  );
}

function DraftTable({
  title,
  items,
  selectedIds,
  savingId,
  onToggle,
  onAssignRecommended,
  onUnassign
}: {
  title: string;
  items: PublishQueueItem[];
  selectedIds: Set<string>;
  savingId: string | null;
  onToggle: (id: string) => void;
  onAssignRecommended: (item: PublishQueueItem) => Promise<void>;
  onUnassign: (item: PublishQueueItem) => Promise<void>;
}) {
  const t = useT();
  return (
    <div className="draft-table-wrap">
      <h3>{title}</h3>
      <table className="health-table">
        <thead>
          <tr><th>{t("publishControlPage.select")}</th><th>{t("publishControlPage.draft")}</th><th>Status</th><th>{t("publishControlPage.recommended")}</th><th>{t("publishControlPage.assigned")}</th><th>{t("publishControlPage.warnings")}</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {items.length === 0 ? <tr><td colSpan={7}>{t("publishControlPage.noDraftsInBucket")}</td></tr> : null}
          {items.map((item) => (
            <tr key={item.publish_draft_id}>
              <td><input type="checkbox" checked={selectedIds.has(item.publish_draft_id)} onChange={() => onToggle(item.publish_draft_id)} /></td>
              <td><strong>{item.title ?? item.publish_draft_id.slice(0, 8)}</strong><small>{item.publish_draft_id.slice(0, 8)}</small></td>
              <td>{humanizeStatus(item.status)}</td>
              <td>{item.recommended_account_name ?? "-"}</td>
              <td>{item.assigned_platform_account_id ? item.assigned_platform_account_id.slice(0, 8) : "-"}</td>
              <td>{item.warnings.length > 0 ? item.warnings[0] : "-"}</td>
              <td className="table-actions">
                <button type="button" disabled={!item.recommended_platform_account_id || savingId === item.publish_draft_id} onClick={() => void onAssignRecommended(item)}>{t("publishControlPage.useRec")}</button>
                <button type="button" disabled={!item.assigned_platform_account_id || savingId === item.publish_draft_id} onClick={() => void onUnassign(item)}>{t("publishControlPage.unassign")}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DraftMiniList({ items, empty }: { items: PublishQueueItem[]; empty: string }) {
  if (items.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="compact-list">
      {items.map((item) => (
        <li key={item.publish_draft_id}>
          <strong>{item.title ?? item.publish_draft_id.slice(0, 8)}</strong>
          <span>{humanizeStatus(item.status)} / {item.recommended_account_name ?? "no recommendation"}</span>
        </li>
      ))}
    </ul>
  );
}
