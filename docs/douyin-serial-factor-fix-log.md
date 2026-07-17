# Douyin Serial Factor Fix Log

This log enforces the requested serial workflow. Work must move one factor at a time only after the previous factor has a passing verification gate.

## Evidence Policy

Use only repository evidence currently available in code, tests, and prior debugging docs unless the operator provides screenshots, HAR files, payloads, API responses, or logs. No attached screenshots, HAR files, real request payloads, or real API responses are present in this task context at initialization.

## Factor 1 — Identity / aweme_id Mapping

### Symptom

Prior debugging evidence showed possible metadata fan-out risk: different visible video cards could receive repeated network-derived title/thumbnail/posted/stats bundles if a non-ID merge path or stale object reuse reached the merge layer.

### Mini Truth Table

| Expected truth from real item | Actual truth at current stage | Exact mismatch | Exact root cause |
| --- | --- | --- | --- |
| Visible DOM card `7420000000000000101` receives only network item `7420000000000000101`. | Behavioral test proves title/count/diagnostic network ID are from `7420000000000000101`. | None after current identity hardening. | Previous risk was insufficient behavioral proof around merge-by-index/object-reference fan-out; current code uses an `aweme_id` map and matching guard. |
| Visible DOM card `7420000000000000102` receives only network item `7420000000000000102`, even when network list order is different. | Behavioral test passes with shuffled network list order. | None after current identity hardening. | Current merge uses `canonicalNetworkMap()` and does not use list position. |
| Visible DOM card `7420000000000000103` receives only network item `7420000000000000103`. | Behavioral test proves item-local count/title and matched `raw.network_aweme_id`. | None after current identity hardening. | Current merge is keyed by DOM-derived `aweme_id`. |
| Network item `9999999999999999999` with no visible matching DOM card must not merge into visible items. | Behavioral test proves its title never appears in visible outputs. | None. | Unmatched network IDs are ignored by canonical item assembly. |
| Network item with missing `aweme_id` must not merge into visible items. | Behavioral test proves missing-ID title never appears in visible outputs. | None. | Network canonicalization skips empty IDs. |
| Shared source `url_list` object must not be reused across merged output items. | Behavioral test proves output arrays are different object references. | None. | Merge clones network metadata and constructs fresh output arrays. |

### Root Cause

The current audited code already contains the required narrow identity hardening from the prior work: DOM cards are canonicalized by parsed `aweme_id`, network items are canonicalized by non-empty `aweme_id`, and the merge helper rejects mismatched network objects. The remaining Factor 1 gap was verification quality: existing tests mostly asserted source patterns rather than proving three distinct DOM items cannot receive index-based, missing-ID, mismatched-ID, or shared-object fan-out.

### Files Changed

- Added behavioral Factor 1 test: `apps/extension-douyin-capture/src/extractor.identity.test.ts`.
- Updated extension test command to include the Factor 1 identity gate: `apps/extension-douyin-capture/package.json`.

### Verification Run

