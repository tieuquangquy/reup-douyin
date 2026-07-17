# Douyin Identity Fan-out Fix Log

## Scope

This log tracks the hard fix for the Douyin capture identity/mapping/fan-out bug where multiple distinct video IDs could display the same thumbnail, title, posted value, stats, or metadata.

## Required Identity Boundary

- `aweme_id` is the only authoritative item-level merge key.
- DOM records may use a video URL only to extract a candidate `aweme_id`.
- Network JSON records must not enter canonical item storage unless they have a non-empty `aweme_id`.
- DOM and network data may merge only when both sides resolve to the same non-empty `aweme_id`.
- Merge must never use profile URL, source URL alone, share URL alone, title, thumbnail URL, list index, loop order, or object position as the item identity.

## Root Cause Addressed

The extension already looked up network metadata by DOM-derived video ID, but the merge helper trusted the caller-provided network object and did not independently reject mismatched IDs. That meant a future caller bug, stale cache shape, or accidental object reuse could fan out one network payload into multiple distinct DOM items.

## Implemented Changes

### Extension

- Refactored visible item capture around `Map<aweme_id, CanonicalItem>` in `apps/extension-douyin-capture/src/extractor.ts`.
- Added a merge-helper identity guard so network metadata is used only when `network.aweme_id === dom.aweme_id`.
- Added `rejected_network_identity_mismatch` diagnostics and `network_identity_mismatch_count` batch diagnostics.
- Added `suspicious_duplicate_payload_mapping_count` diagnostics for distinct `aweme_id` values sharing the same network-backed metadata signature.
- Added `thumbnail_source` and `posted_source` provenance fields.
- Added `validNetworkPostedAt()` to reject invalid/default-midnight network timestamps and fall back to DOM text/time.
- Cloned network metadata and `url_list` arrays to avoid mutable shared references.
- Hardened `apps/extension-douyin-capture/src/networkCache.ts`, `apps/extension-douyin-capture/src/pageNetworkHook.ts`, and `apps/extension-douyin-capture/src/contentScript.ts` to trim/filter IDs, merge only by `aweme_id`, and clone URL arrays.

### Backend

- Updated `apps/api/src/schemas/douyin_extension.py` so extension payload validation accepts `thumbnail_source` and `posted_source`.
- Updated `apps/api/src/services/capture_inbox_service.py` so staged item metadata preserves `thumbnail_source`, `posted_source`, and `network_source` per item.
- Added `_suspicious_duplicate_payload_mapping_count()` and warning code propagation for `suspicious_duplicate_payload_mapping`.
- Updated `apps/api/src/schemas/capture_inbox.py` to expose safe provenance fields on captured item responses.

### Frontend

- Confirmed media tiles are keyed by backend item `id`, not array index, thumbnail URL, or `aweme_id`.
- Confirmed active/focused item state resolves by backend item `id`.
- Added `thumbnail_source` and `posted_source` to `apps/web/src/types/capture-inbox.ts`.
- Added safe debug fields to `capture_inbox_thumbnail_resolved`: backend item ID, `aweme_id`, thumbnail provenance, posted provenance, and network source indicator.
- Added resolver regression coverage for two distinct items with distinct metadata to prevent sibling leakage/fan-out.

## Verification

Passed:

- `npm --prefix apps/extension-douyin-capture test`
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`
- `npx tsx src/test/capture-inbox.test.ts && npx tsx src/test/capture-inbox-canonical.test.ts` from `apps/web`
- `npm --prefix apps/web run typecheck`

## Final Status

Implemented and verified. The Capture pipeline now treats `aweme_id` as the strict extension merge boundary, preserves per-item backend metadata/provenance, reports suspicious duplicate network-backed signatures, and keeps frontend rendering item-local by backend item ID.

## Limitations

- `suspicious_duplicate_payload_mapping` is a warning diagnostic, not a hard rejection, because legitimately similar videos may share thumbnails or metrics.
- Direct execute-script fallback remains DOM-only and does not hydrate network metadata.
- No crawler, video processing, queue, worker, publishing, or database schema work was added.
