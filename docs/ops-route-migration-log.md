# Ops Route Migration Log

## Step: Move Ops Screens Under `/ops` And Clean Operator Studio Navigation

Time started: 2026-04-22

### Current Findings

- `apps/web` uses Next.js App Router under `apps/web/src/app`.
- Shared shell/navigation already exists:
  - `apps/web/src/lib/navigationConfig.ts`
  - `apps/web/src/components/app-shell/AppShell.tsx`
  - `apps/web/src/components/app-shell/Sidebar.tsx`
  - `apps/web/src/components/app-shell/Topbar.tsx`
  - `apps/web/src/components/app-shell/OperatorStudioShell.tsx`
  - `apps/web/src/components/app-shell/OpsConsoleShell.tsx`
- Canonical Ops pages already exist:
  - `/ops`
  - `/ops/publish-health`
  - `/ops/publish-control`
- Legacy ops routes already redirect:
  - `/dashboard/publish-health` -> `/ops/publish-health`
  - `/publish-control` -> `/ops/publish-control`
- Remaining issue: Operator Studio navigation still exposes Publish Health and Publish Control in the Operator sidebar/topbar/home quick launch.
- Remaining issue: `/publishing/health` still renders the publish health page as an Operator-facing route.

### Routes Audited

- `/dashboard/publish-health`
- `/publish-control`
- `/ops/publish-health`
- `/ops/publish-control`
- `/review-board`
- `/source-videos/[id]/transcript-editor`
- `/source-videos/[id]/final-review`
- `/source-videos/[id]/publish`
- `/optimization`

### Decisions Made

- Keep `/ops/publish-health` and `/ops/publish-control` as canonical.
- Keep `/dashboard/publish-health`, `/publish-control`, and `/publishing/health` as transitional redirects to canonical Ops routes.
- Do not duplicate publish health or publish control business logic.
- Remove Publish Health and Publish Control from Operator Studio sidebar and topbar quick actions.
- Keep one explicit Operator-to-Ops switch via topbar and Ops quick launch.
- Update operator contextual links that need publish operations to point to `/ops/...`.

### Files Touched

- `docs/ops-route-migration-log.md`
- `docs/ops-route-migration-resume.md`
- `docs/ops-route-migration-map.md`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/lib/operatorHomeState.ts`
- `apps/web/src/app/publishing/health/page.tsx`
- `apps/web/src/app/optimization/page.tsx`
- `apps/web/src/components/operator-routes/OperatorPublishDraftPage.tsx`
- `apps/web/src/components/operator-routes/PublishDraftsIndexPage.tsx`
- `apps/web/src/components/publish-draft/PublishDraftHeader.tsx`
- `apps/web/src/test/operator-home.test.ts`
- `apps/web/src/test/route-nav.test.ts`

### Verification Status

- `npm --workspace @reup-douyin/web run typecheck`: passed.
- `npm --workspace @reup-douyin/web test`: passed.
- `npm --workspace @reup-douyin/web run build`: passed.
- Restarted the local dev stack with `npm run dev`.
- HTTP smoke checks passed:
  - `/` -> `200`
  - `/review-board` -> `/selection/review-board`
  - `/source-videos/source-1/transcript-editor` -> `/production/transcript-editor/source-1`
  - `/source-videos/source-1/final-review` -> `/production/final-review/source-1`
  - `/source-videos/source-1/publish` -> `200`
  - `/optimization` -> `200`
  - `/ops` -> `200`
  - `/ops/publish-health` -> `200`
  - `/ops/publish-control` -> `200`
  - `/dashboard/publish-health` -> `/ops/publish-health`
  - `/publish-control` -> `/ops/publish-control`
  - `/publishing/health` -> `/ops/publish-health`
- HTML checks:
  - `/` does not include Operator menu text for `Publish Health` or `Publish Control`.
  - `/` includes `Ops Console` switch and `Review Board`.
  - `/ops` includes `Publish Health`, `Publish Control`, `Swagger`, and `Open Operator Studio`.

### Status

Completed.