- `npm --prefix apps/extension-douyin-capture run typecheck && npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `npm --prefix apps/extension-douyin-capture test`

### Pass/Fail Result

Passed. Factor 1 is verified before moving to Factor 2.

## Factor 2 — Thumbnail Extraction and Binding

### Symptom

Prior debugging evidence showed possible thumbnail fan-out risk: multiple visible cards could display the same thumbnail if network thumbnail metadata was merged by list order, missing identity, shared object reuse, or frontend stale resolution instead of the already-verified canonical `aweme_id` item.

### Mini Truth Table

| Expected truth from real item | Actual truth at current stage | Exact mismatch | Exact root cause |
| --- | --- | --- | --- |
| Visible DOM card `7420000000000000101` receives thumbnail `network-101.jpeg` from matching network item `7420000000000000101`. | Behavioral test proves output `thumbnail_url` is `https://p3.douyinpic.com/obj/network-101.jpeg`. | None after current thumbnail merge hardening. | Current merge first gates network metadata by `aweme_id`, then chooses the matched network thumbnail. |
| Visible DOM card `7420000000000000102` receives thumbnail `network-102.jpeg`, even though its network record appears first in the shuffled network list. | Behavioral test proves output `thumbnail_url` is `https://p3.douyinpic.com/obj/network-102.jpeg`. | None. | Current code uses `canonicalNetworkMap()` and does not bind thumbnails by network list position. |
| Visible DOM card `7420000000000000103` receives thumbnail `network-103.jpeg`. | Behavioral test proves output `thumbnail_url` is `https://p3.douyinpic.com/obj/network-103.jpeg`. | None. | Thumbnail selection is scoped to the canonical item merge. |
| Visible DOM card `7420000000000000104` has matching network metadata but no network thumbnail, so it should use DOM fallback `dom-104.jpeg`. | Behavioral test proves output `thumbnail_url` is `https://p3.douyinpic.com/obj/dom-104.jpeg` and `thumbnail_source` is `dom_fallback`. | None. | Current merge uses `networkThumbnail ?? domThumbnail ?? null`, preserving same-item DOM fallback when matched network metadata lacks a thumbnail. |
| Unmatched network thumbnail `mismatch.jpeg` must not merge into visible items. | Behavioral test proves no output item has that thumbnail. | None. | Unmatched network IDs are ignored by canonical item assembly. |
| Missing-ID network thumbnail `missing-id.jpeg` must not merge into visible items. | Behavioral test proves no output item has that thumbnail. | None. | Network canonicalization skips empty IDs. |
| Frontend resolver must not fan out one item's metadata thumbnail across another item. | Existing focused web resolver test proves two different `aweme_id` items resolve distinct metadata thumbnails. | None. | `resolveThumbnailUrl()` resolves only from the item object passed to it; React media tiles are keyed by backend item id. |

### Root Cause

The current audited production path already contains the required thumbnail binding behavior: network thumbnail extraction normalizes cover fields into per-`aweme_id` metadata, extension merge only accepts matching network metadata, backend persistence stores the canonical thumbnail on the same captured item, and frontend resolution reads the current item only. The remaining Factor 2 gap was verification quality: existing tests covered source patterns, backend priority, and frontend resolver behavior, but did not behaviorally prove extension extraction binds three distinct thumbnails plus a DOM fallback thumbnail to the correct canonical `aweme_id` items.

### Files Changed

- Extended behavioral Factor 1/2 gate: `apps/extension-douyin-capture/src/extractor.identity.test.ts`.

### Verification Run

- `npm --prefix apps/extension-douyin-capture run typecheck && npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `npm --prefix apps/extension-douyin-capture test`
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`

### Pass/Fail Result

Passed. Factor 2 is verified before moving to Factor 3.

## Factor 3 — Duration + Posted

### Symptom

Prior debugging evidence showed possible duration/posted fan-out risk: visible cards could display repeated duration or posted timestamps if network metadata merged by list order, missing identity, shared object reuse, or if default network timestamps were accepted as real posted truth.

### Mini Truth Table

