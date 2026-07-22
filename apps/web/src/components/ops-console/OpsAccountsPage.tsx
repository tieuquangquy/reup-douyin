"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchAllPlatformAccounts, fetchPublishControlQueue } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { PlatformAccount } from "../../types/publish-draft";
import type { PublishControlQueue } from "../../types/publish-control";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone, type OpsTone } from "./OpsShared";

type AccountRow = PlatformAccount & {
  healthStatus: string | null;
  needsAttention: boolean;
};

function formatChipLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function AccountsKpi({
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
    <article className={`ops-accounts-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function AccountsPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-accounts-panel">
      <div className="ops-accounts-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-accounts-panel__body">{children}</div>
    </section>
  );
}

function AccountsChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ops-accounts-chip tone-${tone}`}>{formatChipLabel(label)}</span>;
}

export function OpsAccountsPage() {
  const t = useT();
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = loadedAt ? "refresh" : "initial";
    try {
      await request.run(async () => {
        const [accountPayload, queuePayload] = await Promise.all([fetchAllPlatformAccounts(), fetchPublishControlQueue()]);
        return { accountPayload, queuePayload };
      }, ({ accountPayload, queuePayload }) => {
        setAccounts(accountPayload);
        setQueue(queuePayload);
        setLoadedAt(new Date().toISOString());
      }, mode);
      if (mode === "refresh") notify({ id: "ops-accounts-refresh", message: "Accounts refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "ops-accounts-refresh", message: err instanceof Error ? err.message : t("opsAccounts.unavailableTitle"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const unhealthyIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of queue?.accounts ?? []) {
      if (item.health_status === "UNHEALTHY") ids.add(item.platform_account_id);
    }
    return ids;
  }, [queue]);

  const rows = useMemo<AccountRow[]>(
    () =>
      accounts
        .map((account) => {
          const unhealthy = unhealthyIds.has(account.id);
          return {
            ...account,
            healthStatus: unhealthy ? "UNHEALTHY" : null,
            needsAttention: account.is_on_hold || unhealthy,
          };
        })
        .sort((a, b) => {
          if (a.needsAttention !== b.needsAttention) return a.needsAttention ? -1 : 1;
          return a.display_name.localeCompare(b.display_name);
        }),
    [accounts, unhealthyIds],
  );

  const attentionRows = rows.filter((row) => row.needsAttention);
  const activeCount = accounts.filter((item) => item.status === "ACTIVE").length;
  const onHoldCount = accounts.filter((item) => item.is_on_hold).length;
  const unhealthyCount = unhealthyIds.size;

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  if (!loadedAt && !request.error) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}>
        <AsyncContentBoundary skeletonVariant="list" status="loading"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  if (request.error && !loadedAt) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("opsAccounts.unavailableTitle")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="list" status="error"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsAccounts.description")} title={t("opsAccounts.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="list" status="success">
      <main className="ops-page ops-accounts-page">

        <p className="ops-accounts-freshness">
          {t("opsAccounts.loadedAt")}{" "}
          <time dateTime={loadedAt ?? undefined}>{formatDateTime(loadedAt)}</time>
        </p>

        <section className="ops-accounts-kpis" aria-label={t("opsAccounts.title")}>
          <AccountsKpi
            label={t("opsAccounts.accounts")}
            value={String(accounts.length)}
            detail={t("opsAccounts.configuredRecords")}
            tone="muted"
          />
          <AccountsKpi
            label={t("opsAccounts.active")}
            value={String(activeCount)}
            detail={t("opsAccounts.readyForRouting")}
            tone="good"
          />
          <AccountsKpi
            label={t("opsAccounts.onHold")}
            value={String(onHoldCount)}
            detail={t("opsAccounts.manualHoldFlag")}
            tone={onHoldCount > 0 ? "warn" : "good"}
          />
          <AccountsKpi
            label={t("opsAccounts.unhealthy")}
            value={String(unhealthyCount)}
            detail={t("opsAccounts.healthModelOutput")}
            tone={unhealthyCount > 0 ? "danger" : "good"}
          />
        </section>

        <div className="ops-accounts-toolbar">
          <nav className="ops-accounts-actions" aria-label={t("opsAccounts.triage")}>
            <Link href="/ops/publish-control">{t("opsAccounts.openPublishControl")}</Link>
          </nav>
        </div>

        <section className={`ops-accounts-main${attentionRows.length > 0 ? " has-attention" : ""}`}>
          <AccountsPanel title={t("opsAccounts.platformAccounts")}>
            {rows.length === 0 ? (
              <p className="ops-accounts-empty">{t("opsAccounts.noPlatformAccountsConfigured")}</p>
            ) : (
              <ul className="ops-accounts-sheet">
                <li className="ops-accounts-row is-head" aria-hidden="true">
                  <span>{t("opsAccounts.account")}</span>
                  <span>{t("opsAccounts.platform")}</span>
                  <span>{t("opsAccounts.status")}</span>
                  <span>{t("opsAccounts.pageId")}</span>
                  <span>{t("opsAccounts.priority")}</span>
                  <span>{t("opsAccounts.hold")}</span>
                  <span>{t("opsAccounts.updated")}</span>
                </li>
                {rows.map((account) => (
                  <li className={`ops-accounts-row${account.needsAttention ? " is-hot" : ""}`} key={account.id}>
                    <strong className="ops-accounts-row__title" title={account.display_name}>
                      {account.display_name}
                    </strong>
                    <span>{account.platform}</span>
                    <span className="ops-accounts-row__badges">
                      <AccountsChip label={account.status} tone={statusTone(account.status)} />
                      {account.healthStatus ? (
                        <AccountsChip label={account.healthStatus} tone="danger" />
                      ) : null}
                    </span>
                    <span className="ops-accounts-row__id" title={account.external_account_id}>
                      {account.external_account_id}
                    </span>
                    <span>{account.priority}</span>
                    <AccountsChip
                      label={account.is_on_hold ? t("opsAccounts.yes") : t("opsAccounts.no")}
                      tone={account.is_on_hold ? "warn" : "muted"}
                    />
                    <time dateTime={account.updated_at}>{formatDateTime(account.updated_at)}</time>
                  </li>
                ))}
              </ul>
            )}
            <p className="ops-accounts-footnote">{t("opsAccounts.editsInPublishControl")}</p>
          </AccountsPanel>

          {attentionRows.length > 0 ? (
            <AccountsPanel title={t("opsAccounts.attention")}>
              <ul className="ops-accounts-attention">
                {attentionRows.map((account) => (
                  <li key={account.id}>
                    <div>
                      <strong>{account.display_name}</strong>
                      <em>
                        {account.is_on_hold ? t("opsAccounts.onHold") : null}
                        {account.is_on_hold && account.healthStatus ? " · " : null}
                        {account.healthStatus ? formatChipLabel(account.healthStatus) : null}
                      </em>
                    </div>
                    <Link href="/ops/publish-control">{t("opsAccounts.openPublishControl")}</Link>
                  </li>
                ))}
              </ul>
            </AccountsPanel>
          ) : null}
        </section>
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
