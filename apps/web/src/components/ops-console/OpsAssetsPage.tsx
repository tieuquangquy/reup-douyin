"use client";

import { useEffect, useState } from "react";
import { fetchOperationalMetrics } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { OperationalMetrics } from "../../types/operations";
import { OpsMetricCard, OpsPageHeader, OpsPanel, OpsState } from "./OpsShared";

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

  const currentTotal = metrics?.asset_reuse_by_type.reduce((total, item) => total + item.current_count, 0) ?? 0;
  const historicalTotal = metrics?.asset_reuse_by_type.reduce((total, item) => total + item.historical_count, 0) ?? 0;

  if (loading && !metrics) return <OpsState title={t("opsAssets.loadingTitle")} detail={t("opsAssets.loadingDetail")} />;
  if (error && !metrics) return <OpsState title={t("opsAssets.unavailableTitle")} detail={error} retry={() => void load()} />;

  return (
    <main className="ops-page">
      <OpsPageHeader title={t("opsAssets.title")} description={t("opsAssets.description")} actions={<button type="button" onClick={() => void load()}>{t("common.refresh")}</button>} />
      {error ? <div className="inline-error">{error}</div> : null}

      <section className="health-overview-grid">
        <OpsMetricCard label={t("opsAssets.currentAssets")} value={String(currentTotal)} detail={t("opsAssets.isCurrentRecords")} tone="good" />
        <OpsMetricCard label={t("opsAssets.historicalAssets")} value={String(historicalTotal)} detail={t("opsAssets.olderVersionsRetained")} />
        <OpsMetricCard label={t("opsAssets.assetTypes")} value={String(metrics?.asset_reuse_by_type.length ?? 0)} detail={t("opsAssets.trackedInDbMetrics")} />
        <OpsMetricCard label={t("opsAssets.missingOrCorrupt")} value={t("opsAssets.notScanned")} detail={t("opsAssets.requiresFileValidation")} />
      </section>

      <section className="ops-grid">
        <OpsPanel title={t("opsAssets.assetCurrentStaleByType")}>
          <table className="health-table">
            <thead>
              <tr><th>{t("opsAssets.assetType")}</th><th>{t("opsAssets.current")}</th><th>{t("opsAssets.historical")}</th><th>{t("opsAssets.signal")}</th></tr>
            </thead>
            <tbody>
              {metrics?.asset_reuse_by_type.length === 0 ? <tr><td colSpan={4}>{t("opsAssets.noMediaAssetsRecorded")}</td></tr> : null}
              {metrics?.asset_reuse_by_type.map((item) => (
                <tr key={item.asset_type}>
                  <td>{item.asset_type}</td>
                  <td>{item.current_count}</td>
                  <td>{item.historical_count}</td>
                  <td>{item.current_count === 0 ? t("opsAssets.noCurrentAsset") : t("opsAssets.currentExists")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </OpsPanel>

        <OpsPanel title={t("opsAssets.operationalNotes")}>
          <ul className="compact-list">
            <li>{t("opsAssets.noteManifest")}</li>
            <li>{t("opsAssets.noteLocalStorage")}</li>
            <li>{t("opsAssets.noteCorrupt")}</li>
          </ul>
        </OpsPanel>
      </section>
    </main>
  );
}
