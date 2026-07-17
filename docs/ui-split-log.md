# UI Split Log

## Step: Split UI Into Operator Studio And Ops Console

Time started: 2026-04-22

### Findings

- `apps/web` uses the Next.js App Router under `apps/web/src/app`.
- A shared shell already exists:
  - `components/app-shell/AppShell.tsx`
  - `components/app-shell/Sidebar.tsx`
  - `components/app-shell/Topbar.tsx`
  - `components/app-shell/PageShell.tsx`
  - `components/app-shell/OperatorStudioShell.tsx`
  - `components/app-shell/OpsConsoleShell.tsx`
- Navigation is centralized in `apps/web/src/lib/navigationConfig.ts`.
- Operator Studio home already renders at `/` through `OperatorHomePage`.
- Ops Console home already renders at `/ops` through `OpsHomePage`.
- Canonical route aliases already exist for newer grouped routes:
  - `/review-board` redirects to `/selection/review-board`
  - `/source-videos/[id]/transcript-editor` redirects to `/production/transcript-editor/[id]`
  - `/source-videos/[id]/final-review` redirects to `/production/final-review/[id]`
  - `/publish-control` redirects to `/ops/publish-control`
- `/source-videos/[id]/publish` still directly renders the publish draft page to preserve the existing business route.
- `/dashboard/publish-health` currently redirects to `/publishing/health`; for this split it should behave as the Ops publish health alias.

### Decisions Made

- Keep one Next.js app and one route tree.
- Preserve existing business URLs with redirects/aliases rather than moving page implementations.
- Treat `/` as Operator Studio and `/ops` as Ops Console.
- Keep dynamic operator work out of top-level static sidebar items; surface it through Production/Publishing context, breadcrumbs, and contextual links.
- Map legacy `/dashboard/publish-health` to Ops Console publish health.
- Preserve query parameters for `/review-board?fresh=1` when redirecting to the canonical review board route.
- Keep `/publishing/health` as an Operator-facing publish health route because the current UI already exposes it from Operator Studio quick links.

### Files Touched

- `docs/ui-split-log.md`
- `docs/ui-split-resume.md`
- `docs/ui-split-route-map.md`
- `apps/web/src/app/dashboard/publish-health/page.tsx`
- `apps/web/src/app/review-board/page.tsx`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/components/ops-console/OpsToolsPage.tsx`
- `apps/web/src/test/route-nav.test.ts`

### Verification Notes

- `npm --workspace @reup-douyin/web run typecheck`: passed.
- `npm --workspace @reup-douyin/web test`: passed.
- `npm --workspace @reup-douyin/web run build`: passed.
- Dev stack restarted with `npm run dev`.
- HTTP smoke checks passed:
  - `/` -> `200`
  - `/ops` -> `200`
  - `/review-board?fresh=1` -> `/selection/review-board?fresh=1`
  - `/selection/review-board` -> `200`
  - `/source-videos/source-1/transcript-editor` -> `/production/transcript-editor/source-1`
  - `/source-videos/source-1/final-review` -> `/production/final-review/source-1`
  - `/source-videos/source-1/publish` -> `200`
  - `/dashboard/publish-health` -> `/ops/publish-health`
  - `/publish-control` -> `/ops/publish-control`
  - `/optimization` -> `200`
- API Swagger responded at `http://127.0.0.1:8000/docs`.

### Status

Completed.
