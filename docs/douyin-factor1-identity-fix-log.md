# Douyin Factor 1 Identity / aweme_id Fix Log

## Scope Lock

This log is for Factor 1 only: identity and aweme_id mapping in the real Douyin extension capture pipeline.

Explicit non-goals for this pass:
- No thumbnail correctness fixes.
- No duration correctness fixes.
- No stats correctness fixes.
- No UI wording or layout changes.
- No crawler, video processing, scoring, queue, or publishing work.

## Audit Summary

### DOM card extraction

Audited files/functions:
- apps/extension-douyin-capture/src/extractor.ts: extractVideos, collectVideoLinks, videoIdFromUrl, mergeDomAndNetworkVideo.
- apps/extension-douyin-capture/src/popupTransport.ts: direct execution fallback extractVideos.

Findings:
- The content-script extractor already builds a canonical item store as Map<aweme_id, CanonicalItem>.
- DOM identity is parsed from Douyin /video/{id} hrefs.
- DOM links with no parsed ID are skipped and do not receive network metadata.
- The direct execution fallback is DOM-only and does not attach network metadata.

### Network JSON cache

Audited files/functions:
- apps/extension-douyin-capture/src/networkCache.ts: normalizeAwemeRecord, mergeItems.
- apps/extension-douyin-capture/src/pageNetworkHook.ts: normalizeAwemeRecord, mergeItems.
- apps/extension-douyin-capture/src/contentScript.ts: mergeNetworkCacheItems.

Findings:
- The network caches merge by trimmed aweme_id once normalized.
- Empty IDs are skipped during cache merge.
- Returned cache items clone url_list arrays.
- Root identity weakness found: network normalization accepted awemeId, item_id, or id as substitutes for aweme_id. For this Factor 1 requirement, that was too permissive because network item-level metadata must only enter the canonical merge path when the network record itself has a valid aweme_id.

### Merge logic

Audited files/functions:
- apps/extension-douyin-capture/src/extractor.ts: extractVideos, canonicalNetworkMap, mergeNetworkMetadata, cloneNetworkMetadata, mergeDomAndNetworkVideo.

Findings:
- The visible item store is keyed by DOM aweme_id.
- canonicalNetworkMap skips empty IDs and merges only same-ID network records.
- mergeDomAndNetworkVideo only reads network metadata when networkInput.aweme_id equals the DOM aweme_id.
- No merge by index, list position, title, source/profile URL, share URL alone, or thumbnail URL was found in the primary extractor.
- Existing diagnostics count suspicious duplicate metadata bundles; this pass added explicit identity-only warnings.

### Backend integrity

Audited files/functions:
- apps/api/src/services/capture_inbox_service.py: _build_item, _suspicious_duplicate_payload_mapping_count, _warning_codes_for_stage.
- apps/api/src/schemas/douyin_extension.py: DouyinExtensionVideoPayload.
- apps/api/src/schemas/capture_inbox.py: CapturedItemResponse.hydrate_card_grid_metadata.

Findings:
- _build_item preserves item identity as source_video_external_id from aweme_id, video_id, id, or URL fallback.
- CapturedItemResponse exposes aweme_id from source_video_external_id.
- Backend suspicious duplicate payload mapping warning already exists.
- No backend object-template reuse issue was found in this audit.

### Frontend identity

Audited files/functions:
- apps/web/src/components/capture-inbox/CaptureInboxPage.tsx: SessionRibbon, MediaTileGallery.

Findings:
- Session rows use key={session.id}.
- Media tiles use key={item.id}, not array index.
- No frontend React-key identity bug was found in this audit.

## Root Cause

Primary Factor 1 root cause: network record normalization was too permissive in the real extension network-cache path. Both apps/extension-douyin-capture/src/networkCache.ts and apps/extension-douyin-capture/src/pageNetworkHook.ts allowed non-aweme fields (awemeId, item_id, id) to become the canonical network aweme_id. This violated the Factor 1 rule that network item-level metadata may enter the canonical store only when a network item has its own aweme_id.

Bug locations:
- apps/extension-douyin-capture/src/networkCache.ts: normalizeAwemeRecord.
- apps/extension-douyin-capture/src/pageNetworkHook.ts: normalizeAwemeRecord.

Secondary hardening gap: the primary extractor recorded rejected network identity mismatches in diagnostics, but did not emit explicit debug warnings for attempted mismatched merges or suspicious fan-out signatures.

## Implemented New Merge Rule

- DOM item identity key: aweme_id parsed from /video/{aweme_id} only.
- Network item identity key: network.aweme_id only.
- Canonical item store: Map<aweme_id, CanonicalItem>.
- Merge allowed only when dom.aweme_id === network.aweme_id.
- Missing DOM aweme_id: skip item-level network merge.
- Missing network aweme_id: do not normalize into the network cache and do not merge into canonical store.
- Forbidden merge keys remain forbidden: index, list position, title, source/profile URL, share URL alone, thumbnail URL.

## Changes Made

- apps/extension-douyin-capture/src/networkCache.ts
  - normalizeAwemeRecord now uses only record.aweme_id as network identity.
  - looksLikeAwemeRecord now requires record.aweme_id plus item-like evidence before normalizing.
- apps/extension-douyin-capture/src/pageNetworkHook.ts
  - Mirrored the same network aweme_id-only normalization in the injected page hook used by the real browser pipeline.
- apps/extension-douyin-capture/src/extractor.ts
  - Added warnIdentityMappingIssue.
  - Added warning for attempted mismatched DOM/network aweme_id merge.
  - Added warning for suspicious duplicate metadata bundle fan-out across distinct aweme_id values.
- apps/extension-douyin-capture/src/extractor.identity.test.ts
  - Added identity-only verification that awemeId, item_id, and id alias-only network records do not enter the network cache or attach metadata.
  - Kept existing exact aweme_id merge, mismatch rejection, DOM-order, and url_list reference isolation checks.

## Anti-Fan-Out Safeguards

- Mismatched network aweme_id presented to mergeDomAndNetworkVideo logs an identity mapping safeguard warning and is rejected.
- Suspicious duplicate metadata bundles across different aweme_id values log an identity mapping safeguard warning.
- Alias-only network identity fields no longer enter NetworkVideoMetadata normalization.
- Cache merge, canonical merge, and final payload construction continue to clone url_list arrays so distinct IDs do not reuse the same url_list object reference.

## Tests Run

Passed:
- npm --workspace apps/extension-douyin-capture run typecheck
- npx --workspace apps/extension-douyin-capture tsx src/extractor.identity.test.ts

## Verification Result

Pass.

Evidence:
- Three different DOM item IDs remain in visible DOM order and only receive network records matching the same aweme_id.
- No merge occurs for unmatched or missing network aweme_id records.
- Alias-only network identity fields awemeId, item_id, and id do not normalize into the network cache.
- url_list arrays are not the same object reference across distinct IDs.
- Frontend MediaTile rendering uses stable backend item.id keys, not array index.

## Remaining Non-Goals

Thumbnail, duration, stats, and UI behavior were intentionally not fixed in this Factor 1 pass.