| Expected truth from real item | Actual truth at current stage | Exact mismatch | Exact root cause |
| --- | --- | --- | --- |
| Visible DOM card `7420000000000000101` receives duration `00:11` and posted timestamp `2026-04-27T10:11:00.000Z` from matching network item `7420000000000000101`. | Behavioral test proves output duration and posted timestamp match item `7420000000000000101`. | None after current duration/posted hardening. | Current merge gates network metadata by `aweme_id` before choosing duration or posted fields. |
| Visible DOM card `7420000000000000102` receives duration `00:22` and posted timestamp `2026-04-27T10:22:00.000Z`, even though its network record appears first in the shuffled network list. | Behavioral test proves output values remain bound to item `7420000000000000102`. | None. | Current code uses `canonicalNetworkMap()` and does not bind duration/posted by network list position. |
| Visible DOM card `7420000000000000103` receives duration `00:33`, but rejects default midnight network posted timestamp `2026-04-27T00:00:00.000Z`. | Behavioral test proves duration is `33`, posted timestamp is not the default midnight timestamp, and `posted_source` falls back to `dom_text`. | None. | `validNetworkPostedAt()` rejects midnight timestamps before same-item DOM posted fallback. |
| Visible DOM card `7420000000000000104` has matching network metadata but no network duration or posted timestamp, so it should use DOM fallback `04:04` and DOM posted text. | Behavioral test proves `duration_seconds` is `244`, `duration_text` is `04:04`, and `posted_source` is `dom_text`. | None. | Merge order is matching network values first, same-item DOM fallback second. |
| Unmatched network duration/post `999` / `2026-04-27T10:59:00.000Z` must not merge into visible items. | Behavioral test proves no output item has those values. | None. | Unmatched network IDs are ignored by canonical item assembly. |
| Missing-ID network duration/post `888` / `2026-04-27T10:58:00.000Z` must not merge into visible items. | Behavioral test proves no output item has those values. | None. | Network canonicalization skips empty IDs. |
| Frontend resolver must display item-local duration/posted truth. | Existing focused web resolver test proves duration prefers `duration_text` and posted prefers formatted `posted_at` before `posted_text`. | None. | `resolveDuration()` and `resolvePosted()` resolve only from the current item object. |

### Root Cause

The current audited production path already contains the required duration and posted binding behavior: network duration and posted data are normalized per `aweme_id`, extension merge only accepts matching network metadata, default midnight network posted timestamps are rejected, backend persistence stores duration/posted fields on the same captured item, and frontend resolution reads the current item only. The remaining Factor 3 gap was verification quality: existing tests were mostly source-pattern or resolver checks and did not behaviorally prove multi-item duration/posted binding, default timestamp rejection, DOM fallback, and no unmatched or missing-ID fan-out.

### Files Changed

- Extended behavioral Factor 1/2/3 gate: `apps/extension-douyin-capture/src/extractor.identity.test.ts`.

### Verification Run

- `npm --prefix apps/extension-douyin-capture run typecheck && npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `npm --prefix apps/extension-douyin-capture test`
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`

### Pass/Fail Result

Passed. Factor 3 is verified before moving to Factor 4.

## Factor 4 — Views / Likes / Comments

### Symptom

Prior debugging evidence showed possible views/likes/comments fan-out risk: different visible cards could display repeated stats if network `statistics` metadata merged by list order, missing identity, shared object reuse, or if DOM metric fallback was not scoped to the same visible card.

### Mini Truth Table

| Expected truth from real item | Actual truth at current stage | Exact mismatch | Exact root cause |
| --- | --- | --- | --- |
| Visible DOM card `7420000000000000101` receives view/like/comment counts `101` / `1101` / `2101` from matching network item `7420000000000000101`. | Behavioral test proves the canonical and nested `statistics` counts match those values. | None after current stats binding verification. | Current merge gates network metadata by `aweme_id` before choosing stats fields. |
| Visible DOM card `7420000000000000102` receives counts `102` / `1202` / `2202`, even though its network record appears first in the shuffled network list. | Behavioral test proves output stats remain bound to item `7420000000000000102`. | None. | Current code uses `canonicalNetworkMap()` and does not bind stats by network list position. |
| Visible DOM card `7420000000000000103` receives counts `103` / `1303` / `2303`. | Behavioral test proves output stats remain distinct from the other visible items. | None. | Network stats are normalized per `aweme_id` and merged only through the canonical item merge. |
| Visible DOM card `7420000000000000104` has matching network metadata but no network stats, so it should use same-item DOM fallback counts `404` / `44` / `4`. | Behavioral test proves the canonical fields and nested `statistics` fields use those DOM fallback counts. | None. | Merge order is matching network stats first, same-item DOM metrics fallback second. |
| Unmatched network stats `999` / `1999` / `2999` must not merge into visible items. | Behavioral test proves no output item has those values. | None. | Unmatched network IDs are ignored by canonical item assembly. |
| Missing-ID network stats `888` / `1888` / `2888` must not merge into visible items. | Behavioral test proves no output item has those values. | None. | Network canonicalization skips empty IDs. |
| Backend/API/frontend preserve and render item-local stats. | Audit shows backend stores canonical stats in `metadata_json`, preserves merged `statistics`, response hydration exposes item-local numeric fields, and frontend resolvers read only the current item. Existing web resolver verification passes. | None. | Current backend and frontend paths are per captured item and do not use cross-item caches. |

