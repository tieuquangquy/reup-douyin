"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchPublishHandoffs } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PublishHandoff } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchPublishHandoffs(100);
      setHandoffs(payload.items);
      setTotal(payload.total_count);
      setLoadedAt(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsPublishHandoffs.loadError"));
    } finally {
      setLoading(false);
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
    <TopbarRefreshButton busy={loading && handoffs.length > 0} disabled={loading && handoffs.length === 0} onClick={() => void load()} />
  );

  if (loading && handoffs.length === 0 && !error) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsPublishHandoffs.description")} title={t("opsPublishHandoffs.title")}>
        <OpsState title={t("opsPublishHandoffs.loadingTitle")} detail={t("opsPublishHandoffs.loadingDetail")} />
      </OperatorStudioShell>
    );
  }

  if (error && handoffs.length === 0) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("opsPublishHandoffs.description")} title={t("opsPublishHandoffs.title")}>
        <OpsState title={t("opsPublishHandoffs.unavailableTitle")} detail={error} retry={() => void load()} />
      </OperatorStudioShell>
    );
  }

  return (
    <OperatorStudioShell actions={refreshAction} description={t("opsPublishHandoffs.description")} title={t("opsPublishHandoffs.title")}>
      <main className="ops-page ops-handoffs-page">
        {error ? <div className="inline-error">{error}</div> : null}

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
    </OperatorStudioShell>
  );
}
