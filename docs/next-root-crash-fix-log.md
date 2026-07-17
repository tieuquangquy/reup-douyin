# Next Root Crash Fix Log

## Findings
- Initial audit completed for [`AGENTS.md`](AGENTS.md), [`apps/web/src/app/layout.tsx`](apps/web/src/app/layout.tsx), [`apps/web/src/app/page.tsx`](apps/web/src/app/page.tsx), [`apps/web/src/lib/i18n.tsx`](apps/web/src/lib/i18n.tsx), and [`apps/web/next.config.mjs`](apps/web/next.config.mjs).
- App uses Next.js App Router via [`apps/web/src/app`](apps/web/src/app/layout.tsx).
- Route `/` is served by [`HomePage`](apps/web/src/app/page.tsx:3) wrapped by [`RootLayout`](apps/web/src/app/layout.tsx:10) and [`I18nProvider`](apps/web/src/lib/i18n.tsx:50).
- Deterministic failure signal captured from dev terminal: `ENOENT` for webpack persistent cache pack files under [`.next/cache/webpack/*/*.pack.gz`](apps/web/.next/cache/webpack) followed by missing static chunk/CSS 404s and React Client Manifest resolution errors.
- Concurrent Next dev servers were observed on ports `3000` and `3001` at the same time, indicating overlapping dev processes amplified cache/manifest inconsistency.
- Minimal-risk stabilization is to disable webpack persistent cache only in dev via [`webpack(config, { dev })`](apps/web/next.config.mjs:4), setting [`config.cache = false`](apps/web/next.config.mjs:8) when `dev`.

## Commands Run
- [`npm --workspace @reup-douyin/web run dev`](apps/web/package.json:6)
- Route probes using PowerShell `Invoke-WebRequest` across `/`, `/intake`, `/review-board`, `/accounts/douyin`, `/ops`, `/ops/publish-health`, `/ops/publish-control`, and `/source-videos/test-id/transcript-editor`.
- Port/process inspection via `Get-NetTCPConnection` and `Get-CimInstance Win32_Process`.
- Forced cleanup of duplicate dev servers via `taskkill /PID ... /F`.
- [`npm --workspace @reup-douyin/web run typecheck`](apps/web/package.json:8).

## Root Cause
- Primary root cause: unstable Next.js 15 dev-time webpack persistent cache artifacts on Windows (`ENOENT` on `.pack.gz` files) causing manifest/chunk mismatch and fallback error rendering.
- Secondary aggravator: duplicate concurrent Next dev server processes (3000 + 3001) increased inconsistent cache/manifest state.
- This is runtime/tooling-state failure, not a business-logic crash in [`apps/web/src/app/page.tsx`](apps/web/src/app/page.tsx:1), [`apps/web/src/app/layout.tsx`](apps/web/src/app/layout.tsx:1), or [`apps/web/src/lib/i18n.tsx`](apps/web/src/lib/i18n.tsx:1).

## Files Touched
- [`apps/web/next.config.mjs`](apps/web/next.config.mjs)
- [`docs/next-root-crash-fix-log.md`](docs/next-root-crash-fix-log.md)
- [`docs/next-root-crash-fix-resume.md`](docs/next-root-crash-fix-resume.md)

## Verification Notes
- After applying dev-only cache disable and removing duplicate servers, route verification returned `200` for:
  - `/`, `/intake`, `/review-board` (redirect to `/selection/review-board` then `200`), `/accounts/douyin`, `/ops`, `/ops/publish-health`, `/ops/publish-control`, `/source-videos/test-id/transcript-editor` (redirect chain to production transcript route then `200`).
- [`npm --workspace @reup-douyin/web run typecheck`](apps/web/package.json:8) passed.

## Status
- Done: root cause isolated and mitigated with minimal-risk config change in [`apps/web/next.config.mjs`](apps/web/next.config.mjs).
