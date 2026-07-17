# Dynamic Navigation Fix Log

## Step: Fix Dynamic Navigation For Transcript Editor And Final Review

### Findings

- `apps/web` uses Next.js App Router.
- Production sidebar items are configured in `apps/web/src/lib/navigationConfig.ts`.
- `Transcript Editor` and `Final Review` are separate nav items with separate active patterns.
- Both items currently share the same fallback `href: "/selection/review-board"`.
- Both items currently use `status: "context"`, which `NavSection.tsx` renders as the same generic `Context` badge.
- Dynamic route aliases exist and work:
  - `/source-videos/[id]/transcript-editor` redirects to `/production/transcript-editor/[id]`
  - `/source-videos/[id]/final-review` redirects to `/production/final-review/[id]`
- Current source-video context is available from dynamic route path segments when the operator is already inside source-video work.

### Root Cause

The nav model only supports a static `href` plus a generic `context` badge. It does not let `Transcript Editor` and `Final Review` resolve separate dynamic destinations from the current source video, so both items fall back to the same URL and the same label.

### Decision Made

- Add a small source-video navigation resolver in the web shell.
- Current source-video strategy:
  - Extract `sourceVideoId` from the current route when on a source-video workflow page.
  - Store that id in `localStorage` as lightweight last-current source context.
  - Reuse that id for Production sidebar actions in the same browser session.
- When current context exists:
  - `Transcript Editor` links to `/source-videos/{id}/transcript-editor`.
  - `Final Review` links to `/source-videos/{id}/final-review`.
- When no current context exists:
  - `Transcript Editor` links to `/selection/review-board` with `Select video`.
  - `Final Review` links to `/publishing/drafts` with `Select output`.
- Replace generic `Context` wording for these two items with clearer dynamic badges.

### Files Touched

- `docs/dynamic-nav-fix-log.md`
- `docs/dynamic-nav-fix-resume.md`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/components/app-shell/Sidebar.tsx`
- `apps/web/src/components/app-shell/NavSection.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/test/route-nav.test.ts`

### Verification

- `node` JSON parse for `en.json` and `vi.json`: passed.
- `npm --workspace @reup-douyin/web run typecheck`: passed.
- `npm --workspace @reup-douyin/web test`: passed.
- `npm --workspace @reup-douyin/web run build`: passed.
- Restarted dev stack and removed stale port-3000 listener.
- HTTP smoke checks passed:
  - `/`
  - `/review-board`
  - `/selection/review-board`
  - `/source-videos/source-1/transcript-editor`
  - `/source-videos/source-1/final-review`
  - `/source-videos/source-1/publish`
  - `/production/transcript-editor/source-1`
  - `/production/final-review/source-1`
  - `/optimization`
- Route-nav tests verify:
  - `Transcript Editor` resolves to `/source-videos/source-1/transcript-editor` when current source video exists.
  - `Final Review` resolves to `/source-videos/source-1/final-review` when current source video exists.
  - No-context fallbacks differ: `/selection/review-board` and `/publishing/drafts`.
  - Badge labels differ in no-context state: `Select video` and `Select output`.
- SSR HTML check for `/` includes `Transcript Editor`, `Final Review`, `Select video`, and `Select output`.

### Status

Completed.
