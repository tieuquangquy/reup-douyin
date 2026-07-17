# Douyin Factor 1 Identity / aweme_id Fix Resume

## Current Objective

Fix only Factor 1: identity and aweme_id mapping for the real Douyin extension capture pipeline.

Status: completed and verified.

## Scope Lock

Did not fix or alter:
- thumbnail correctness,
- duration correctness,
- stats correctness,
- UI wording,
- UI layout,
- crawler, processing, scoring, queue, or publishing behavior.

## Audit Status

Completed audit of:
- apps/extension-douyin-capture/src/extractor.ts
- apps/extension-douyin-capture/src/networkCache.ts
- apps/extension-douyin-capture/src/pageNetworkHook.ts
- apps/extension-douyin-capture/src/contentScript.ts
- apps/extension-douyin-capture/src/popupTransport.ts
- apps/api/src/services/capture_inbox_service.py
- apps/api/src/schemas/douyin_extension.py
- apps/api/src/schemas/capture_inbox.py
- apps/web/src/components/capture-inbox/CaptureInboxPage.tsx

## Root Cause Fixed

Network normalization was too permissive before the canonical extractor merge. In both network cache implementations, normalizeAwemeRecord accepted fallback identity fields such as awemeId, item_id, or id as the network aweme_id. Factor 1 requires network item-level metadata to enter the canonical store only when the network item has a valid aweme_id field.

Fixed files/functions:
- apps/extension-douyin-capture/src/networkCache.ts: normalizeAwemeRecord, looksLikeAwemeRecord
- apps/extension-douyin-capture/src/pageNetworkHook.ts: normalizeAwemeRecord, looksLikeAwemeRecord

Hardening added:
- apps/extension-douyin-capture/src/extractor.ts: warn on attempted mismatched DOM/network aweme_id merge.
- apps/extension-douyin-capture/src/extractor.ts: warn on suspicious duplicate metadata bundle across distinct aweme_id values.

## Confirmed Safe Areas

Already aligned with Factor 1 and left in place:
- apps/extension-douyin-capture/src/extractor.ts uses Map<aweme_id, CanonicalItem> in extractVideos.
- apps/extension-douyin-capture/src/extractor.ts only passes exact networkById.get(awemeId) to DOM merge.
- apps/extension-douyin-capture/src/extractor.ts cloneNetworkMetadata clones url_list.
- apps/extension-douyin-capture/src/contentScript.ts mergeNetworkCacheItems keys by aweme_id after normalization.
- apps/extension-douyin-capture/src/popupTransport.ts direct fallback does not merge network metadata.
- apps/api/src/services/capture_inbox_service.py preserves per-item source_video_external_id.
- apps/web/src/components/capture-inbox/CaptureInboxPage.tsx uses stable backend item id as MediaTile key.

## Implemented Rule

- DOM item identity key: aweme_id parsed from /video/{aweme_id} only.
- Network item identity key: network.aweme_id only.
- Canonical item store remains Map<aweme_id, CanonicalItem>.
- Merge only when dom.aweme_id === network.aweme_id.
- Missing DOM aweme_id does not receive guessed network metadata.
- Missing network aweme_id does not enter network normalization or canonical merge.
- No merge by index, list position, title, source/profile URL, share URL alone, or thumbnail URL.

## Verification Checklist

Completed:
- 3 different item IDs do not receive the same merged record due to pipeline bug.
- No merge occurs when aweme_id mismatches.
- No shared url_list/object reference is reused across IDs.
- One item only receives metadata from its own identity.
- Frontend list key is stable according to backend identity.
- Network awemeId, item_id, and id aliases do not substitute for missing aweme_id.

## Tests Run

Passed:
- npm --workspace apps/extension-douyin-capture run typecheck
- npx --workspace apps/extension-douyin-capture tsx src/extractor.identity.test.ts

## Final Status

Factor 1 identity / aweme_id mapping is fixed and verified. Later factors remain intentionally untouched.