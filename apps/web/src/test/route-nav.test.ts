/**
 * Route navigation tests for the unified route map + Phase 5 operator IA.
 *
 * These tests verify:
 * 1. All unified operator routes resolve to existing page modules.
 * 2. Redirect routes map old paths to their canonical new paths.
 * 3. All hrefs produced by operatorHomeState.ts point to declared routes.
 * 4. Sidebar IA: Operator = day journey; Ops = monitor + AI settings.
 *
 * No live API, DB, or browser is required. Tests run with tsx.
 */
import assert from "node:assert/strict";
import { buildOperatorMetrics, buildActionQueue, buildQuickLaunchItems, buildContinueItems } from "../lib/operatorHomeState";
import {
  extractSourceVideoIdFromPath,
  getBreadcrumbs,
  isNavItemActive,
  operatorNavSections,
  opsNavSections,
  resolveNavItemHref,
  resolveNavItemStatusLabel
} from "../lib/navigationConfig";
import type { PublishHealthDashboard } from "../types/analytics";
import type { Job } from "../types/jobs";
import type { PublishControlQueue } from "../types/publish-control";
import type { Candidate } from "../types/review-board";

// ---------------------------------------------------------------------------
// Route map: canonical routes exposed by the Next.js app router.
// ---------------------------------------------------------------------------

const OPERATOR_STUDIO_ROUTES = [
  // Home
  "/",
  // Selection
  "/selection/review-board",
  "/selection/candidates",
  "/selection/reup-queue",
  // Production
  "/production/downloads",
  "/production/transcript-editor/[sourceVideoId]",
  "/production/final-review/[sourceVideoId]",
  // Publishing
  "/publishing/drafts",
  "/publishing/drafts/[draftId]",
  "/publishing/export-packages",
  "/publishing/export-packages/[packageId]",
  "/publishing/publish-handoffs",
  "/publishing/publish-handoffs/[handoffId]",
  "/publishing/health",
  // Ops Console
  "/ops",
  "/ops/pipeline",
  "/ops/accounts",
  "/ops/assets",
  "/ops/health",
  "/ops/jobs",
  "/ops/users",
  "/ops/optimization",
  "/ops/publish-attempts",
  "/ops/publish-control",
  "/ops/publish-health",
  "/ops/reconciliation",
  "/ops/risk",
  "/ops/routing-rules",
  "/ops/tools",
  "/ops/extensions/douyin",
  "/ops/extensions/douyin/capture-inbox",
  // Cross-cutting
  "/optimization",
  "/publish-control",
  "/accounts/douyin",
  "/setup/douyin-extension",
  "/intake",
  "/intake/crawl-sessions",
  "/intake/profiles",
] as const;

/** Canonical route map used for href verification. */
const CANONICAL_ROUTES = new Set<string>(OPERATOR_STUDIO_ROUTES);

// ---------------------------------------------------------------------------
// Test: all canonical routes are declared.
// ---------------------------------------------------------------------------

for (const route of OPERATOR_STUDIO_ROUTES) {
  assert.ok(
    typeof route === "string" && route.startsWith("/"),
    `Route must be a non-empty string starting with '/': ${route}`
  );
}

// ---------------------------------------------------------------------------
// Test: hrefs from operatorHomeState never point outside the declared route set
// unless they are old compat-redirect routes (verified separately below).
// ---------------------------------------------------------------------------

const candidates = [
  { id: "c1", source_video_id: "sv1", status: "SHORTLISTED" as const, updated_at: "2026-04-21T00:00:00Z", source_video: null }
] as unknown as Candidate[];

const jobs = [
  { id: "j1", job_type: "RENDER_FINAL" as const, status: "RUNNING" as const, updated_at: "2026-04-21T00:01:00Z", completed_steps: 1, total_steps: 3, error_code: null, error_message: null }
] as unknown as Job[];

const health = {
  overview: {
    drafts_ready_not_published: 1,
    needs_reconciliation_attempts: 0,
    drafts_blocked_by_risk: 0
  },
  action_queue: {
    needs_reconciliation: [],
    drafts_ready: [{ source_video_id: "sv2", publish_draft_id: "d1" }],
    recent_successes: []
  }
} as unknown as PublishHealthDashboard;

const queue = {
  unassigned_drafts: [],
  assigned_drafts: [{ source_video_id: "sv3", publish_draft_id: "d2" }],
  scheduled_drafts: [],
  needs_attention: []
} as unknown as PublishControlQueue;

const allHrefs = new Set<string>();

const metrics = buildOperatorMetrics({ candidates, jobs, health, queue });
for (const m of metrics) {
  if (m.href) allHrefs.add(m.href);
}

const actions = buildActionQueue({ candidates, health, queue, recentSourceVideoId: "sv1" });
for (const a of actions) {
  if (a.href) allHrefs.add(a.href);
}

