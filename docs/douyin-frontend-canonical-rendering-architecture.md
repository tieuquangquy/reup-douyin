# Douyin Frontend Canonical Rendering Architecture

## Goal

The Capture Inbox frontend renders backend canonical metadata fields consistently for real Douyin visible profile-grid captures. Operators see real thumbnails and metadata whenever available, and do not see generic pending/missing placeholders when canonical data exists.

## Boundary

`apps/web` owns UI rendering and browser-safe presentation logic only. It must not perform crawling, video processing, scoring, queue orchestration, or direct persistence. Backend/API remains the source of canonical Capture Inbox item fields.

## Canonical Resolver Layer

Capture Inbox item presentation routes through shared frontend resolvers in `apps/web/src/lib/captureInboxCanonical.ts`:

- `resolveThumbnailUrl(item)`
- `resolveDuration(item)`
- `resolvePosted(item)`
- `resolveViewCount(item)`
- `resolveLikeCount(item)`
- `resolveCommentCount(item)`
- `resolvePreviewStatus(item)`
- `resolveMediaStatus(item)`

These helpers centralize canonical-first logic so the gallery tile and right inspector cannot drift.

## Field Precedence

- Thumbnail: prefer `thumbnail_url`; only use bounded image-like fallbacks when canonical thumbnail is absent.
- Duration: prefer `duration_text`; otherwise derive from `duration_seconds`; otherwise show `Not captured`.
- Posted: prefer formatted `posted_at`; otherwise use `posted_text`; otherwise show `Not captured`.
- Metrics: prefer canonical numeric counts; use canonical text only when numeric value is absent; otherwise show `Not captured`.
- Preview status: map canonical status to truthful labels: `Ready`, `Pending`, or `Missing`.
- Media status: map canonical status to truthful labels: `Ready`, `Pending`, `Missing`, or `Source link captured`.

## UI Consumers

`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` uses the shared resolvers for:

- only-with-thumbnail filtering;
- tile thumbnail rendering;
- tile metadata chips;
- right inspector overview duration/posted fields;
- right inspector source thumbnail link;
- right inspector preview/media status fields;
- preview URL fallback status.

## Wording Rules

- Do not show `Pending` for absent engagement metrics; use `Not captured`.
- Do not show `Pending` for `source_link_captured` media; use `Source link captured`.
- Do not show missing-thumbnail placeholders when `resolveThumbnailUrl(item)` returns a real URL.
- Do not fake values from unrelated fields.

## Real Douyin Profile-Grid Case

For visible profile-grid captures, the extension/backend path can provide cover image URLs, duration/posted text, and engagement metrics. The frontend displays those canonical fields directly through the resolver layer rather than hiding them behind `Pending`, `Missing`, or generic thumbnail placeholders.

## Test Coverage

- `apps/web/src/test/capture-inbox.test.ts` asserts the static UI architecture uses shared canonical resolvers and avoids stale ad hoc status logic.
- `apps/web/src/test/capture-inbox-canonical.test.ts` executes resolver behavior against a real Douyin visible profile-grid-like item and verifies thumbnail, metadata, and status outputs.
- `apps/web/package.json` includes both Capture Inbox tests in the normal web test script.
