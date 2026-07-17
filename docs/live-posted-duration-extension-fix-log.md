# Live Posted/Duration Extension Fix Log (Part B only)

## Task

Part B only: fix live metadata extraction/normalization for posted + duration in extension path.

In scope fields only:

- `posted_at`
- `posted_text`
- `duration_seconds`
- `duration_text`

Out of scope:

- views/likes/comments/shares
- backend persistence/API
- frontend UI

## Baseline from Part A

Using [`docs/live-metadata-gap-audit-log.md`](./live-metadata-gap-audit-log.md), extension currently applies canonical priority in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:680), but live behavior still reports `Posted Not captured` and `Duration Not captured` in UI.

Working hypothesis for Part B:

- posted/duration values can be present upstream but rejected or degraded by extension normalization guards in some real payload shapes
- stricter trust guards and exact-id source selection are required
- no cross-item leakage must remain guaranteed

## Required source priority

For both posted and duration:

1. exact network JSON by `aweme_id`
2. exact detail hydrate by `aweme_id`
3. item-local DOM fallback only when trustworthy
4. otherwise missing

## Planned changes (before implementation)

Target files (extension-only):

- [`apps/extension-douyin-capture/src/extractor.ts`](../apps/extension-douyin-capture/src/extractor.ts)
- [`apps/extension-douyin-capture/src/popupTransport.ts`](../apps/extension-douyin-capture/src/popupTransport.ts) (parity path if needed)
- extension tests for posted/duration behaviors only

No backend/frontend changes in Part B.

## Verification plan

Focused tests to add/update:

1. exact network posted maps to canonical posted
2. detail posted fills only when network missing
3. exact network duration maps to canonical duration
4. detail duration fills only when network missing
5. bad posted values rejected
6. bad duration values rejected
7. no cross-item leakage
8. popupTransport parity retained

## Implementation results

Changed files:

- [`apps/extension-douyin-capture/src/extractor.ts`](../apps/extension-douyin-capture/src/extractor.ts)
- [`apps/extension-douyin-capture/src/popupTransport.ts`](../apps/extension-douyin-capture/src/popupTransport.ts)
- [`apps/extension-douyin-capture/src/extractor.test.ts`](../apps/extension-douyin-capture/src/extractor.test.ts)

Function-level changes:

1. [`extractDuration()`](../apps/extension-douyin-capture/src/extractor.ts:646)
   - Added strict segment validation (`mm:ss` seconds < 60, `hh:mm:ss` minutes/seconds < 60).
   - Rejects malformed but regex-matching durations instead of emitting misleading canonical values.

2. [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:680)
   - Kept canonical posted timestamp priority: network → detail → DOM parsed fallback.
   - Changed posted source derivation to rely on `domPostedAt` (trusted parsed value) for DOM provenance.
   - Changed [`posted_text`](../apps/extension-douyin-capture/src/types.ts:103) output to canonical priority (`networkPostedAt ?? detailPostedAt ?? dom posted_text ?? null`) so authoritative upstream posted data is no longer dropped when DOM text is absent.

3. [`validDurationText()`](../apps/extension-douyin-capture/src/extractor.ts:999)
   - Enforces bounded segment semantics for trusted canonical duration text:
     - `mm:ss` → seconds < 60
     - `hh:mm:ss` → minutes < 60 and seconds < 60

4. [`extractDuration()`](../apps/extension-douyin-capture/src/popupTransport.ts:897)
   - Applied same strict duration segment validation for direct execute-script fallback parity.

5. [`extractor.test.ts`](../apps/extension-douyin-capture/src/extractor.test.ts:152)
   - Updated posted assertion to verify canonical posted priority behavior.
   - Added assertion verifying DOM posted provenance only when parsed DOM timestamp is valid.

## Verification results

Command run:

- [`npm run extension:test`](../package.json:24)

Observed result: pass (exit code 0)

- `extension extractor tests passed`
- `extension identity / aweme_id mapping tests passed`
- `popup action hardening tests passed`
- `extension direct execution transport tests passed`
- extension build + dist module resolution tests passed
