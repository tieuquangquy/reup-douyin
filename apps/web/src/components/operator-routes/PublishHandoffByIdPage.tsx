"use client";

import { useEffect, useState } from "react";
import { fetchPublishHandoff } from "../../lib/api";
import type { PublishHandoff } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { OpsDetailPanel, OpsDetailSection, OpsMetadataList, OpsStatePanel, OpsSummaryCards, statusTone, type OpsSummaryCardItem } from "../ops-console/OpsShared";

export function PublishHandoffByIdPage({ handoffId }: { handoffId: string }) {
  const [handoff, setHandoff] = useState<PublishHandoff | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setHandoff(await fetchPublishHandoff(handoffId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Publish Handoff");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [handoffId]);

  return (
    <OperatorStudioShell
      actions={
        <>
          <TopbarRefreshButton busy={loading && Boolean(handoff)} disabled={loading && !handoff} onClick={() => void load()} />
          <a href="/publishing/publish-handoffs">All Publish Handoffs</a>
          {handoff ? <a href={`/publishing/export-packages/${handoff.export_package_id}`}>Open Export Package</a> : null}
          <a href="/selection/reup-queue">Reup Queue</a>
        </>
      }
      description="Inspect handoff payloads before manual downstream publishing. Publish Handoff records do not call platform APIs or auto-publish."
      title="Publish Handoff detail"
    >
      {loading ? <OpsStatePanel detail="Loading manual handoff payload and diagnostics." title="Loading Publish Handoff" variant="loading" /> : null}
      {!loading && (error || !handoff) ? (
        <OpsStatePanel
          action={<button type="button" onClick={() => void load()}>Retry</button>}
          detail={error ?? "Publish Handoff not found"}
          title="Could not load Publish Handoff"
          variant="error"
        />
      ) : null}
      {!loading && handoff ? (
        <>
          <OpsSummaryCards cards={summaryCardsForHandoff(handoff)} title="Handoff state summary" />

          <OpsDetailPanel title="Handoff detail panel">
            <OpsDetailSection title="Overview">
              <OpsMetadataList items={[
                { label: "Handoff id", value: handoff.id },
                { label: "Status", value: handoff.status },
                { label: "Export Package", value: <a href={`/publishing/export-packages/${handoff.export_package_id}`}>{handoff.export_package_id}</a> },
                { label: "Target platform", value: handoff.target_platform },
                { label: "Workspace", value: handoff.workspace_id },
                { label: "Operator note", value: handoff.operator_note ?? "None" }
              ]} />
            </OpsDetailSection>

            <OpsDetailSection title="Workflow / Lifecycle">
              <OpsMetadataList items={[
                { label: "Created at", value: formatDateTime(handoff.created_at) },
                { label: "Ready at", value: formatDateTime(handoff.ready_at) },
                { label: "Accepted at", value: formatDateTime(handoff.accepted_at) },
                { label: "Failed at", value: formatDateTime(handoff.failed_at) },
                { label: "Cancelled at", value: formatDateTime(handoff.cancelled_at) },
                { label: "Publish automation", value: "Not triggered here" }
              ]} />
            </OpsDetailSection>

            <OpsDetailSection title="Outputs / Downstream artifacts" description="Payload is safe to inspect and copy for manual downstream work. Secrets, cookies, and credentials must not appear here.">
              <pre>{JSON.stringify(handoff.payload_json ?? {}, null, 2)}</pre>
            </OpsDetailSection>

            <OpsDetailSection collapsed title="Diagnostics">
              <pre>{JSON.stringify(handoff.diagnostics_json ?? {}, null, 2)}</pre>
            </OpsDetailSection>
          </OpsDetailPanel>
        </>
      ) : null}
    </OperatorStudioShell>
  );
}

function summaryCardsForHandoff(handoff: PublishHandoff): OpsSummaryCardItem[] {
  return [
    { key: "status", label: "Handoff status", value: handoff.status, description: "Current manual handoff lifecycle state.", tone: statusTone(handoff.status) },
    { key: "target", label: "Target platform", value: handoff.target_platform, description: "Destination selected for manual publishing work.", tone: "good" },
    { key: "ready", label: "Ready at", value: formatDateTime(handoff.ready_at), description: "Payload readiness timestamp.", tone: "good" },
    { key: "automation", label: "Publish automation", value: "Not triggered", description: "No external platform API call is made from this view.", tone: "muted" }
  ];
}

function formatDateTime(value: string | null): string {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
