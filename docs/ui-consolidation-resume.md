# UI Consolidation Resume

## Current Step

Sidebar / Topbar / Navigation Flow refinement for `apps/web`.

## Done

- Audited current shell/navigation structure and full `apps/web` route layout.
- Rebuilt navigation config around maintainable sidebar groups, quick actions, active patterns, and breadcrumb rules.
- Removed raw dynamic routes from sidebar and replaced them with workflow/context items.
- Added consistent breadcrumbs to the topbar.
- Added practical topbar quick links and surface switching between Operator Studio and Ops Console.
- Added contextual shell actions on review, transcript, final review, publish draft, publish health, optimization, and key ops pages.
- Added route-nav tests for active state and breadcrumb behavior.
- Fixed a misplaced duplicate `"use client"` directive in `PublishControlPlanePage.tsx` that blocked Next build verification.
- Created `docs/ui-consolidation-log.md` and `docs/ui-consolidation-route-map.md`.

## In Progress

- No code work is currently in progress for this step.
- Remaining navigation polish should be driven by real operator usage after this structure is exercised.

## Next Recommended UI Step

Replace the placeholder operator routes with thin API-backed list screens, starting with:

- `/intake/profiles`
- `/intake/crawl-sessions`
- `/production/downloads`

This would make the new sidebar groups feel fully operational without changing the existing production workflow routes.

## Key Files Touched

- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/components/app-shell/Sidebar.tsx`
- `apps/web/src/components/app-shell/NavSection.tsx`
- `apps/web/src/components/app-shell/Topbar.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/components/operator-routes/*`
- `apps/web/src/app/publishing/health/page.tsx`
- `apps/web/src/app/optimization/page.tsx`
- `apps/web/src/app/ops/page.tsx`
- `apps/web/src/app/ops/publish-control/page.tsx`
- `apps/web/src/app/ops/publish-health/page.tsx`
- `apps/web/src/test/route-nav.test.ts`

## Known Limitations

- No new product workflow or backend API was added.
- No persistent recent-work table or browser history feature was introduced.
- Dynamic route labels intentionally stay generic in breadcrumbs: `Transcript Editor`, `Final Review`, and `Publish Draft`.
- Mobile behavior degrades to stacked sidebar/topbar layout; desktop remains the primary target for this step.
