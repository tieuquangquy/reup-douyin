# Douyin Frontend Canonical Rendering Log

## Scope

Part 3 updated the Capture Inbox frontend so visible Douyin profile-grid items render canonical thumbnail and metadata fields consistently. The change was limited to `apps/web`, Capture Inbox UI rendering, frontend resolver helpers, and related tests/docs.

## Audit Findings

- Main Capture Inbox tiles resolved thumbnails through component-local helper logic in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- Tile metadata chips and the right inspector used different logic for duration, posted time, thumbnail, preview status, and media status.
- Metric formatting fell back to generic `Pending`, which was misleading for views, likes, and comments when values were simply not captured.
- The right inspector derived media status from `media_ready`, causing `source_link_captured` captures to appear as generic pending-like state.
- Frontend Capture Inbox item types did not include the backend-supported `pending` status literal for preview/media fields.
- Thumbnail CSS already used `object-fit: cover`, which is acceptable for Douyin portrait covers inside the existing tile frame without a layout redesign.

## Implementation Completed

- Added `apps/web/src/lib/captureInboxCanonical.ts` as the shared canonical resolver layer.
- Implemented required helpers:
  - `resolveThumbnailUrl(item)`
  - `resolveDuration(item)`
  - `resolvePosted(item)`
  - `resolveViewCount(item)`
  - `resolveLikeCount(item)`
  - `resolveCommentCount(item)`
  - `resolvePreviewStatus(item)`
  - `resolveMediaStatus(item)`
- Updated `apps/web/src/types/capture-inbox.ts` so `preview_status` and `media_status` include `pending`.
- Updated `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` so:
  - the only-with-thumbnail filter uses `resolveThumbnailUrl(item)`;
  - media tiles render real images when a canonical/resolved thumbnail exists;
  - thumbnail placeholder text is `Thumbnail not captured` instead of a generic old placeholder;
  - metadata chips use shared resolvers for duration, posted, views, likes, comments, preview, and media;
  - the right inspector overview/status rows use the same shared resolvers;
  - preview URL fallback uses resolved preview status instead of blindly displaying `Pending`;
  - media status no longer uses `item.media_ready ? "Ready" : "Pending"`.
- Kept debug thumbnail logging safe and non-production-only.
- Added `apps/web/src/test/capture-inbox-canonical.test.ts` to execute real resolver behavior against a Douyin visible profile-grid-like item.
- Updated `apps/web/src/test/capture-inbox.test.ts` static assertions for the shared resolver architecture and consistency.
- Added the Capture Inbox tests to the web app `test` script.

## Verification

Command run from repository root:

```bat
npm --workspace apps/web exec -- tsx src/test/capture-inbox.test.ts && npm --workspace apps/web exec -- tsx src/test/capture-inbox-canonical.test.ts && npm --workspace apps/web run typecheck
```

Result: passed.

Observed output:

```text
capture inbox Media-first Triage Studio, canonical rendering, session ribbon, status strip, filter toolbar, right-side inspector, state sync, action hierarchy, and polish tests passed
capture inbox canonical resolver behavior tests passed

> typecheck
> tsc --noEmit -p tsconfig.typecheck.json
```

## Real Douyin Visible Profile-Grid Verification

The executable canonical resolver test constructs a profile-grid-like item with:

- canonical `thumbnail_url` from a Douyin image host;
- canonical `duration_text` and `duration_seconds`;
- canonical `posted_at` and `posted_text`;
- canonical numeric and raw text views/likes/comments;
- `preview_status = "ready"`;
- `media_status = "source_link_captured"`.

Assertions confirm the frontend:

- renders canonical `thumbnail_url` before raw fallback aliases;
- shows canonical duration text;
- formats canonical posted timestamp before using posted text;
- shows numeric view/like/comment values first;
- preserves text metrics when numeric values are absent;
- shows `Source link captured` instead of generic `Pending` for source-link-only captures;
- uses `Not captured` for missing metrics instead of fake or pending values.
