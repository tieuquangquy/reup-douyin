"use client";

import { useEffect, useState } from "react";
import { createPublishHandoff, fetchExportPackage } from "../../lib/api";
import type { ExportPackage, PublishHandoff } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { OpsDetailPanel, OpsDetailSection, OpsItemCard, OpsMetadataList, OpsStatePanel, OpsSummaryCards, statusTone, type OpsItemAction, type OpsSummaryCardItem } from "../ops-console/OpsShared";

export function ExportPackageByIdPage({ packageId }: { packageId: string }) {
  const [item, setItem] = useState<ExportPackage | null>(null);
  const [createdHandoff, setCreatedHandoff] = useState<PublishHandoff | null>(null);
  const [loading, setLoading] = useState(true);
  const [creatingHandoff, setCreatingHandoff] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setItem(await fetchExportPackage(packageId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Export Package");
    } finally {
      setLoading(false);
    }
  }

  async function createHandoff() {
    setCreatingHandoff(true);
    setError(null);
    setActionMessage(null);
    try {
      const handoff = await createPublishHandoff({
        export_package_id: packageId,
        target_platform: "FACEBOOK_REELS",
        operator_note: "Operator created a Publish Handoff from the Export Package detail page."
      });
      setCreatedHandoff(handoff);
      setActionMessage(`Publish Handoff created: ${handoff.id}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create Publish Handoff");
    } finally {
      setCreatingHandoff(false);
    }
  }

  useEffect(() => {
    void load();
  }, [packageId]);

  return (
    <OperatorStudioShell
      actions={
        <>
          <TopbarRefreshButton busy={loading && Boolean(item)} disabled={loading && !item} onClick={() => void load()} />
          <a href="/publishing/export-packages">All Export Packages</a>
          <a href="/selection/reup-queue">Reup Queue</a>
          {item ? (
            <button disabled={creatingHandoff || item.item_count === 0 || item.status === "CANCELLED"} onClick={() => void createHandoff()} type="button">
              {creatingHandoff ? "Creating..." : "Create Publish Handoff"}
            </button>
          ) : null}
        </>
      }
      description="Inspect package contents before creating or following a Publish Handoff. Export Packages are inspectable artifacts, not external publishing automation."
      title="Export Package detail"
    >
      {loading ? <OpsStatePanel detail="Loading package contents, manifest, and linked handoff references." title="Loading Export Package" variant="loading" /> : null}
      {!loading && (error || !item) ? (
        <OpsStatePanel
          action={<button type="button" onClick={() => void load()}>Retry</button>}
          detail={error ?? "Export Package not found"}
          title="Could not load Export Package"
          variant="error"
        />
      ) : null}
      {!loading && item ? (
        <>
          {actionMessage ? <p className="success-message">{actionMessage}</p> : null}
          {createdHandoff ? <p><a href={`/publishing/publish-handoffs/${createdHandoff.id}`}>Open created Publish Handoff</a></p> : null}
          {error ? <div className="inline-error">{error}</div> : null}
          <OpsSummaryCards cards={summaryCardsForPackage(item)} title="Package state summary" />

          <OpsDetailPanel title="Package detail panel">
            <OpsDetailSection title="Overview">
              <OpsMetadataList items={[
                { label: "Package id", value: item.id },
                { label: "Status", value: item.status },
                { label: "Workspace", value: item.workspace_id },
                { label: "Created", value: formatDateTime(item.created_at) },
                { label: "Ready", value: formatDateTime(item.ready_at) },
                { label: "Operator note", value: item.operator_note ?? "None" },
                { label: "Publish handoffs", value: item.publish_handoff_ids.length ? item.publish_handoff_ids.map((handoffId) => <a href={`/publishing/publish-handoffs/${handoffId}`} key={handoffId}>{handoffId}</a>) : "None" }
              ]} />
            </OpsDetailSection>

            <OpsDetailSection title="Outputs / Downstream artifacts">
              <div className="operator-quick-grid">
                {item.items.map((packageItem) => (
                  <PackageContentCard item={packageItem} key={packageItem.id} />
                ))}
              </div>
            </OpsDetailSection>

            <OpsDetailSection collapsed title="Diagnostics">
              <pre>{JSON.stringify({ manifest_json: item.manifest_json, diagnostics_json: item.diagnostics_json }, null, 2)}</pre>
            </OpsDetailSection>
          </OpsDetailPanel>
        </>
      ) : null}
    </OperatorStudioShell>
  );
}

function PackageContentCard({ item }: { item: ExportPackage["items"][number] }) {
  const actions: OpsItemAction[] = [
    { key: "transcript", label: "Open transcript editor", href: `/production/transcript-editor/${item.source_video_id}`, tone: "secondary" },
    { key: "final-review", label: "Open final review", href: `/production/final-review/${item.source_video_id}`, tone: "secondary" }
  ];

  return (
    <OpsItemCard
      actions={actions}
      metadata={[
        { label: "Queue item", value: item.reup_queue_item_id },
        { label: "Candidate", value: item.video_candidate_id },
        { label: "Source video", value: item.source_video_id }
      ]}
      preview={<strong>{item.item_status}</strong>}
      statusLabel={item.item_status}
      statusTone="good"
      title={`${item.item_status} / ${item.source_video_id}`}
    >
      <p>Package content row preserved from the originating Reup Queue item.</p>
    </OpsItemCard>
  );
}

function summaryCardsForPackage(item: ExportPackage): OpsSummaryCardItem[] {
  return [
    { key: "items", label: "Packaged items", value: item.item_count, description: "Rows included in this durable package.", tone: "good" },
    { key: "handoffs", label: "Publish handoffs", value: item.publish_handoff_ids.length, description: "Manual downstream handoff records linked to this package.", tone: "good" },
    { key: "status", label: "Package status", value: item.status, description: "Current package lifecycle state.", tone: statusTone(item.status) },
    { key: "automation", label: "Publish automation", value: "Not triggered", description: "Creating a handoff does not call platform APIs.", tone: "muted" }
  ];
}

function formatDateTime(value: string | null): string {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
