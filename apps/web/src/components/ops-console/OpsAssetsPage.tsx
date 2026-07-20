"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { fetchOperationalMetrics } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { OperationalMetrics, OpsAssetReuseSummary } from "../../types/operations";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { OpsState, formatDateTime, type OpsTone } from "./OpsShared";

type AssetRow = OpsAssetReuseSummary & {
  total: number;
  staleShare: number;
  needsCurrent: boolean;
};

function buildAssetRows(items: OpsAssetReuseSummary[]): AssetRow[] {
  return items
    .map((item) => {
      const total = item.current_count + item.historical_count;
      const staleShare = total > 0 ? item.historical_count / total : 0;
      return {
        ...item,
        total,
        staleShare,
        needsCurrent: item.current_count === 0 && total > 0,
      };
    })
    .sort((a, b) => {
      if (a.needsCurrent !== b.needsCurrent) return a.needsCurrent ? -1 : 1;
      return b.total - a.total || a.asset_type.localeCompare(b.asset_type);
    });
}

function AssetsKpi({
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
    <article className={`ops-assets-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function AssetsPanel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="ops-assets-panel">
      <div className="ops-assets-panel__head">
        <h2>{title}</h2>
        {action}
      </div>
      <div className="ops-assets-panel__body">{children}</div>
    </section>
  );
}

export function OpsAssetsPage() {
  const t = useT();
  const [metrics, setMetrics] = useState<OperationalMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setMetrics(await fetchOperationalMetrics());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsAssets.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const rows = buildAssetRows(metrics?.asset_reuse_by_type ?? []);
  const currentTotal = rows.reduce((sum, row) => sum + row.current_count, 0);
  const historicalTotal = rows.reduce((sum, row) => sum + row.historical_count, 0);
  const needsCurrentRows = rows.filter((row) => row.needsCurrent);
  const needsCurrentCount = needsCurrentRows.length;

  const refreshAction = (
    <TopbarRefreshButton busy={loading && Boolean(metrics)} disabled={loading && !metrics} onClick={() => void load()} />
  );

  if (loading && !metrics) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsAssets.description")} title={t("opsAssets.title")}>
        <OpsState title={t("opsAssets.loadingTitle")} detail={t("opsAssets.loadingDetail")} />
      </OpsConsoleShell>
    );
  }

  if (error && !metrics) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsAssets.description")} title={t("opsAssets.title")}>
        <OpsState title={t("opsAssets.unavailableTitle")} detail={error} retry={() => void load()} />
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsAssets.description")} title={t("opsAssets.title")}>
      <main className="ops-page ops-assets-page">
        {error ? <div className="inline-error">{error}</div> : null}

        <p className="ops-assets-freshness">
          {t("opsAssets.metricsGenerated")}{" "}
          <time dateTime={metrics?.generated_at}>{formatDateTime(metrics?.generated_at)}</time>
        </p>

        <section className="ops-assets-kpis" aria-label={t("opsAssets.title")}>
          <AssetsKpi
            label={t("opsAssets.currentAssets")}
            value={String(currentTotal)}
            detail={t("opsAssets.isCurrentRecords")}
            tone="good"
          />
          <AssetsKpi
            label={t("opsAssets.historicalAssets")}
            value={String(historicalTotal)}
            detail={t("opsAssets.olderVersionsRetained")}
            tone="muted"
          />
          <AssetsKpi
            label={t("opsAssets.assetTypes")}
            value={String(rows.length)}
            detail={t("opsAssets.trackedInDbMetrics")}
            tone="muted"
          />
          <AssetsKpi
            label={t("opsAssets.needsCurrent")}
            value={String(needsCurrentCount)}
            detail={t("opsAssets.needsCurrentDetail")}
            tone={needsCurrentCount > 0 ? "warn" : "good"}
          />
        </section>

        <div className="ops-assets-toolbar">
          <nav className="ops-assets-actions" aria-label={t("opsAssets.triage")}>
            <Link href="/ops/health">{t("opsAssets.openHealth")}</Link>
            <Link href="/ops/tools">{t("opsAssets.openTools")}</Link>
          </nav>
        </div>

        <section className={`ops-assets-main${needsCurrentRows.length > 0 ? " has-attention" : ""}`}>
          <AssetsPanel title={t("opsAssets.byType")}>
            {rows.length === 0 ? (
              <p className="ops-assets-empty">{t("opsAssets.noMediaAssetsRecorded")}</p>
            ) : (
              <ul className="ops-assets-by-type">
                <li className="ops-assets-row is-head" aria-hidden="true">
                  <span>{t("opsAssets.assetType")}</span>
                  <span>{t("opsAssets.current")}</span>
                  <span>{t("opsAssets.historical")}</span>
                  <span>{t("opsAssets.staleShare")}</span>
                  <span>{t("opsAssets.signal")}</span>
                </li>
                {rows.map((row) => (
                  <li className={`ops-assets-row${row.needsCurrent ? " is-gap" : ""}`} key={row.asset_type}>
                    <code>{row.asset_type}</code>
                    <strong>{row.current_count}</strong>
                    <span>{row.historical_count}</span>
                    <span>{Math.round(row.staleShare * 100)}%</span>
                    <span className={`ops-assets-signal tone-${row.needsCurrent ? "warn" : "good"}`}>
                      {row.needsCurrent ? t("opsAssets.noCurrentAsset") : t("opsAssets.currentExists")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="ops-assets-footnote">{t("opsAssets.fileScanDeferred")}</p>
          </AssetsPanel>

          {needsCurrentRows.length > 0 ? (
            <AssetsPanel title={t("opsAssets.attention")}>
              <ul className="ops-assets-attention">
                {needsCurrentRows.map((row) => (
                  <li key={row.asset_type}>
                    <code>{row.asset_type}</code>
                    <span>
                      {t("opsAssets.historical")} <strong>{row.historical_count}</strong>
                    </span>
                  </li>
                ))}
              </ul>
            </AssetsPanel>
          ) : null}
        </section>
      </main>
    </OpsConsoleShell>
  );
}
