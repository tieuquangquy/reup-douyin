# Ops Route Migration Resume

## Current Step

Move publish operations screens under `/ops` and remove ops links from Operator Studio primary navigation.

## Done

- Read `AGENTS.md`.
- Audited `apps/web` route structure and navigation config.
- Confirmed Next.js App Router is used.
- Confirmed canonical `/ops/publish-health` and `/ops/publish-control` routes exist and reuse existing page components.
- Created the required migration docs.
- Removed Publish Health and Publish Control from Operator Studio sidebar/topbar quick actions.
- Removed publish health/control from Operator home quick launch and kept a single Ops Console launch.
- Redirected `/publishing/health` to `/ops/publish-health`.
- Updated operator contextual links to use canonical `/ops/publish-health` and `/ops/publish-control`.
- Updated route-nav and operator-home tests.
- Verified typecheck, tests, build, required route smoke checks, and shell text checks.

## In Progress

- No active code work remains for this migration step.

## Next Exact Step

Next cleanup step: remove or relabel old docs references that still describe `/publishing/health` as an Operator route, while keeping the runtime redirect in place for compatibility.

## Key Files To Continue

- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/lib/operatorHomeState.ts`
- `apps/web/src/app/publishing/health/page.tsx`
- `apps/web/src/app/optimization/page.tsx`
- `apps/web/src/components/operator-routes/OperatorPublishDraftPage.tsx`
- `apps/web/src/components/operator-routes/PublishDraftsIndexPage.tsx`
- `apps/web/src/components/publish-draft/PublishDraftHeader.tsx`
- `apps/web/src/test/route-nav.test.ts`
- `docs/ops-route-migration-log.md`
- `docs/ops-route-migration-map.md`

## Verification Snapshot

- Web: `http://localhost:3000`
- Swagger: `http://127.0.0.1:8000/docs`
- Typecheck: passed.
- Web tests: passed.
- Next build: passed.
- Required HTTP route checks: passed.
