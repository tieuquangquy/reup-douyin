# UI Consolidation Log

## 2026-04-22 - Sidebar / Topbar / Navigation Flow Refinement

### Audit Findings

- `apps/web` already had `AppShell`, `Sidebar`, `Topbar`, `OperatorStudioShell`, and `OpsConsoleShell`.
- Navigation config existed, but Operator Studio sidebar mixed Home under Intake and exposed raw dynamic route patterns like `/source-videos/[id]/transcript-editor`.
- Active state was path-prefix based and did not reliably cover legacy redirect routes such as `/review-board`, `/dashboard/publish-health`, or `/publish-control`.
- Topbar had page title, language switcher, a basic quick-actions menu, and surface switcher, but no breadcrumb/location context.
- Operator home already had useful quick launch, continue, action queue, and recent activity panels.
- Dynamic operator routes had local header links, but their shell-level context was weak.
- Ops Console had several pages and a tools page with Swagger, but Swagger was not visible from primary navigation.

### Navigation Decisions

- Operator Studio sidebar now uses these groups:
  - Home
  - Intake
  - Selection
  - Production
  - Publishing
  - Optimization
- Ops Console sidebar now uses these groups:
  - Ops Home
  - Jobs
  - Publish Ops
  - Accounts & Routing
  - Risk & Tools
- Dynamic source-video routes are not shown as raw static menu items.
- Production dynamic routes highlight a contextual `Production Work` item.
- Publish draft routes, including legacy `/source-videos/[id]/publish`, highlight `Drafts`.
- Publish control remains reachable from Operator Studio through `/publish-control`, which preserves the existing redirect into Ops Console.
- Swagger is available as a contextual Ops shortcut and opens the FastAPI docs in a new tab.

### Contextual Links Added

- Review board shell actions: Home, Production Work, Drafts.
- Transcript editor shell actions: Review Board, Final Review, Home.
- Final review shell actions: Transcript Editor, Publish Draft, Drafts.
- Publish draft shell actions: Final Review, Publish Health, Publish Control.
- Publish drafts index actions: Publish Health and Publish Control.
- Publish health actions: Drafts, Publish Control, Reconciliation.
- Optimization actions: Publish Health, Publish Control, Ops Optimization.
- Ops home/actions: Health, Jobs, Publish Health.
- Ops publish pages now cross-link between Publish Health, Publish Control, Attempts, Reconciliation, and Operator Drafts.

### Files Changed

- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/components/app-shell/NavSection.tsx`
- `apps/web/src/components/app-shell/Topbar.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/components/operator-routes/OperatorReviewBoardPage.tsx`
- `apps/web/src/components/operator-routes/OperatorTranscriptEditorPage.tsx`
- `apps/web/src/components/operator-routes/OperatorFinalReviewPage.tsx`
- `apps/web/src/components/operator-routes/OperatorPublishDraftPage.tsx`
- `apps/web/src/components/operator-routes/PublishDraftsIndexPage.tsx`
- `apps/web/src/app/publishing/health/page.tsx`
- `apps/web/src/app/optimization/page.tsx`
- `apps/web/src/app/ops/page.tsx`
- `apps/web/src/app/ops/publish-control/page.tsx`
- `apps/web/src/app/ops/publish-health/page.tsx`
- `apps/web/src/components/publish-control/PublishControlPlanePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/test/route-nav.test.ts`
- `docs/ui-consolidation-log.md`
- `docs/ui-consolidation-resume.md`
- `docs/ui-consolidation-route-map.md`

### Verification

- `node` JSON parse for `en.json` and `vi.json`: passed.
- `npm --workspace @reup-douyin/web run typecheck`: passed.
- `npm --workspace @reup-douyin/web test`: passed.
- `npm --workspace @reup-douyin/web run build`: passed.
- Build output confirms these route families compile:
  - `/`
  - `/selection/review-board`
  - `/publishing/health`
  - `/publish-control`
  - `/optimization`
  - `/ops`
  - `/production/transcript-editor/[sourceVideoId]`
  - `/production/final-review/[sourceVideoId]`
  - `/source-videos/[id]/publish`

### Remaining Rough Edges

- Recent/current work remains derived from existing home dashboard state; there is no persistent recent-history system.
- Intake and production downloads are still lightweight placeholder pages.
- Some deep pages keep their own internal page headers, so the shell topbar and page header can both appear.
- Swagger URL defaults to `http://localhost:8000/docs`; production deployment should eventually derive external docs links from environment/config.
