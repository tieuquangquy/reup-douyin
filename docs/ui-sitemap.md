# UI Sitemap

This sitemap records the current web route surface after the Operator Studio / Ops Console unification work.

## Operator Studio

Operator Studio is the default workflow area at `/`. It is for the local operator's day-to-day content flow.

| Route | Status | Purpose | Component entry |
| --- | --- | --- | --- |
| `/` | Available | Operator home dashboard, work queue, recent activity, quick launch | `components/operator-home/OperatorHomePage` |
| `/intake` | Available | Intake landing and next-step shortcuts | `components/operator-routes/OperatorPlaceholderPage` |
| `/intake/profiles` | Placeholder | Source profiles list area | `components/operator-routes/OperatorPlaceholderPage` |
| `/intake/crawl-sessions` | Placeholder | Crawl/session history area | `components/operator-routes/OperatorPlaceholderPage` |
| `/selection/review-board` | Available | Candidate review board | `components/operator-routes/OperatorReviewBoardPage` |
| `/selection/candidates` | Redirect | Alias into review board until a separate candidates list exists | `redirect('/selection/review-board')` |
| `/production/downloads` | Placeholder | Download/media asset queue area | `components/operator-routes/OperatorPlaceholderPage` |
| `/production/transcript-editor/[sourceVideoId]` | Available | Transcript and translation draft editor | `components/operator-routes/OperatorTranscriptEditorPage` |
| `/production/final-review/[sourceVideoId]` | Available | Final render review and publish-ready decision | `components/operator-routes/OperatorFinalReviewPage` |
| `/publishing/drafts` | Available | Publish draft index/entry area | `components/operator-routes/PublishDraftsIndexPage` |
| `/publishing/drafts/[draftId]` | Available | Publish draft editor resolved by draft id | `components/operator-routes/PublishDraftByIdPage` |
| `/publishing/health` | Available | Publish health and analytics-lite dashboard | `components/publish-health/PublishHealthDashboardPage` |
| `/optimization` | Available | Outcome quality and optimization hints | `components/optimization/OptimizationPage` |

## Ops Console

Ops Console is the operational area under `/ops`. It is for health, jobs, assets, publishing operations, account routing, policies, and tools.

| Route | Status | Purpose | Component entry |
| --- | --- | --- | --- |
| `/ops` | Available | Decision-first Ops home with incidents, queue/worker signals, dependency health, workload, outcomes, and diagnostics | `components/ops-console/OpsHomePage` |
| `/ops/health` | Available | API/DB inferred health, worker/job summary, storage/risk summary | `components/ops-console/OpsHealthPage` |
| `/ops/jobs` | Available | Running, failed, retryable, stale jobs and failure categories | `components/ops-console/OpsJobsPage` |
| `/ops/assets` | Available | Current vs historical asset summary and asset health limitations | `components/ops-console/OpsAssetsPage` |
| `/ops/publish-attempts` | Available | Latest publish attempts, internal/external status, IDs, permalinks | `components/ops-console/OpsPublishAttemptsPage` |
| `/ops/reconciliation` | Available | Attempts needing status reconciliation and manual refresh | `components/ops-console/OpsReconciliationPage` |
| `/publishing/accounts` | Available | Facebook Page connection, permissions, safety and warm-up in Operator Studio | `components/ops-console/OpsAccountsPage` |
| `/ops/routing-rules` | Available | Routing rule table and queue coverage | `components/ops-console/OpsRoutingRulesPage` |
| `/ops/risk` | Available | Open, acknowledged, waived, and resolved risk warnings | `components/ops-console/OpsRiskPage` |
| `/ops/tools` | Available | Local commands, runbooks, Swagger reference, browser action policy | `components/ops-console/OpsToolsPage` |
| `/ops/publish-health` | Available | Ops alias for publish health | `components/publish-health/PublishHealthDashboardPage` |
| `/ops/publish-control` | Available | Multi-account/page publish control plane | `components/publish-control/PublishControlPlanePage` |
| `/ops/optimization` | Available | Ops alias for optimization views | `components/optimization/OptimizationPage` |

## Compatibility Routes

These routes remain available so older links do not break while docs and demos move to the unified map.

| Compatibility route | Current behavior |
| --- | --- |
| `/review-board` | Redirects to `/selection/review-board`. |
| `/dashboard/publish-health` | Redirects to `/publishing/health`. |
| `/publish-control` | Redirects to `/ops/publish-control`. |
| `/source-videos/[id]/transcript-editor` | Redirects to `/production/transcript-editor/[id]`. |
| `/source-videos/[id]/final-review` | Redirects to `/production/final-review/[id]`. |
| `/source-videos/[id]/publish` | Compatibility alias that still renders the source-video scoped publish editor. |

## Route Grouping Principles

- Operator Studio uses workflow language: intake, selection, production, publishing, optimization.
- Ops Console uses operational language: health, jobs, assets, publish ops, accounts and routing, risk and policies, tools.
- Global navigation should only link directly to routes that do not require a selected source video or draft id.
- Dynamic source-video and draft links should appear contextually from cards, rows, headers, and detail panels.
- Placeholder routes must stay explicit; they should not pretend planned screens are complete.
- Compatibility routes can be removed only after demo docs, operator docs, and tests stop referencing them.

## Shared UI Areas

Shared components are not routes. They can be reused in both shells.

| Area | Existing files |
| --- | --- |
| App shell and navigation | `apps/web/src/components/app-shell/*`, `apps/web/src/lib/navigationConfig.ts` |
| Risk summaries and warnings | `apps/web/src/components/risk/*` |
| API client | `apps/web/src/lib/api.ts` |
| State helpers | `apps/web/src/lib/*State.ts` |
| Domain types | `apps/web/src/types/*` |

## Known Sitemap Gaps

- `/intake/profiles`, `/intake/crawl-sessions`, and `/production/downloads` are route placeholders. They need thin API-backed list screens in a later pass.
- There is no neutral source-video detail page yet.
- The publish draft editor is still source-video scoped internally. `/publishing/drafts/[draftId]` resolves the draft and reuses that editor.
- Ops health does not yet have dedicated Redis, worker heartbeat, or file-level storage scan endpoints. The current pages show available metrics and label missing signals explicitly.
