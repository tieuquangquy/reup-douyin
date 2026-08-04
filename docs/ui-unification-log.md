# UI Unification Log

## Step: Route Audit and Unification Plan

Time started: 2026-04-21 23:09:33 +07:00

Status: Completed for planning scope.

### Findings

- `apps/web` uses Next.js app router.
- The root route currently redirects directly to `/review-board`.
- Feature screens exist and are mostly well-separated by component folders.
- There is no app shell, persistent navigation, Studio home, or Ops home.
- Operational screens are currently mixed with operator workflow routes:
  - `/dashboard/publish-health`
  - `/publish-control`
  - `/optimization`
- Source-video workflow screens are dynamic and should stay in Operator Studio:
  - `/source-videos/[id]/transcript-editor`
  - `/source-videos/[id]/final-review`
  - `/source-videos/[id]/publish`
- Shared risk UI already exists and should remain shared.

### Files Inspected

- `AGENTS.md`
- `apps/web/package.json`
- `apps/web/src/app/layout.tsx`
- `apps/web/src/app/page.tsx`
- `apps/web/src/app/review-board/page.tsx`
- `apps/web/src/app/dashboard/publish-health/page.tsx`
- `apps/web/src/app/publish-control/page.tsx`
- `apps/web/src/app/optimization/page.tsx`
- `apps/web/src/app/source-videos/[id]/transcript-editor/page.tsx`
- `apps/web/src/app/source-videos/[id]/final-review/page.tsx`
- `apps/web/src/app/source-videos/[id]/publish/page.tsx`
- `apps/web/src/components/review-board/*`
- `apps/web/src/components/transcript-editor/*`
- `apps/web/src/components/final-review/*`
- `apps/web/src/components/publish-draft/*`
- `apps/web/src/components/publish-health/*`
- `apps/web/src/components/publish-control/*`
- `apps/web/src/components/optimization/*`
- `apps/web/src/components/risk/*`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/*`

### Proposed Route Map

| Route | Proposed group | Proposed future action |
| --- | --- | --- |
| `/` | Operator Studio | Replace redirect with Studio home. |
| `/review-board` | Operator Studio | Keep route; wrap in Studio shell. |
| `/source-videos/[id]/transcript-editor` | Operator Studio | Keep route; wrap in Studio shell. |
| `/source-videos/[id]/final-review` | Operator Studio | Keep route; wrap in Studio shell. |
| `/source-videos/[id]/publish` | Operator Studio | Keep route; wrap in Studio shell. |
| `/dashboard/publish-health` | Ops Console | Add `/ops/publish-health`; keep or redirect old route later. |
| `/publish-control` | Ops Console | Add `/ops/publish-control`; keep or redirect old route later. |
| `/optimization` | Ops Console | Add `/ops/optimization`; keep or redirect old route later. |
| `/ops` | Ops Console | Add Ops home. |

### Notes

- No runtime files were changed in this planning step.
- No navigation config file was created yet. It is reasonable to create it in the next implementation step once shell component names are chosen.
- The next pass should update docs/demo links after route aliases exist.

## Step: App Shell and Route Foundation

Time started: 2026-04-21 23:14:33 +07:00

Status: Completed for foundation scope.

### Files Created

- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/components/app-shell/AppShell.tsx`
- `apps/web/src/components/app-shell/Sidebar.tsx`
- `apps/web/src/components/app-shell/Topbar.tsx`
- `apps/web/src/components/app-shell/PageShell.tsx`
- `apps/web/src/components/app-shell/NavSection.tsx`
- `apps/web/src/components/app-shell/StatusBadge.tsx`
- `apps/web/src/components/app-shell/OperatorStudioShell.tsx`
- `apps/web/src/components/app-shell/OpsConsoleShell.tsx`
- `apps/web/src/app/ops/page.tsx`
- `apps/web/src/app/ops/publish-health/page.tsx`
- `apps/web/src/app/ops/publish-control/page.tsx`
- `apps/web/src/app/ops/optimization/page.tsx`

### Files Updated

- `apps/web/src/app/page.tsx`
- `apps/web/src/app/globals.css`
- `docs/ui-unification-log.md`
- `docs/ui-unification-resume.md`
- `docs/ui-sitemap.md`

### Navigation Structure

Operator Studio sections:

- Intake
- Selection
- Production
- Publishing
- Optimization

Ops Console sections:

- Health
- Jobs
- Assets
- Publish Ops
- Accounts & Routing
- Risk & Policies
- Tools

Available nav targets:

- `/`
- `/review-board`
- `/ops`
- `/ops/publish-health`
- `/ops/publish-control`
- `/ops/optimization`

Context-only operator nav entries currently point back to `/review-board`:

- Transcript Editor
- Final Review
- Publish Draft

They intentionally require a source-video context and should become contextual links later.

### Route Foundation Created

- `/` now renders Operator Studio home instead of redirecting to `/review-board`.
- `/ops` now renders Ops Console home.
- `/ops/publish-health` reuses `PublishHealthDashboardPage`.
- `/ops/publish-control` reuses `PublishControlPlanePage`.
- `/ops/optimization` reuses `OptimizationPage`.
- Existing routes remain available:
  - `/review-board`
  - `/dashboard/publish-health`
  - `/publish-control`
  - `/optimization`
  - `/source-videos/[id]/transcript-editor`
  - `/source-videos/[id]/final-review`
  - `/source-videos/[id]/publish`

### Verification

- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run build`

All three commands passed.

### Known Blockers

- Existing feature pages still own their internal headers. The new shell is applied to new home and ops alias routes first; wrapping every feature page needs a separate visual pass to avoid duplicate sticky headers.
- Dynamic source-video links cannot be global nav links without a selected source video id.
- Job and asset ops screens are placeholders in navigation only; no new product surfaces were implemented.

## Step: Operator Studio Home Dashboard

Time started: 2026-04-21 23:20:33 +07:00

Status: Completed.

### Files Created

- `apps/web/src/components/operator-home/OperatorHomePage.tsx`
- `apps/web/src/components/operator-home/OverviewCards.tsx`
- `apps/web/src/components/operator-home/ActionQueuePanel.tsx`
- `apps/web/src/components/operator-home/RecentActivityPanel.tsx`
- `apps/web/src/components/operator-home/QuickLaunchGrid.tsx`
- `apps/web/src/lib/operatorHomeState.ts`
- `apps/web/src/types/jobs.ts`
- `apps/web/src/test/operator-home.test.ts`

### Files Updated

- `apps/web/src/app/page.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/lib/api.ts`
- `apps/web/package.json`
- `docs/ui-unification-log.md`
- `docs/ui-unification-resume.md`

### New Home Dashboard Structure

The `/` route now renders an Operator Studio control center with:

- Overview metrics strip
  - candidates waiting review
  - jobs running
  - final outputs ready
  - publish drafts ready
  - failed / needs reconciliation
- Action queue
  - review needed
  - transcript edits needed
  - final review needed
  - blocked by risk
  - publish reconciliation needed
- Recent activity
  - recent jobs
  - recent publish success/reconciliation signals
  - recent candidate updates
- Quick launch
  - Review board
  - Transcript editor with recent/current source-video context when available
  - Final review with recent/current source-video context when available
  - Publish drafts with ready draft context when available
  - Publish health
  - Publish control
  - Optimization
  - Ops Console

### APIs and Hooks Used

No new backend API was added.

Existing frontend API calls used:

- `fetchCandidates(DEFAULT_FILTERS)` -> `/candidates`
- `fetchJobs(undefined, 25)` -> `/jobs`
- `fetchPublishHealthDashboard("last_7_days")` -> `/analytics/publish-health`
- `fetchPublishControlQueue()` -> `/publish-control/queue`
- `fetchOptimizationDashboard()` -> `/optimization/dashboard-snapshot`

State aggregation is isolated in `apps/web/src/lib/operatorHomeState.ts`.

### Missing Data Handling

- `final outputs ready` is derived from publish-ready draft backlog until a dedicated render-output summary endpoint exists.
- Transcript/final-review quick links use the recent/current source video from publish queue or approved candidates. If no source-video context exists, those cards route back to `/review-board`.
- Recent activity uses the latest job list and publish health signals; no dedicated activity feed API exists yet.

### Verification

- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run build`
- `Invoke-WebRequest http://localhost:3000/`

All checks passed.

## Step: Route Unification for Operator Studio

Time started: 2026-04-21 23:29:24 +07:00

Status: Completed for current operator route scope.

### Route Mapping: Old to New

| Old route | New route | Behavior |
| --- | --- | --- |
| `/review-board` | `/selection/review-board` | Redirect. |
| `/source-videos/[id]/transcript-editor` | `/production/transcript-editor/[sourceVideoId]` | Redirect. |
| `/source-videos/[id]/final-review` | `/production/final-review/[sourceVideoId]` | Redirect. |
| `/source-videos/[id]/publish` | `/publishing/drafts` and `/publishing/drafts/[draftId]` | Compatibility alias still renders source-video publish editor because the old route is source-video scoped. |
| `/dashboard/publish-health` | `/publishing/health` | Redirect. |
| `/publish-control` | `/ops/publish-control` | Redirect. |
| `/optimization` | `/optimization` | Kept as operator optimization route and wrapped in Operator Studio shell. |

### New Operator Routes Added

- `/intake`
- `/intake/profiles`
- `/intake/crawl-sessions`
- `/selection/review-board`
- `/selection/candidates`
- `/production/downloads`
- `/production/transcript-editor/[sourceVideoId]`
- `/production/final-review/[sourceVideoId]`
- `/publishing/drafts`
- `/publishing/drafts/[draftId]`
- `/publishing/health`
- `/optimization`

### Redirects and Aliases Added

- `/review-board` redirects to `/selection/review-board`.
- `/selection/candidates` redirects to `/selection/review-board`.
- `/source-videos/[id]/transcript-editor` redirects to `/production/transcript-editor/[id]`.
- `/source-videos/[id]/final-review` redirects to `/production/final-review/[id]`.
- `/dashboard/publish-health` redirects to `/publishing/health`.
- `/publish-control` redirects to `/ops/publish-control`.
- `/source-videos/[id]/publish` remains a compatibility alias because the current editor can be source-video scoped.
- `/publishing/drafts/[draftId]` resolves draft detail, then reuses the source-video scoped publish draft editor.

### Files Created

- `apps/web/src/components/operator-routes/OperatorPlaceholderPage.tsx`
- `apps/web/src/components/operator-routes/OperatorReviewBoardPage.tsx`
- `apps/web/src/components/operator-routes/OperatorTranscriptEditorPage.tsx`
- `apps/web/src/components/operator-routes/OperatorFinalReviewPage.tsx`
- `apps/web/src/components/operator-routes/OperatorPublishDraftPage.tsx`
- `apps/web/src/components/operator-routes/PublishDraftByIdPage.tsx`
- `apps/web/src/components/operator-routes/PublishDraftsIndexPage.tsx`
- `apps/web/src/app/intake/page.tsx`
- `apps/web/src/app/intake/profiles/page.tsx`
- `apps/web/src/app/intake/crawl-sessions/page.tsx`
- `apps/web/src/app/selection/review-board/page.tsx`
- `apps/web/src/app/selection/candidates/page.tsx`
- `apps/web/src/app/production/downloads/page.tsx`
- `apps/web/src/app/production/transcript-editor/[sourceVideoId]/page.tsx`
- `apps/web/src/app/production/final-review/[sourceVideoId]/page.tsx`
- `apps/web/src/app/publishing/drafts/page.tsx`
- `apps/web/src/app/publishing/drafts/[draftId]/page.tsx`
- `apps/web/src/app/publishing/health/page.tsx`

### Files Updated

- `apps/web/src/app/review-board/page.tsx`
- `apps/web/src/app/dashboard/publish-health/page.tsx`
- `apps/web/src/app/publish-control/page.tsx`
- `apps/web/src/app/optimization/page.tsx`
- `apps/web/src/app/source-videos/[id]/transcript-editor/page.tsx`
- `apps/web/src/app/source-videos/[id]/final-review/page.tsx`
- `apps/web/src/app/source-videos/[id]/publish/page.tsx`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/lib/operatorHomeState.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/review-board/CandidateCard.tsx`
- `apps/web/src/components/review-board/CandidateDetailDrawer.tsx`
- `apps/web/src/components/transcript-editor/TranscriptEditorHeader.tsx`
- `apps/web/src/components/final-review/FinalReviewHeader.tsx`
- `apps/web/src/components/final-review/FinalReviewActions.tsx`
- `apps/web/src/components/final-review/FinalReviewStates.tsx`
- `apps/web/src/components/publish-draft/PublishDraftHeader.tsx`
- `apps/web/src/components/publish-draft/PublishDraftPage.tsx`
- `apps/web/src/components/publish-health/PublishHealthDashboardPage.tsx`

### Cross-links Added

- Review board candidate cards link to transcript editor and final review.
- Candidate detail drawer links to transcript editor and final review.
- Transcript editor links forward to final review.
- Final review links back to transcript editor, candidate review, and publish draft.
- Publish draft links to final review, publishing health, and publish control.
- Publish health manage links route to the unified publish drafts index.

### Issues Found During Migration

- The current publish editor is source-video scoped, while the target route is draft-id scoped. This was handled by a small draft-id resolver that fetches the draft and reuses `PublishDraftPage` with `source_video_id`.
- Some desired routes do not have product screens yet:
  - `/intake/profiles`
  - `/intake/crawl-sessions`
  - `/production/downloads`
  These are implemented as explicit placeholders rather than hidden missing pages.
- The local dev server kept an old child Node process on port 3000 after restart. It was manually stopped during verification; no script change was made in this step.

### Verification

- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run build`
- HTTP route checks covered `/`, all new static operator routes, representative dynamic routes, and legacy redirects.

## Step: Ops Console

Time started: 2026-04-21 23:45:00 +07:00

Status: Completed for minimal operational console scope.

### Ops Routes Created

- `/ops`
- `/ops/health`
- `/ops/jobs`
- `/ops/assets`
- `/ops/publish-attempts`
- `/ops/reconciliation`
- `/publishing/accounts`
- `/ops/routing-rules`
- `/ops/risk`
- `/ops/tools`

Existing compatibility/extended ops routes remain available:

- `/ops/publish-health`
- `/ops/publish-control`
- `/ops/optimization`

### Panels and Widgets Created

- Ops home:
  - job health summary
  - publish success/reconciliation summary
  - account health summary
  - asset/risk summary
  - operational section launch grid
  - action queue
- Health:
  - API and DB reachability inferred from `/ops/metrics`
  - worker activity inferred from running jobs
  - Redis marked honestly as not exposed
  - storage summarized from asset metrics
- Jobs:
  - running / failed / retryable / stale counts
  - latest jobs table
  - common failure categories
- Assets:
  - current vs historical asset counts by type
  - explicit note that file corruption/missing scans require a later backend scan
- Publish attempts:
  - latest attempts
  - internal status, external status, IDs, permalink, errors
- Reconciliation:
  - attempts in `NEEDS_RECONCILIATION` or `RECONCILING`
  - manual refresh status action
- Accounts:
  - configured platform accounts
  - account health table from publish control queue
- Routing rules:
  - current rules table
  - queue coverage counts
- Risk:
  - open / acknowledged / waived / resolved flags
  - severity and status visibility
- Tools:
  - local command references
  - Swagger link
  - browser action policy for destructive commands

### APIs Touched

No backend API was added.

Frontend API client additions:

- `fetchOperationalMetrics()` -> `GET /ops/metrics`
- `fetchAllPlatformAccounts()` -> `GET /platform-accounts`
- `fetchPublishAttemptList()` -> `GET /publish-attempts`
- `fetchRiskFlags()` -> `GET /risk-flags`

Existing APIs reused:

- `GET /jobs`
- `GET /analytics/publish-health`
- `GET /publish-control/queue`
- `GET /routing-rules`
- `POST /publish-attempts/{id}/refresh-status`

### Files Created

- `apps/web/src/types/operations.ts`
- `apps/web/src/components/ops-console/OpsShared.tsx`
- `apps/web/src/components/ops-console/OpsHomePage.tsx`
- `apps/web/src/components/ops-console/OpsHealthPage.tsx`
- `apps/web/src/components/ops-console/OpsJobsPage.tsx`
- `apps/web/src/components/ops-console/OpsAssetsPage.tsx`
- `apps/web/src/components/ops-console/OpsPublishAttemptsPage.tsx`
- `apps/web/src/components/ops-console/OpsReconciliationPage.tsx`
- `apps/web/src/components/ops-console/OpsAccountsPage.tsx`
- `apps/web/src/components/ops-console/OpsRoutingRulesPage.tsx`
- `apps/web/src/components/ops-console/OpsRiskPage.tsx`
- `apps/web/src/components/ops-console/OpsToolsPage.tsx`
- `apps/web/src/app/ops/health/page.tsx`
- `apps/web/src/app/ops/jobs/page.tsx`
- `apps/web/src/app/ops/assets/page.tsx`
- `apps/web/src/app/ops/publish-attempts/page.tsx`
- `apps/web/src/app/ops/reconciliation/page.tsx`
- `apps/web/src/app/publishing/accounts/page.tsx`
- `apps/web/src/app/ops/routing-rules/page.tsx`
- `apps/web/src/app/ops/risk/page.tsx`
- `apps/web/src/app/ops/tools/page.tsx`

### Files Updated

- `apps/web/src/app/ops/page.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/navigationConfig.ts`
- `docs/ui-sitemap.md`
- `docs/ui-unification-log.md`
- `docs/ui-unification-resume.md`

### Known Gaps

- Redis health is not exposed by backend yet.
- Worker heartbeat is inferred from jobs; there is no dedicated heartbeat endpoint yet.
- Asset missing/corrupt summaries need a backend scan before this page can show hard pass/fail.
- Tools are CLI/runbook references only; destructive actions such as reset/seed are intentionally not runnable from browser UI.

### Verification

- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run build`
- HTTP `HEAD` checks returned `200` for:
  - `/ops`
  - `/ops/health`
  - `/ops/jobs`
  - `/ops/assets`
  - `/ops/publish-attempts`
  - `/ops/reconciliation`
  - `/publishing/accounts`
  - `/ops/routing-rules`
  - `/ops/risk`
  - `/ops/tools`

## Step: Global Action Flow and Contextual Navigation

Time started: 2026-04-22 00:04:00 +07:00

Status: Completed for lightweight navigation scope.

### New Action Flows

- Operator Studio action queue now exposes clearer CTA text per item:
  - review needed -> `/selection/review-board`
  - transcript edits needed -> `/production/transcript-editor/{sourceVideoId}` when context exists
  - final review needed -> `/production/final-review/{sourceVideoId}` when context exists
  - blocked by risk -> `/ops/risk`
  - publish reconciliation needed -> `/ops/reconciliation`
  - publish drafts ready -> `/publishing/drafts/{draftId}` when a ready draft id exists
- Added "Next" shortcut in the action queue header for the first non-clear item.
- Added "Continue where you left off" panel:
  - continue transcript for latest active source video
  - open final review for the same source video
  - continue latest ready publish draft
  - resolve latest reconciliation queue when needed
- Quick launch now prefers direct publish draft detail when a ready draft id is available.
- Recent activity now links failed/retryable jobs to `/ops/jobs` and reconciliation items to `/ops/reconciliation`.

### Cross-links Added or Improved

- Topbar now has a lightweight "Quick actions" launcher:
  - Operator Studio: Home, Review, Drafts, Publish health, Optimization
  - Ops Console: Health, Jobs, Reconcile, Accounts, Routing
- Publish health publication rows now link directly to `/publishing/drafts/{draftId}` instead of the generic draft index.
- Ops publish attempts already link attempts back to draft detail and external permalink where available.
- Ops reconciliation already links uncertain attempts back to draft detail and exposes refresh status action.

### Status Wording Improved

- Action queue rows now use "Needs work" instead of generic "Open" when count is non-zero.
- Action queue rows show a human CTA such as "Open review board", "Continue transcript", "Review risk", or "Resolve status".
- Continue panel badges use explicit "Continue".

### Files Updated

- `apps/web/src/components/app-shell/Topbar.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/lib/operatorHomeState.ts`
- `apps/web/src/components/operator-home/ActionQueuePanel.tsx`
- `apps/web/src/components/operator-home/OperatorHomePage.tsx`
- `apps/web/src/components/publish-health/PublishHealthDashboardPage.tsx`
- `apps/web/src/test/operator-home.test.ts`
- `docs/ui-unification-log.md`
- `docs/ui-unification-resume.md`

### Files Created

- `apps/web/src/components/operator-home/ContinuePanel.tsx`

### Verification

- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run build`
- HTTP checks:
  - `/selection/review-board` returned `200`
  - `/publishing/drafts` returned `200`
  - `/publishing/health` returned `200`
  - `/ops` returned `200`
  - `/ops/jobs` returned `200`
  - `/ops/reconciliation` returned `200`
  - `/ops/publish-attempts` returned `200`
  - `/` rendered through `GET`; `HEAD /` on the current dev server returned a transient 500 even though the page body rendered normally.

## Step: UI Polish, Wording, and Consistency Pass

Time started: 2026-04-21 23:55:11 +07:00

Status: Completed.

### Wording Changes

- Added a shared status label formatter so raw enum values such as `NEEDS_RECONCILIATION`, `RETRYABLE`, `READY`, and `NEEDS_FIX` render as operator-readable labels.
- Standardized final review wording:
  - `Approve export` remains the technical render approval action.
  - `Media publish-ready` now means the current render is the approved media output for publish draft preparation.
  - Publish draft readiness remains separate as `Draft ready`.
- Reworded final review confirmations and errors so operators understand that rerendering requires a fresh media publish-ready review.
- Updated publish draft and publish health surfaces to display human status labels instead of raw enum tokens.
- Updated risk warning display so severity/status and latest risk decisions use readable labels.

### Consistency Fixes

- Replaced stray separator rendering in review board, transcript header, final review, publish draft header, and media summary with ASCII `/` separators.
- Candidate cards and detail drawer now humanize candidate status.
- Publish control queue and account cards now humanize account, draft, and routing rule statuses.
- Quick launch cards now show `Ready` instead of a vague `Open` badge.
- Ops metric badges now use `Healthy`, `Needs attention`, `Blocked`, or `Info` instead of raw tone names.
- Sidebar active matching now requires an exact route or child route, preventing overly broad active states.
- Sidebar active item styling now has a stronger left accent and active title color.
- State panels and tables received small readability improvements for long error/detail text and dense ops tables.

### UX Friction Removed

- Reduced ambiguity between media publish readiness, publish draft readiness, and successful publishing.
- Removed raw enum display from the most operator-facing lists and summaries.
- Made active navigation clearer during long sessions.
- Improved scan speed in tables by aligning cells to the top.

### Files Updated

- `apps/web/src/lib/statusLabels.ts`
- `apps/web/src/components/app-shell/StatusBadge.tsx`
- `apps/web/src/components/app-shell/NavSection.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/components/review-board/CandidateCard.tsx`
- `apps/web/src/components/review-board/CandidateDetailDrawer.tsx`
- `apps/web/src/components/transcript-editor/TranscriptEditorHeader.tsx`
- `apps/web/src/components/final-review/FinalReviewHeader.tsx`
- `apps/web/src/components/final-review/FinalReviewActions.tsx`
- `apps/web/src/components/final-review/FinalReviewPage.tsx`
- `apps/web/src/components/final-review/FinalRenderMetadataPanel.tsx`
- `apps/web/src/components/publish-draft/PublishDraftHeader.tsx`
- `apps/web/src/components/publish-draft/PublishDraftPage.tsx`
- `apps/web/src/components/publish-draft/PublishDraftStates.tsx`
- `apps/web/src/components/publish-draft/PublishMediaSummary.tsx`
- `apps/web/src/components/publish-health/PublishHealthDashboardPage.tsx`
- `apps/web/src/components/publish-control/PublishControlPlanePage.tsx`
- `apps/web/src/components/risk/RiskSummaryCard.tsx`
- `apps/web/src/components/ops-console/OpsShared.tsx`
- `apps/web/src/components/operator-home/QuickLaunchGrid.tsx`
- `apps/web/src/components/operator-routes/OperatorFinalReviewPage.tsx`
- `apps/web/src/components/operator-routes/PublishDraftsIndexPage.tsx`
- `apps/web/src/lib/operatorHomeState.ts`

## Step: Documentation And Route-Test Closeout

### Route Nav Tests Added

Created `apps/web/src/test/route-nav.test.ts` — a stateless test that:
- Declares the full canonical route map (`OPERATOR_STUDIO_ROUTES`).
- Calls every `operatorHomeState` builder function with fixture data.
- Collects every `href` produced and asserts each one appears in `CANONICAL_ROUTES` or is a known legacy redirect.
- Verifies split-nav routes (`/ops/publish-health`, `/publishing/health`) are both declared.
- Verifies the canonical publish draft route uses `/publishing/drafts/[draftId]`.

Added to `apps/web/package.json` `test` script to run as part of the suite.

### Docs Updated

**docs/demo-flow.md** — Replaced the old four-route list with a complete unified route map:
- Operator Studio home at `/`
- Selection: `/selection/review-board`
- Production: `/production/transcript-editor/{id}`, `/production/final-review/{id}`
- Publishing: `/publishing/drafts`, `/publishing/drafts/{id}`, `/publishing/health`
- Ops Console: `/ops`

**docs/local-operator-guide.md** — Updated the Operator Demo Path to reflect the seven-step flow:
1. Open `/` → home dashboard
2. Open `/selection/review-board`
3. Open `/production/transcript-editor/{id}`
4. Open `/production/final-review/{id}`
5. Open `/publishing/drafts` or `/publishing/drafts/{id}`
6. Check risk decisions
7. Open `/ops` for operational health

### Files Created
- `apps/web/src/test/route-nav.test.ts`

### Files Updated
- `apps/web/package.json` — added `route-nav.test.ts` to test script
- `docs/demo-flow.md` — replaced old route references with unified routes
- `docs/local-operator-guide.md` — updated Operator Demo Path

All 10 web test suites pass (9 existing + 1 new route-nav test). The route-nav test verifies every href from `operatorHomeState` maps to a declared route, ensuring nav consistency as the route map grows.

**UI unification complete.** See `docs/ui-unification-handoff.md` for the authoritative final reference.
