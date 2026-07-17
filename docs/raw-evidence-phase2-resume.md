# Phase 2 Raw Evidence Collection Resume

## Current Task

Implement raw evidence collection from the Douyin extension so backend Phase 3 can normalize Time, Performance, and Processing fit reliably.

## Files Expected To Change

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/networkCache.ts`
- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts` only for the direct DOM fallback mirror path
- extension tests near existing extractor/network identity tests
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/capture_inbox_service.py`
- API tests near `test_douyin_extension_capture_service.py`

## Implementation Notes

1. Add raw evidence types to extension payload types.
2. Bound and sanitize raw aweme objects in the network collector.
3. Store raw network evidence on normalized network metadata for exact-id lookup.
4. Store raw detail evidence separately when the source represents detail/hydrate evidence.
5. Build an item-local DOM snapshot from the discovered link/card.
6. Attach `raw_network_aweme`, `raw_detail_aweme`, `raw_dom_snapshot`, and `raw_evidence_summary` to each `VideoPayload`.
7. Add optional API schema fields and persist them during staging.
8. Keep current canonical fields as-is except where needed to carry raw evidence.

## Non-Goals To Preserve

- Do not decide canonical truth in the extension.
- Do not implement a backend normalizer.
- Do not add hydration jobs.
- Do not alter Capture Inbox UI/filter behavior.
- Do not use non-exact matching for raw network/detail evidence.

## Test Targets

- `normalizeDouyinNetworkPayload` returns bounded raw evidence on matching items.
- `extractVideos` attaches raw evidence only to matching `aweme_id` payloads.
- `extractVideos` includes item-local DOM snapshot and summary diagnostics.
- `DouyinExtensionVideoPayload` accepts raw evidence fields.
- `CaptureInboxService._build_item` persists raw evidence fields in staged metadata/raw payload.

## Validation Commands

From repo root on Windows cmd:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run test
cd apps\api && python -m unittest tests.test_douyin_extension_capture_service
```
