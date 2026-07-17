"use client";

import { useEffect, useState } from "react";
import { fetchPublishHandoffs } from "../../lib/api";
import type { PublishHandoff } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PageShell } from "../app-shell/PageShell";
import { OpsItemCard, OpsStatePanel, OpsSummaryCards, statusTone, type OpsItemAction, type OpsSummaryCardItem } from "../ops-console/OpsShared";

export function PublishHandoffsIndexPage() {
  const [handoffs, setHandoffs] = useState<PublishHandoff[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchPublishHandoffs(100);
      setHandoffs(payload.items);
      setTotal(payload.total_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Publish Handoffs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const summaryCards: OpsSummaryCardItem[] = [
    { key: "total", label: "Handoff records", value: total, description: "Manual handoff artifacts available for inspection.", tone: "good" },
    { key: "ready", label: "Ready", value: handoffs.filter((item) => item.status === "READY_FOR_OPERATOR" || item.status === "ACCEPTED").length, description: "Handoffs prepared for manual downstream work.", tone: "good" },
    { key: "failed", label: "Needs attention", value: handoffs.filter((item) => item.status === "FAILED_NEEDS_ATTENTION").length, description: "Handoffs requiring operator review.", tone: "danger" },
    { key: "automation", label: "Publish automation", value: "None", description: "These records do not call external platform APIs.", tone: "muted" }
  ];

  return (
    <OperatorStudioShell
      actions={<button type="button" onClick={() => void load()}>Refresh</button>}
      description="Inspect operator-controlled Publish Handoff records created from Export Packages. Handoffs are manual artifacts, not publish automation."
      title="Publish Handoffs"
    >
      {loading ? <OpsStatePanel detail="Loading manual handoff records created from Export Packages." title="Loading Publish Handoffs" variant="loading" /> : null}
      {!loading && error ? (
        <OpsStatePanel
          action={<button type="button" onClick={() => void load()}>Retry</button>}
          detail={error}
          title="Could not load Publish Handoffs"
          variant="error"
        />
      ) : null}
      {!loading && !error ? (
        <PageShell
          actions={
            <>
              <a href="/publishing/export-packages">Export Packages</a>
              <a href="/selection/reup-queue">Reup Queue</a>
            </>
          }
          description={`${total} handoff record(s). Handoffs are payloads for manual downstream publishing, not external automation.`}
          title="Publish Handoff index"
        >
          <OpsSummaryCards cards={summaryCards} title="Publish Handoff summary" />
          <div className="operator-quick-grid">
            {handoffs.length === 0 ? (
              <OpsStatePanel detail="Create a handoff from an Export Package after inspecting package contents." title="No Publish Handoffs yet" variant="empty" />
            ) : null}
            {handoffs.map((item) => (
              <PublishHandoffCard item={item} key={item.id} />
            ))}
          </div>
        </PageShell>
      ) : null}
    </OperatorStudioShell>
  );
}

function PublishHandoffCard({ item }: { item: PublishHandoff }) {
  const actions: OpsItemAction[] = [
    { key: "open", label: "Open handoff", href: `/publishing/publish-handoffs/${item.id}`, tone: "primary" },
    { key: "package", label: "Open Export Package", href: `/publishing/export-packages/${item.export_package_id}`, tone: "secondary" }
  ];

  return (
    <OpsItemCard
      actions={actions}
      metadata={[
        { label: "Target platform", value: item.target_platform },
        { label: "Export Package", value: item.export_package_id.slice(0, 8) },
        { label: "Ready", value: formatDateTime(item.ready_at) }
      ]}
      preview={<strong>{item.target_platform}</strong>}
      statusLabel={item.status}
      statusTone={statusTone(item.status)}
      title={`Publish Handoff ${item.id.slice(0, 8)}`}
    >
      <p>Manual handoff payload for downstream publishing work. No platform API call is triggered here.</p>
    </OpsItemCard>
  );
}

function formatDateTime(value: string | null): string {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