### Root Cause

The current audited production path already contains the required views/likes/comments binding behavior: network stats are normalized per `aweme_id`, DOM metric fallback is extracted from the same visible card text, extension merge only accepts matching network metadata, backend persistence stores canonical stats on the same captured item and preserves nested `statistics`, API response hydration exposes canonical numeric fields, and frontend resolution reads the current item only. The remaining Factor 4 gap was verification quality: existing tests proved source patterns and one frontend canonical metric preference, but did not behaviorally prove multi-item stats binding, DOM fallback, nested `statistics` consistency, and no unmatched or missing-ID stats fan-out.

### Files Changed

- Extended behavioral Factor 1/2/3/4 gate: `apps/extension-douyin-capture/src/extractor.identity.test.ts`.

### Verification Run

- `npm --prefix apps/extension-douyin-capture run typecheck && npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `npm --prefix apps/extension-douyin-capture test`
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`

### Pass/Fail Result

Passed. Factor 4 is verified before moving to Factor 5.

## Factor 5 — Preview / Source Link / Media Asset Statuses

### Symptom

Prior debugging evidence showed status conflation risk: capture ingestion could mark media assets as `ready` from requested/legacy payload status even when the capture had no thumbnail, no source link, no generated media asset, and no downstream artifact evidence.

### Mini Truth Table

| Expected truth from real item | Actual truth at current stage | Exact mismatch | Exact root cause |
| --- | --- | --- | --- |
| A captured item with no true thumbnail or preview image should have `preview_status = missing`. | Existing backend test proves requested `preview_status = ready` is overridden to `missing` when no thumbnail exists. | None. | `_derive_preview_status()` derives readiness from a valid thumbnail candidate rather than trusting requested status. |
| A captured item with no source URL or share URL should have `source_link_status = missing`. | Existing backend test proves requested `source_link_status = captured` is overridden to `missing` when no source/share URL exists. | None. | `_derive_source_link_status()` derives captured status from source/share URL evidence. |
| A captured item with no generated media asset evidence should have `media_asset_status = not_generated`, even if incoming payload requests `ready`. | Narrow fix now proves requested `media_asset_status = ready` is overridden to `not_generated`. | Previously backend accepted requested `ready`. | `_derive_media_asset_status()` trusted requested `ready` and legacy `media_status = ready` without generated asset evidence. |
| Legacy `media_status` should remain a derived compatibility field: `ready` only for a real ready media asset, `source_link_captured` for source-link-only captures, otherwise `missing`. | Backend test now proves no-asset/no-source item gets `media_status = missing`. | Previously requested/legacy `ready` could make `media_status = ready`. | Legacy media status was downstream of the too-permissive media asset status. |
| Frontend status labels should preserve separated semantics. | Existing web resolver test passes: preview missing, source link missing, and media asset not generated remain distinct. | None. | Frontend resolvers use separate `preview_status`, `source_link_status`, and `media_asset_status` fields. |

### Root Cause

