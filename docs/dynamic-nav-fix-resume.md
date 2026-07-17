# Dynamic Navigation Fix Resume

## Current Step

Fix Production sidebar dynamic navigation for:

- Transcript Editor
- Final Review

## Done

- Read `AGENTS.md`.
- Audited `apps/web` route structure and navigation components.
- Identified root cause in static nav config plus generic `Context` badge.
- Created required fix docs.
- Extended nav item config with per-item source-video target metadata.
- Added current source-video extraction and dynamic href/status resolvers.
- Updated `Sidebar` to store/reuse the current source-video id in `localStorage`.
- Updated `NavSection` to render resolved hrefs and clearer per-item badges.
- Added wording for `Open current video`, `Select video`, and `Select output`.
- Added route-nav tests for current-context and no-context behavior.
- Verified typecheck, tests, build, and route smoke checks.

## In Progress

- No active work remains for this fix.

## Next Exact Task

Next task if continuing: replace the lightweight `localStorage` current-source context with an API-backed recent-work source if/when the product gains a durable recent-work model.

## Key Files To Continue

- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/components/app-shell/Sidebar.tsx`
- `apps/web/src/components/app-shell/NavSection.tsx`
- `apps/web/src/test/route-nav.test.ts`
- `docs/dynamic-nav-fix-log.md`
- `docs/dynamic-nav-fix-resume.md`

## Verification Snapshot

- Typecheck: passed.
- Web tests: passed.
- Next build: passed.
- Required route smoke checks: passed.
- No-context UI labels are clear and distinct.
