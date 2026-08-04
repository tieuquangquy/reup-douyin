"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchPublishHandoffs } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { PublishHandoff } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone, type OpsTone } from "../ops-console/OpsShared";

function HandoffKpi({ label, value, detail, tone = "muted" }: { label: string; value: string; detail: string; tone?: OpsTone }) {
  return (
    <article className={`ops-handoffs-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function HandoffPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-handoffs-panel">
      <div className="ops-handoffs-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-handoffs-panel__body">{children}</div>
    </section>
  );
}

export function PublishHandoffsIndexPage() {
  const t = useT();
  const [handoffs, setHandoffs] = useState<PublishHandoff[]>([]);
  const [total, setTotal] = useState(0);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = loadedAt ? "refresh" : "initial";
    try {
      await request.run(() => fetchPublishHandoffs(100), (payload) => {
        setHandoffs(payload.items);
        setTotal(payload.total_count);
        setLoadedAt(new Date().toISOString());
      }, mode);
      if (mode === "refresh") notify({ id: "publish-handoffs-refresh", message: "Publish handoffs refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "publish-handoffs-refresh", message: err instanceof Error ? err.message : t("opsPublishHandoffs.loadError"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const needsAttention = useMemo(
    () => handoffs.filter((item) => item.status === "FAILED_NEEDS_ATTENTION"),
    [handoffs]
  );
  const ready = handoffs.filter((item) => item.status === "READY_FOR_OPERATOR" || item.status === "ACCEPTED").length;
  const hasAttention = needsAttention.length > 0;

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  if (!loadedAt && !request.error) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsPublishHandoffs.description")} title={t("opsPublishHandoffs.title")}>
        <AsyncContentBoundary skeletonVariant="table" loadingLabel={t("opsPublishHandoffs.loadingDetail")} status="loading"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  if (request.error && !loadedAt) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsPublishHandoffs.description")} title={t("opsPublishHandoffs.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("opsPublishHandoffs.unavailableTitle")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="table" status="error"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  return (
    <OperatorStudioShell actions={refreshAction} description={t("opsPublishHandoffs.description")} title={t("opsPublishHandoffs.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="table" status="success">
      <main className="ops-page ops-handoffs-page">

        <div className="ops-handoffs-freshness">
          <p>
            {t("opsPublishHandoffs.loadedAt")}{" "}
            {loadedAt ? <time dateTime={loadedAt}>{formatDateTime(loadedAt)}</time> : "—"}
          </p>
        </div>

        <section className="ops-handoffs-kpis" aria-label={t("opsPublishHandoffs.summary")}>
          <HandoffKpi label={t("opsPublishHandoffs.handoffRecords")} value={String(total)} detail={t("opsPublishHandoffs.handoffRecordsDetail")} tone="good" />
          <HandoffKpi label={t("opsPublishHandoffs.ready")} value={String(ready)} detail={t("opsPublishHandoffs.readyDetail")} tone="good" />
          <HandoffKpi
            label={t("opsPublishHandoffs.needsAttention")}
            value={String(needsAttention.length)}
            detail={t("opsPublishHandoffs.needsAttentionDetail")}
            tone={needsAttention.length > 0 ? "danger" : "muted"}
          />
        </section>

        <div className="ops-handoffs-toolbar">
          <nav className="ops-handoffs-actions" aria-label={t("opsPublishHandoffs.triage")}>
            <Link href="/publishing/export-packages">{t("opsPublishHandoffs.openPackages")}</Link>
            <Link href="/selection/reup-queue">{t("opsPublishHandoffs.openReupQueue")}</Link>
          </nav>
        </div>

        <section className={`ops-handoffs-main${hasAttention ? " has-attention" : ""}`}>
          <HandoffPanel title={t("opsPublishHandoffs.handoffs")}>
            {handoffs.length === 0 ? (
              <p className="ops-handoffs-empty">{t("opsPublishHandoffs.empty")}</p>
            ) : (
              <ul className="ops-handoffs-sheet">
                <li className="ops-handoffs-row is-head" aria-hidden="true">
                  <span>{t("opsPublishHandoffs.handoff")}</span>
                  <span>{t("opsPublishHandoffs.status")}</span>
                  <span>{t("opsPublishHandoffs.platform")}</span>
                  <span>{t("opsPublishHandoffs.package")}</span>
                  <span>{t("opsPublishHandoffs.readyAt")}</span>
                  <span>{t("opsPublishHandoffs.action")}</span>
                </li>
                {handoffs.map((item) => (
                  <li className={`ops-handoffs-row${item.status === "FAILED_NEEDS_ATTENTION" ? " is-hot" : ""}`} key={item.id}>
                    <strong className="ops-handoffs-row__title" title={item.id}>
                      {t("opsPublishHandoffs.handoff")} {item.id.slice(0, 8)}
                    </strong>
                    <span className={`ops-handoffs-chip tone-${statusTone(item.status)}`}>{item.status}</span>
                    <span>{item.target_platform}</span>
                    <Link href={`/publishing/export-packages/${item.export_package_id}`} title={item.export_package_id}>
                      {item.export_package_id.slice(0, 8)}
                    </Link>
                    <span>{formatDateTime(item.ready_at)}</span>
                    <Link className="ops-handoffs-row__link" href={`/publishing/publish-handoffs/${item.id}`}>
                      {t("opsPublishHandoffs.open")}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <p className="ops-handoffs-footnote">{t("opsPublishHandoffs.noPlatformApi")}</p>
          </HandoffPanel>

          {hasAttention ? (
            <HandoffPanel title={t("opsPublishHandoffs.attention")}>
              <ul className="ops-handoffs-attention">
                {needsAttention.map((item) => (
                  <li key={item.id}>
                    <div>
                      <strong>
                        {t("opsPublishHandoffs.handoff")} {item.id.slice(0, 8)}
                      </strong>
                      <em>
                        {item.status} · {item.target_platform}
                      </em>
                    </div>
                    <Link href={`/publishing/publish-handoffs/${item.id}`}>{t("opsPublishHandoffs.open")}</Link>
                  </li>
                ))}
              </ul>
            </HandoffPanel>
          ) : null}
        </section>
      </main>
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}