Preview and source-link derivation were already evidence-based, but media asset derivation was too permissive. `_derive_media_asset_status()` accepted requested `ready` and legacy `media_status = ready`, even though extension capture does not generate media assets. That allowed source-link/preview capture evidence to be conflated with downstream media asset readiness. The narrow fix keeps `failed` as an explicit requested failure state and otherwise derives Phase 1 capture-ingest media assets as `not_generated` until a future downstream process provides real asset evidence.

### Files Changed

- Updated media asset status derivation: `apps/api/src/services/capture_inbox_service.py`.
- Updated backend status regression test: `apps/api/tests/test_douyin_extension_capture_service.py`.

### Verification Run

- Initial incorrect command failed because it ran from the repository root without the API package import path: `python -m unittest apps.api.tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_build_item_keeps_preview_and_media_missing_when_assets_are_absent`.
- Correct targeted command passed: `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_build_item_keeps_preview_and_media_missing_when_assets_are_absent` from `apps/api`.
- Full API extension capture service suite passed: `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`.
- Extension suite passed: `npm --prefix apps/extension-douyin-capture test`.
- Web canonical resolver suite passed: `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`.

### Pass/Fail Result

Passed. Factor 5 is verified before moving to Factor 6.

## Factor 6 — Backend Persistence + API Response Correctness

### Symptom

Backend persistence and response hydration used truthiness-based fallback for canonical numeric fields. A legitimate zero value for duration or stats could be treated as absent and replaced by fallback raw/statistics aliases before response serialization or promotion adapter projection.

### Mini Truth Table

| Expected truth from real item | Actual truth at current stage | Exact mismatch | Exact root cause |
| --- | --- | --- | --- |
| A captured item with `duration_seconds = 0` should persist and return `0`, not fall back to another duration alias. | New backend test proves persisted item and `CapturedItemResponse` both expose `duration_seconds = 0`. | Previously possible fallback loss for zero duration. | `_build_item()` used `raw_item.get("duration_seconds") or raw_item.get("duration")`, so numeric zero was treated as missing. |
| Captured item canonical `view_count = 0`, `like_count = 0`, and `comment_count = 0` should persist as real values. | New backend test proves `metadata_json` and merged `raw_payload_json.statistics` preserve all three zero canonical stats. | Previously zero canonical stats could be replaced by alternate `statistics` values. | Canonical stat derivation used truthiness-based `or` fallback. |
| API response fields should expose canonical zero stats without requiring frontend raw blob guessing. | New backend test validates `CapturedItemResponse.model_validate(item)` returns `view_count = 0`, `like_count = 0`, and `comment_count = 0`. | Previously response hydration depended on whichever value survived persistence. | Persistence now preserves zero with explicit presence fallback before response hydration. |
| Promotion adapter payload should preserve canonical zero stats when composing downstream payloads. | Audit/fix changed adapter field selection from truthiness fallback to explicit presence fallback. | Previously adapter projection could replace zero metadata values with raw fallback values. | `_adapter_payload_for_items()` used `metadata.get(...) or raw.get(...)` for stats. |
| API response serialization should preserve per-item identity without cross-item reuse. | Audit shows routes instantiate a fresh `CapturedItemResponse` per item and hydrate from that item only. | None. | Response routes iterate item objects and do not use shared mutable response metadata. |

### Root Cause

The backend/API contract already exposed canonical metadata fields and response hydration from `metadata_json`, raw payload, and nested `statistics`, but Factor 6 found a real zero-value persistence defect. Several backend paths used Python truthiness fallback (`or`) where explicit presence semantics were required. Since `0` is falsy, a legitimate zero duration or stat could be replaced by a fallback alias. The narrow fix introduces explicit first-present fallback semantics for canonical numeric persistence and adapter projection, and also sets `preview_ready` / `media_ready` booleans during item construction so direct response validation of newly built items matches persisted database defaults.

### Files Changed

- Updated backend canonical field fallback and readiness booleans: `apps/api/src/services/capture_inbox_service.py`.
- Added backend persistence/API response regression test: `apps/api/tests/test_douyin_extension_capture_service.py`.

