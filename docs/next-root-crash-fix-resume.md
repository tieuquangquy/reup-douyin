# Next Root Crash Fix Resume

## Current Step
Complete. Root cause isolated and mitigated with minimal-risk dev config change.

## Done
- Reviewed constraints in [`AGENTS.md`](AGENTS.md).
- Mapped root route stack in [`apps/web/src/app/layout.tsx`](apps/web/src/app/layout.tsx), [`apps/web/src/app/page.tsx`](apps/web/src/app/page.tsx), and [`apps/web/src/lib/i18n.tsx`](apps/web/src/lib/i18n.tsx).
- Reviewed and updated [`apps/web/next.config.mjs`](apps/web/next.config.mjs).
- Captured deterministic terminal errors (`ENOENT` webpack `.pack.gz`, manifest misses, chunk/CSS 404 chain).
- Confirmed duplicate concurrent Next servers and removed overlap.
- Verified critical routes and dynamic transcript route behavior after fix.
- Ran [`npm --workspace @reup-douyin/web run typecheck`](apps/web/package.json:8) successfully.

## In Progress
- None.

## Next Exact Task
1. Keep a single dev server process for [`npm --workspace @reup-douyin/web run dev`](apps/web/package.json:6).
2. If similar symptoms reappear, stop all Node dev servers, clear [`apps/web/.next`](apps/web/.next), and restart.
3. Preserve dev-only cache disable in [`apps/web/next.config.mjs`](apps/web/next.config.mjs:4) unless upgrading Next and revalidating stability.

## Key Files To Continue
- [`apps/web/next.config.mjs`](apps/web/next.config.mjs)
- [`docs/next-root-crash-fix-log.md`](docs/next-root-crash-fix-log.md)
- [`docs/next-root-crash-fix-resume.md`](docs/next-root-crash-fix-resume.md)