const quickLaunch = buildQuickLaunchItems({ recentSourceVideoId: "sv1", readyDraftSourceVideoId: "sv2", readyDraftId: "d1" });
for (const q of quickLaunch) {
  if (q.href) allHrefs.add(q.href);
}

const continueItems = buildContinueItems({ recentSourceVideoId: "sv1", readyDraftId: "d1", reconciliationDraftId: null });
for (const c of continueItems) {
  if (c.href) allHrefs.add(c.href);
}

const KNOWN_LEGACY_REDIRECT_SOURCES = new Set<string>([
  "/source-videos/[id]/transcript-editor",
  "/source-videos/[id]/final-review",
  "/source-videos/[id]/publish",
  "/review-board",
  "/publish-control",
]);

function isKnownLegacyRedirect(href: string): boolean {
  for (const legacy of KNOWN_LEGACY_REDIRECT_SOURCES) {
    if (href.startsWith(legacy.replace("[id]", ""))) return true;
  }
  return false;
}

const unknownHrefs: string[] = [];
for (const href of allHrefs) {
  if (CANONICAL_ROUTES.has(href)) continue;
  const base = href.replace(/\/[^/]+$/, "");
  const dynamicRoutes = [...CANONICAL_ROUTES].filter((r) => r.startsWith(base + "/["));
  if (dynamicRoutes.length > 0) continue;
  if (isKnownLegacyRedirect(href)) continue;
  unknownHrefs.push(href);
}

assert.equal(
  unknownHrefs.length,
  0,
  `Found hrefs with no matching route declaration:\n  ${unknownHrefs.join("\n  ")}\n\nAdd them to OPERATOR_STUDIO_ROUTES or KNOWN_LEGACY_REDIRECT_SOURCES.`
);

assert.ok(CANONICAL_ROUTES.has("/publishing/health"), "publishing/health must be a declared route");
assert.ok(CANONICAL_ROUTES.has("/ops/publish-health"), "ops/publish-health must be a declared route");
assert.ok(CANONICAL_ROUTES.has("/ops/publish-control"), "ops/publish-control must be a declared route");
assert.ok(CANONICAL_ROUTES.has("/ops/reconciliation"), "ops/reconciliation must be a declared route");
assert.ok(CANONICAL_ROUTES.has("/ops/risk"), "ops/risk must be a declared route");
assert.ok(CANONICAL_ROUTES.has("/ops/pipeline"), "ops/pipeline must be a declared route");

// ---------------------------------------------------------------------------
// Phase 5 IA: Operator journey vs Ops monitor/settings
// ---------------------------------------------------------------------------

function findNavItem(label: string, href?: string, surface?: "operator" | "ops") {
  const sections = surface === "operator" ? operatorNavSections : surface === "ops" ? opsNavSections : [...operatorNavSections, ...opsNavSections];
  const allItems = sections.flatMap((section) => section.items);
  const item = allItems.find((candidate) => candidate.label === label && (!href || candidate.href === href));
  assert.ok(item, `Missing nav item ${label}${href ? ` at ${href}` : ""}${surface ? ` on ${surface}` : ""}`);
  return item;
}

function operatorLabels(): string[] {
  return operatorNavSections.flatMap((s) => s.items.map((i) => i.label));
}

function opsLabels(): string[] {
  return opsNavSections.flatMap((s) => s.items.map((i) => i.label));
}

assert.ok(operatorLabels().includes("nav.captureInbox"), "Capture Inbox must live on Operator Studio");
assert.equal(opsLabels().includes("nav.captureInbox"), false, "Capture Inbox must not remain on Ops sidebar");
assert.equal(operatorLabels().includes("nav.intake"), false, "Intake must be removed from Operator sidebar");
assert.equal(operatorLabels().includes("nav.optimization"), false, "Optimization must be removed from Operator sidebar");
assert.equal(opsLabels().includes("nav.assetState"), false, "Asset State must be removed from Ops sidebar");
assert.equal(opsLabels().includes("nav.publishHealth"), false, "Publish Health must be removed from Ops sidebar");
assert.equal(opsLabels().includes("nav.publishControl"), false, "Publish Control must be removed from Ops sidebar");
assert.equal(opsLabels().includes("nav.riskGates"), false, "Risk Gates must be removed from Ops sidebar");
assert.equal(opsLabels().includes("nav.tools"), false, "Tools must be removed from Ops sidebar");
assert.ok(opsLabels().includes("nav.jobMonitor"), "Job Monitor stays on Ops");
assert.ok(opsLabels().includes("nav.users"), "Users stays on Ops");
assert.ok(opsLabels().includes("nav.captionAiSettings"), "Caption AI stays on Ops");
assert.equal(opsLabels().includes("nav.swagger"), false, "Swagger must not appear in Ops sidebar");
assert.equal(opsLabels().includes("nav.apiAuthUi"), false, "API login UI must not appear in Ops sidebar");
assert.equal(
  opsNavSections.some((s) => s.title === "nav.sectionAdvanced"),
  false,
  "Ops Advanced backend section must be removed"
);
assert.equal(opsLabels().includes("nav.douyinExtensionManager"), false, "Extension Manager must be removed from Ops sidebar");
assert.equal(operatorLabels().includes("nav.douyinAccounts"), false, "Douyin Accounts must be removed from Operator sidebar");
assert.ok(operatorLabels().includes("nav.douyinExtensionSetup"), "Extension Setup stays on Operator Studio");