### Verification Run

- `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_build_item_and_response_preserve_zero_canonical_stats` from `apps/api`.
- `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_build_item_persists_canonical_thumbnail_url` from `apps/api`.
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`.
- `npm --prefix apps/extension-douyin-capture test`.
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`.

### Pass/Fail Result

Passed. Factor 6 is verified before moving to Factor 7.

## Factor 7 — Frontend Rendering Correctness and Stale Reuse Prevention

### Symptom

Frontend rendering mostly used item-local canonical resolvers and stable item IDs, but the stats fallback resolver preferred alternate raw aliases before canonical nested statistic keys when direct response fields and `metadata_json` were absent. That could display a stale/legacy alias value even when the raw item-local `statistics` object contained canonical `view_count` / `like_count` values.

### Mini Truth Table

| Expected truth from real item | Actual truth at current stage | Exact mismatch | Exact root cause |
| --- | --- | --- | --- |
| A tile with direct canonical `view_count = 0`, `like_count = 0`, `comment_count = 0`, and `duration_seconds = 0` should render `0` metrics and `0:00` duration. | New frontend resolver test proves direct zero values render as real values before metadata/raw aliases. | None after Factor 6 + Factor 7 verification. | Resolver direct-field checks already used explicit numeric type checks, preserving zero. |
| If direct fields are absent but raw `statistics` contains both canonical `view_count` and alternate `play_count`, the canonical nested field should win. | New frontend resolver test proves `view_count = 101` wins over `play_count = 999`. | Previously `play_count` could win over canonical nested `view_count`. | `canonicalNumber()` checked the alternate alias before the canonical nested statistics key. |
| If direct fields are absent but raw `statistics` contains both canonical `like_count` and alternate `digg_count`, the canonical nested field should win. | New frontend resolver test proves `like_count = 202` wins over `digg_count = 888`. | Previously `digg_count` could win over canonical nested `like_count`. | `canonicalNumber()` checked the alternate alias before the canonical nested statistics key. |
| Two different item objects should render distinct item-local thumbnails, duration, posted text, stats, preview status, source-link status, and media-asset status. | Extended frontend resolver test proves distinct outputs remain scoped to each item. | None. | Resolvers read only the passed item object and do not use shared caches. |
| Gallery and inspector rendering should not reuse stale React state across items. | Audit shows `MediaTileGallery` uses `key={item.id}`, active inspector state is keyed by `activeItemId`, and inspector expanded text resets on `item?.id`. | None. | Current React state boundaries are item-id based. |
| Action response raw/source details should not persist across new actions. | Audit shows `runAction()` clears `rawDetails` and `sourceUrls` before each action and reloads session state afterward. | None. | Current action flow resets per-action diagnostics before awaiting the new response. |

### Root Cause

The UI rendering path already used stable item identity and item-local resolver calls for tiles, inspector, filters, and action diagnostics. The real Factor 7 defect was narrower: the metric resolver fallback order was not fully canonical when falling back to raw nested stats. `canonicalNumber()` preferred alternate aliases such as `play_count` / `digg_count` before canonical nested `view_count` / `like_count`, so stale or legacy aliases could render over canonical nested fields if direct API fields and metadata were missing. The fix changes fallback order to direct field, metadata canonical key, raw nested canonical key, then alternate alias.

### Files Changed

- Updated frontend metric fallback order: `apps/web/src/lib/captureInboxCanonical.ts`.
- Extended frontend canonical resolver tests: `apps/web/src/test/capture-inbox-canonical.test.ts`.

### Verification Run

- First Factor 7 verification run failed because the new status scoping fixture placed `preview_status` only inside `metadata_json`; production `resolvePreviewStatus()` intentionally reads API response fields and thumbnail evidence for statuses. The fixture was corrected to model API response fields directly.
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`.

### Pass/Fail Result

Passed. Factor 7 is verified and all serial factors now have passing verification gates.
