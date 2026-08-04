"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchExportPackages } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { ExportPackage } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone, type OpsTone } from "../ops-console/OpsShared";

function ExportKpi({ label, value, detail, tone = "muted" }: { label: string; value: string; detail: string; tone?: OpsTone }) {
  return (
    <article className={`ops-export-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function ExportPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-export-panel">
      <div className="ops-export-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-export-panel__body">{children}</div>
    </section>
  );
}

export function ExportPackagesIndexPage() {
  const t = useT();
  const [packages, setPackages] = useState<ExportPackage[]>([]);
  const [total, setTotal] = useState(0);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = loadedAt ? "refresh" : "initial";
    try {
      await request.run(() => fetchExportPackages(100), (payload) => {
        setPackages(payload.items);
        setTotal(payload.total_count);
        setLoadedAt(new Date().toISOString());
      }, mode);
      if (mode === "refresh") notify({ id: "export-packages-refresh", message: "Export packages refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "export-packages-refresh", message: err instanceof Error ? err.message : t("opsExportPackages.loadError"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const needsAttention = useMemo(
    () => packages.filter((item) => item.status === "FAILED_NEEDS_ATTENTION"),
    [packages]
  );
  const linkedHandoffs = packages.reduce((count, item) => count + item.publish_handoff_ids.length, 0);
  const cancelled = packages.filter((item) => item.status === "CANCELLED").length;
  const hasAttention = needsAttention.length > 0;

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  if (!loadedAt && !request.error) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsExportPackages.description")} title={t("opsExportPackages.title")}>
        <AsyncContentBoundary skeletonVariant="table" loadingLabel={t("opsExportPackages.loadingDetail")} status="loading"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  if (request.error && !loadedAt) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsExportPackages.description")} title={t("opsExportPackages.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("opsExportPackages.unavailableTitle")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="table" status="error"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  return (
    <OperatorStudioShell actions={refreshAction} description={t("opsExportPackages.description")} title={t("opsExportPackages.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="table" status="success">
      <main className="ops-page ops-export-page">

        <div className="ops-export-freshness">
          <p>
            {t("opsExportPackages.loadedAt")}{" "}
            {loadedAt ? <time dateTime={loadedAt}>{formatDateTime(loadedAt)}</time> : "—"}
          </p>
        </div>

        <section className="ops-export-kpis" aria-label={t("opsExportPackages.summary")}>
          <ExportKpi label={t("opsExportPackages.packageRecords")} value={String(total)} detail={t("opsExportPackages.packageRecordsDetail")} tone="good" />
          <ExportKpi label={t("opsExportPackages.linkedHandoffs")} value={String(linkedHandoffs)} detail={t("opsExportPackages.linkedHandoffsDetail")} tone="good" />
          <ExportKpi
            label={t("opsExportPackages.needsAttention")}
            value={String(needsAttention.length)}
            detail={t("opsExportPackages.needsAttentionDetail")}
            tone={needsAttention.length > 0 ? "danger" : "muted"}
          />
          <ExportKpi label={t("opsExportPackages.cancelled")} value={String(cancelled)} detail={t("opsExportPackages.cancelledDetail")} tone="muted" />
        </section>

        <div className="ops-export-toolbar">
          <nav className="ops-export-actions" aria-label={t("opsExportPackages.triage")}>
            <Link href="/selection/reup-queue">{t("opsExportPackages.openReupQueue")}</Link>
            <Link href="/publishing/publish-handoffs">{t("opsExportPackages.openHandoffs")}</Link>
          </nav>
        </div>

        <section className={`ops-export-main${hasAttention ? " has-attention" : ""}`}>
          <ExportPanel title={t("opsExportPackages.packages")}>
            {packages.length === 0 ? (
              <p className="ops-export-empty">{t("opsExportPackages.empty")}</p>
            ) : (
              <ul className="ops-export-sheet">
                <li className="ops-export-row is-head" aria-hidden="true">
                  <span>{t("opsExportPackages.package")}</span>
                  <span>{t("opsExportPackages.status")}</span>
                  <span>{t("opsExportPackages.items")}</span>
                  <span>{t("opsExportPackages.handoffs")}</span>
                  <span>{t("opsExportPackages.created")}</span>
                  <span>{t("opsExportPackages.action")}</span>
                </li>
                {packages.map((item) => (
                  <li className={`ops-export-row${item.status === "FAILED_NEEDS_ATTENTION" ? " is-hot" : ""}`} key={item.id}>
                    <strong className="ops-export-row__title" title={item.id}>
                      {item.label || `${t("opsExportPackages.package")} ${item.id.slice(0, 8)}`}
                    </strong>
                    <span className={`ops-export-chip tone-${statusTone(item.status)}`}>{item.status}</span>
                    <span>{item.item_count}</span>
                    <span>{item.publish_handoff_ids.length}</span>
                    <span>{formatDateTime(item.created_at)}</span>
                    <Link className="ops-export-row__link" href={`/publishing/export-packages/${item.id}`}>
                      {t("opsExportPackages.open")}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <p className="ops-export-footnote">{t("opsExportPackages.noAutoPublish")}</p>
          </ExportPanel>

          {hasAttention ? (
            <ExportPanel title={t("opsExportPackages.attention")}>
              <ul className="ops-export-attention">
                {needsAttention.map((item) => (
                  <li key={item.id}>
                    <div>
                      <strong>{item.label || item.id.slice(0, 8)}</strong>
                      <em>{item.status}</em>
                    </div>
                    <Link href={`/publishing/export-packages/${item.id}`}>{t("opsExportPackages.open")}</Link>
                  </li>
                ))}
              </ul>
            </ExportPanel>
          ) : null}
        </section>
      </main>
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}