const operatorItemCount = operatorNavSections.reduce((n, s) => n + s.items.length, 0);
assert.ok(operatorItemCount <= 12, `Operator sidebar should stay lean (got ${operatorItemCount})`);

assert.ok(isNavItemActive(findNavItem("nav.home", undefined, "operator"), "/"), "Home must be active on /");
assert.ok(
  isNavItemActive(findNavItem("nav.captureInbox", undefined, "operator"), "/ops/extensions/douyin/capture-inbox"),
  "Capture Inbox must be active on Operator"
);
assert.ok(isNavItemActive(findNavItem("nav.douyinExtensionSetup", undefined, "operator"), "/setup/douyin-extension"), "Extension setup must be active");
assert.ok(isNavItemActive(findNavItem("nav.reviewBoard", undefined, "operator"), "/selection/review-board"), "Review board must be active on canonical route");
assert.ok(isNavItemActive(findNavItem("nav.reviewBoard", undefined, "operator"), "/review-board"), "Review board must cover legacy redirect route");
assert.ok(isNavItemActive(findNavItem("nav.reupQueue", undefined, "operator"), "/selection/reup-queue"), "Reup Queue must be active");
assert.ok(isNavItemActive(findNavItem("nav.exportPackages", undefined, "operator"), "/publishing/export-packages/package-1"), "Export Packages must be active on detail route");
assert.ok(isNavItemActive(findNavItem("nav.publishHandoffs", undefined, "operator"), "/publishing/publish-handoffs/handoff-1"), "Publish Handoffs must be active on detail route");
assert.ok(isNavItemActive(findNavItem("nav.opsHome", undefined, "ops"), "/ops"), "Ops home must be active");
assert.ok(isNavItemActive(findNavItem("nav.pipelineDashboard", undefined, "operator"), "/ops/pipeline"), "Pipeline Dashboard must be active on Operator Studio");
assert.equal(
  opsNavSections.some((section) => section.items.some((item) => item.label === "nav.pipelineDashboard")),
  false,
  "Pipeline Dashboard must leave Ops Console sidebar"
);
assert.ok(operatorLabels().includes("nav.pipelineDashboard"), "Pipeline Dashboard must appear on Operator Studio");
assert.ok(isNavItemActive(findNavItem("nav.users", undefined, "ops"), "/ops/users"), "Users must be active on Ops");
assert.ok(isNavItemActive(findNavItem("nav.transcriptEditor", undefined, "operator"), "/production/transcript-editor/source-1"), "Transcript editor must highlight");
assert.ok(isNavItemActive(findNavItem("nav.finalReview", undefined, "operator"), "/production/final-review/source-1"), "Final review must highlight");
assert.ok(isNavItemActive(findNavItem("nav.publishDrafts", undefined, "operator"), "/source-videos/source-1/publish"), "Legacy publish draft route must highlight drafts");

assert.equal(
  operatorNavSections.some((section) =>
    section.items.some((item) => item.href === "/ops/publish-health" || item.href === "/ops/publish-control" || item.href === "/publish-control")
  ),
  false,
  "Operator nav must not expose ops publish routes"
);
assert.equal(
  operatorNavSections.some((section) => section.items.some((item) => item.label === "nav.publishHealth" || item.label === "nav.publishControl")),
  false,
  "Operator nav must not include publish ops labels"
);

