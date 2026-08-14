import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const sharedSource = readFileSync("apps/web/src/components/ops-console/OpsShared.tsx", "utf8");
const globalCssSource = readFileSync("apps/web/src/app/globals.css", "utf8");
const captureSource = readFileSync("apps/web/src/components/capture-inbox/CaptureInboxPage.tsx", "utf8");
const reviewSource = readFileSync("apps/web/src/components/review-board/ReviewBoardPage.tsx", "utf8");
const reupSource = readFileSync("apps/web/src/components/reup-queue/ReupQueuePage.tsx", "utf8");
const exportPackagesIndexSource = readFileSync("apps/web/src/components/operator-routes/ExportPackagesIndexPage.tsx", "utf8");
const exportPackageDetailSource = readFileSync("apps/web/src/components/operator-routes/ExportPackageByIdPage.tsx", "utf8");
const publishHandoffsIndexSource = readFileSync("apps/web/src/components/operator-routes/PublishHandoffsIndexPage.tsx", "utf8");
const publishHandoffDetailSource = readFileSync("apps/web/src/components/operator-routes/PublishHandoffByIdPage.tsx", "utf8");

const requiredPrimitives = [
  "OpsWorkflowContext",
  "OpsNextActionBanner",
  "OpsSummaryCards",
  "OpsFilterBar",
  "OpsItemCard",
  "OpsDetailPanel",
  "OpsDetailSection",
  "OpsBatchActionBar",
  "OpsStatePanel",
  "OpsConsolePage",
  "OpsSection",
  "OpsContentGrid",
  "OpsMainColumn",
  "OpsSideColumn",
  "OpsToolbar",
  "OpsToolbarGroup",
  "OpsEmptyState",
  "OpsStatusBadge",
  "OpsMetadataList",
  "OpsActionRow",
  "statusTone"
];

for (const primitive of requiredPrimitives) {
  assert.match(sharedSource, new RegExp(`export function ${primitive}|export type ${primitive}|export function statusTone`), `Shared Ops Console module must export ${primitive}`);
}

const requiredCssHooks = [
  "ops-console-workflow-context",
  "ops-console-next-action",
  "ops-console-summary-panel",
  "ops-console-filter-bar",
  "ops-console-item-card",
  "ops-console-detail-panel",
  "ops-console-detail-section",
  "ops-console-batch-action-bar",
  "ops-console-state-panel",
  "ops-console-page",
  "ops-console-section",
  "ops-console-content-grid",
  "ops-console-main-column",
  "ops-console-side-column",
  "ops-console-toolbar",
  "ops-console-toolbar-controls",
  "ops-console-toolbar-group"
];

for (const cssHook of requiredCssHooks) {
  assert.match(globalCssSource, new RegExp(`\\.${cssHook}`), `Global CSS must define .${cssHook}`);
}

assert.match(globalCssSource, /\.ops-console-batch-action-bar[\s\S]*position: sticky/, "Shared batch action bar must remain sticky for selected operator work");
assert.match(globalCssSource, /\.ops-console-page[\s\S]*padding:\s*22px var\(--app-content-inset-x\) 28px/, "Ops Console page must breathe below the topbar with shared inset");
assert.match(globalCssSource, /:root\s*\{[^}]*--app-content-inset-x:\s*24px;/, "globals must define shared 24px content inset token");
assert.doesNotMatch(
  globalCssSource,
  /\.ops-console-page\s*\{[^}]*max-width:\s*1480px/,
  "Ops Console page must be full-width (no 1480px content column)"
);
assert.doesNotMatch(
  globalCssSource,
  /\.ops-console-page\s*\{[^}]*margin:\s*0 auto/,
  "Ops Console page must not center a capped column"
);
assert.match(globalCssSource, /\.ops-console-summary-grid[\s\S]*repeat\(auto-fit, minmax\(180px, 1fr\)\)/, "Shared summary grid must prevent vertical card stacking on normal widths");
assert.match(globalCssSource, /@media \(max-width: 1180px\)[\s\S]*\.ops-console-content-grid[\s\S]*grid-template-columns: 1fr/, "Shared content grid must collapse cleanly at tablet widths");
assert.match(sharedSource, /children\?: ReactNode/, "Shared detail panel must allow empty-selection states without placeholder children");

const surfaces = [
  ["Capture Inbox", captureSource],
  ["Review Board", reviewSource],
  ["Reup Queue", reupSource],
  ["Export Packages index", exportPackagesIndexSource],
  ["Export Package detail", exportPackageDetailSource],
  ["Publish Handoffs index", publishHandoffsIndexSource],
  ["Publish Handoff detail", publishHandoffDetailSource]
] as const;

for (const [label, source] of surfaces) {
  assert.match(source, /OperatorStudioShell/, `${label} must use the Operator Studio shell (Phase 5 journey nav)`);
}

for (const [label, source] of surfaces) {
  if (label.includes("detail")) {
    assert.match(source, /OpsDetailPanel/, `${label} must use the shared detail panel`);
  } else if (label === "Capture Inbox" || label === "Review Board" || label === "Reup Queue") {
    // Studio media-tile surfaces: Operator shell + shared Ops primitives (not OpsItemCard lists).
    assert.match(source, /OpsConsolePage|OpsDetailPanel|OpsStatePanel/, `${label} must keep shared Ops Console primitives`);
  } else if (label === "Export Packages index") {
    assert.match(source, /export-packages-page is-v4/, `${label} must use Dispatch bay export-packages shell`);
    assert.doesNotMatch(source, /OpsItemCard|OpsSummaryCards|ops-export-page|export-packages-spectrum/, `${label} must leave legacy Ops / Drafts-clone chrome`);
  } else if (label === "Publish Handoffs index") {
    assert.match(source, /ops-handoffs-page/, `${label} must use triage ops-handoffs-page shell`);
    assert.doesNotMatch(source, /OpsItemCard|OpsSummaryCards/, `${label} must leave legacy OpsItemCard / OpsSummaryCards`);
  } else {
    assert.match(source, /OpsItemCard|OpsSummaryCards/, `${label} must use shared list or summary primitives`);
  }
}

assert.match(exportPackageDetailSource, /does not call platform APIs/, "Export Package detail must keep handoff creation separate from platform publishing");
assert.match(publishHandoffDetailSource, /do(?:es)? not call platform APIs or auto-publish/, "Publish Handoff detail must keep manual publishing boundary explicit");

assert.match(captureSource, /OpsConsolePage/, "Capture Inbox must compose OpsConsolePage under Operator Studio shell");
assert.match(reupSource, /OpsConsolePage/, "Reup Queue must compose OpsConsolePage under Operator Studio shell");
assert.match(captureSource, /OpsToolbarGroup/, "Capture Inbox toolbar chips must be grouped");
assert.match(reupSource, /OpsFilterBar|OpsToolbarGroup/, "Reup Queue filters must use shared Ops filter primitives");

console.log("ops-console design system source tests passed");
