# UI Split Resume

## Current Step

Split `apps/web` into two clear surfaces:

- Operator Studio at `/`
- Ops Console at `/ops`

## Completed

- Read `AGENTS.md`.
- Audited the current `apps/web` structure and route inventory.
- Confirmed the app uses Next.js App Router.
- Confirmed shared shell components already exist and are suitable for reuse.
- Confirmed Operator home and Ops home implementations already exist.
- Created the required UI split docs.
- Updated `/dashboard/publish-health` to route into Ops Console publish health.
- Updated `/review-board` redirect to preserve search params such as `fresh=1`.
- Updated navigation config, Swagger default URL, and route-nav tests for the split.
- Verified typecheck, tests, build, and HTTP smoke routes.

## In Progress

- No active code work remains for this step.

## Next Exact Step

Next recommended UI step: replace placeholder routes with thin API-backed list screens:

1. `/intake/profiles`
2. `/intake/crawl-sessions`
3. `/production/downloads`

## Key Files To Continue

- `apps/web/src/app/dashboard/publish-health/page.tsx`
- `apps/web/src/app/review-board/page.tsx`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/test/route-nav.test.ts`
- `docs/ui-split-log.md`
- `docs/ui-split-route-map.md`

## Verification Snapshot

- Web: `http://localhost:3000`
- Swagger: `http://127.0.0.1:8000/docs`
- Typecheck: passed.
- Web tests: passed.
- Next build: passed.
- Required route smoke checks: passed.