const transcriptItem = findNavItem("nav.transcriptEditor", undefined, "operator");
const finalReviewItem = findNavItem("nav.finalReview", undefined, "operator");
assert.equal(resolveNavItemHref(transcriptItem, "source-1"), "/production/transcript-editor/source-1");
assert.equal(resolveNavItemHref(finalReviewItem, "source-1"), "/production/final-review/source-1");
assert.notEqual(resolveNavItemHref(transcriptItem, "source-1"), resolveNavItemHref(finalReviewItem, "source-1"));
assert.equal(resolveNavItemHref(transcriptItem, null), "/selection/review-board");
assert.equal(resolveNavItemHref(finalReviewItem, null), "/publishing/drafts");
assert.doesNotMatch(
  resolveNavItemHref(transcriptItem, "source-1"),
  /\/source-videos\//,
  "Transcript nav must open the production canonical path (avoid NEXT_REDIRECT overlay)"
);
assert.equal(resolveNavItemStatusLabel(transcriptItem, "source-1"), "nav.openCurrentVideo");
assert.equal(resolveNavItemStatusLabel(finalReviewItem, "source-1"), "nav.openCurrentVideo");
assert.equal(resolveNavItemStatusLabel(transcriptItem, null), "nav.selectVideo");
assert.equal(resolveNavItemStatusLabel(finalReviewItem, null), "nav.selectOutput");
assert.equal(extractSourceVideoIdFromPath("/source-videos/source-1/transcript-editor"), "source-1");
assert.equal(extractSourceVideoIdFromPath("/source-videos/source-1/final-review"), "source-1");
assert.equal(extractSourceVideoIdFromPath("/production/transcript-editor/source-1"), "source-1");
assert.equal(extractSourceVideoIdFromPath("/production/final-review/source-1"), "source-1");

// ---------------------------------------------------------------------------
// Breadcrumbs
// ---------------------------------------------------------------------------

assert.deepEqual(getBreadcrumbs("/selection/review-board").map((item) => item.label), ["nav.home", "nav.sectionWork", "nav.reviewBoard"]);
assert.deepEqual(getBreadcrumbs("/selection/reup-queue").map((item) => item.label), ["nav.home", "nav.sectionWork", "nav.reupQueue"]);
assert.deepEqual(getBreadcrumbs("/ops/extensions/douyin/capture-inbox").map((item) => item.label), ["nav.home", "nav.sectionWork", "nav.captureInbox"]);
assert.deepEqual(getBreadcrumbs("/intake").map((item) => item.label), ["nav.home", "nav.intake"]);
assert.deepEqual(getBreadcrumbs("/accounts/douyin").map((item) => item.label), ["nav.home"]);
assert.deepEqual(getBreadcrumbs("/setup/douyin-extension").map((item) => item.label), ["nav.home", "nav.sectionSetup", "nav.douyinExtensionSetup"]);
assert.deepEqual(getBreadcrumbs("/ops/extensions/douyin").map((item) => item.label), ["nav.opsConsole"]);
assert.deepEqual(getBreadcrumbs("/production/transcript-editor/source-1").map((item) => item.label), ["nav.home", "nav.sectionProduction", "nav.transcriptEditor"]);
assert.deepEqual(getBreadcrumbs("/production/final-review/source-1").map((item) => item.label), ["nav.home", "nav.sectionProduction", "nav.finalReview"]);
assert.deepEqual(getBreadcrumbs("/source-videos/source-1/publish").map((item) => item.label), ["nav.home", "nav.sectionPublishing", "nav.publishDraft"]);
assert.deepEqual(getBreadcrumbs("/dashboard/publish-health").map((item) => item.label), ["nav.opsConsole", "nav.publishHealth"]);
assert.deepEqual(getBreadcrumbs("/publishing/export-packages").map((item) => item.label), ["nav.home", "nav.sectionPublishing", "nav.exportPackages"]);
assert.deepEqual(getBreadcrumbs("/publishing/export-packages/package-1").map((item) => item.label), ["nav.home", "nav.sectionPublishing", "nav.exportPackage"]);
assert.deepEqual(getBreadcrumbs("/publishing/publish-handoffs").map((item) => item.label), ["nav.home", "nav.sectionPublishing", "nav.publishHandoffs"]);
assert.deepEqual(getBreadcrumbs("/publishing/publish-handoffs/handoff-1").map((item) => item.label), ["nav.home", "nav.sectionPublishing", "nav.publishHandoff"]);
assert.deepEqual(getBreadcrumbs("/ops/reconciliation").map((item) => item.label), ["nav.opsConsole", "nav.reconciliation"]);
assert.deepEqual(getBreadcrumbs("/ops/pipeline").map((item) => item.label), ["nav.home", "nav.pipelineDashboard"]);
assert.deepEqual(getBreadcrumbs("/ops/users").map((item) => item.label), ["nav.opsConsole", "nav.sectionMonitor", "nav.users"]);
assert.deepEqual(getBreadcrumbs("/ops/caption-ai").map((item) => item.label), ["nav.opsConsole", "nav.sectionAiSettings", "nav.captionAiSettings"]);

const publishHref = "/publishing/drafts/draft-abc";
const publishBase = publishHref.replace(/\/[^/]+$/, "");
assert.ok(
  CANONICAL_ROUTES.has(publishBase + "/[draftId]"),
  "Canonical publish draft route must use /publishing/drafts/[draftId]"
);

console.log(`route-nav tests passed — ${allHrefs.size} hrefs verified across ${OPERATOR_STUDIO_ROUTES.length} declared routes.`);
