"use client";

import { useEffect, useState } from "react";
import { fetchExportPackages } from "../../lib/api";
import type { ExportPackage } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PageShell } from "../app-shell/PageShell";
import { OpsItemCard, OpsStatePanel, OpsSummaryCards, statusTone, type OpsItemAction, type OpsSummaryCardItem } from "../ops-console/OpsShared";

export function ExportPackagesIndexPage() {
  const [packages, setPackages] = useState<ExportPackage[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchExportPackages(100);
      setPackages(payload.items);
      setTotal(payload.total_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Export Packages");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const summaryCards: OpsSummaryCardItem[] = [
    { key: "total", label: "Package records", value: total, description: "Durable export containers loaded for review.", tone: "good" },
    { key: "handoffs", label: "Linked handoffs", value: packages.reduce((count, item) => count + item.publish_handoff_ids.length, 0), description: "Manual Publish Handoff records created from packages.", tone: "good" },
    { key: "failed", label: "Needs attention", value: packages.filter((item) => item.status === "FAILED_NEEDS_ATTENTION").length, description: "Packages that require operator inspection.", tone: "danger" },
    { key: "cancelled", label: "Cancelled", value: packages.filter((item) => item.status === "CANCELLED").length, description: "Explicitly cancelled package records.", tone: "muted" }
  ];

  return (
    <OperatorStudioShell
      actions={<button type="button" onClick={() => void load()}>Refresh</button>}
      description="Inspect durable Export Packages generated from READY_TO_EXPORT Reup Queue items. Packages are handoff containers and never publish externally."
      title="Export Packages"
    >
      {loading ? <OpsStatePanel detail="Loading durable package records generated from Reup Queue export-ready rows." title="Loading Export Packages" variant="loading" /> : null}
      {!loading && error ? (
        <OpsStatePanel
          action={<button type="button" onClick={() => void load()}>Retry</button>}
          detail={error}
          title="Could not load Export Packages"
          variant="error"
        />
      ) : null}
      {!loading && !error ? (
        <PageShell
          actions={
            <>
              <a href="/selection/reup-queue">Open Reup Queue</a>
              <a href="/publishing/publish-handoffs">Publish Handoffs</a>
            </>
          }
          description={`${total} package record(s). Packages are inspectable handoff containers; they do not publish externally.`}
          title="Export Package index"
        >
          <OpsSummaryCards cards={summaryCards} title="Export Package summary" />
          <div className="operator-quick-grid">
            {packages.length === 0 ? (
              <OpsStatePanel detail="Select READY_TO_EXPORT rows in Reup Queue and create an Export Package." title="No Export Packages yet" variant="empty" />
            ) : null}
            {packages.map((item) => (
              <ExportPackageCard item={item} key={item.id} />
            ))}
          </div>
        </PageShell>
      ) : null}
    </OperatorStudioShell>
  );
}

function ExportPackageCard({ item }: { item: ExportPackage }) {
  const actions: OpsItemAction[] = [
    { key: "open", label: "Open package", href: `/publishing/export-packages/${item.id}`, tone: "primary" }
  ];

  return (
    <OpsItemCard
      actions={actions}
      metadata={[
        { label: "Items", value: item.item_count },
        { label: "Handoffs", value: item.publish_handoff_ids.length },
        { label: "Created", value: formatDateTime(item.created_at) }
      ]}
      preview={<strong>{item.item_count} item(s)</strong>}
      statusLabel={item.status}
      statusTone={statusTone(item.status)}
      title={item.label || `Export Package ${item.id.slice(0, 8)}`}
    >
      <p>Inspectable package container for manual downstream handoff work.</p>
    </OpsItemCard>
  );
}

function formatDateTime(value: string | null): string {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
